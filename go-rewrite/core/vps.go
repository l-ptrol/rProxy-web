package core

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// Пути к данным rProxy
const (
	RProxyRoot = "/opt/etc/rproxy"
	SSHKeyPath = "/opt/etc/rproxy/id_ed25519"
)

// VPSDir — директория конфигов VPS
var VPSDir = filepath.Join(RProxyRoot, "vps")

// EnsureSSHKey гарантирует наличие SSH-ключа для работы с VPS
func EnsureSSHKey() {
	if _, err := os.Stat(SSHKeyPath); err == nil {
		os.Chmod(SSHKeyPath, 0600)
		return
	}

	Msg("Генерирую SSH-ключ (ed25519)...")

	keygen := "/opt/bin/ssh-keygen"
	if _, err := os.Stat(keygen); os.IsNotExist(err) {
		keygen = "ssh-keygen"
	}

	cmd := exec.Command(keygen, "-t", "ed25519", "-f", SSHKeyPath, "-N", "", "-q")
	if err := cmd.Run(); err != nil {
		Err(fmt.Sprintf("Не удалось сгенерировать SSH-ключ: %v", err))
		return
	}
	os.Chmod(SSHKeyPath, 0600)

	// Генерируем публичный ключ если не создался автоматически
	pubKey := SSHKeyPath + ".pub"
	if _, err := os.Stat(pubKey); os.IsNotExist(err) {
		out, err := exec.Command(keygen, "-y", "-f", SSHKeyPath).Output()
		if err == nil {
			os.WriteFile(pubKey, out, 0644)
		}
	}
}

// RunRemote выполняет команду на удаленном VPS через SSH с таймаутом
func RunRemote(vpsCfg map[string]string, command string, timeout time.Duration) (bool, string) {
	sshBin := ResolveBin("ssh")

	host := vpsCfg["VPS_HOST"]
	user := vpsCfg["VPS_USER"]
	if user == "" {
		user = "root"
	}
	port := vpsCfg["VPS_PORT"]
	if port == "" {
		port = "22"
	}

	args := GetSSHArgs(sshBin, host, user, port, SSHKeyPath, false)
	args = append(args, fmt.Sprintf("%s@%s", user, host), command)

	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	cmd := exec.CommandContext(ctx, sshBin, args...)
	cmd.Env = GetProcessEnv()

	outBytes, err := cmd.CombinedOutput()
	output := strings.TrimSpace(string(outBytes))

	if ctx.Err() == context.DeadlineExceeded {
		return false, "Превышено время ожидания SSH"
	}

	if err != nil {
		return false, output
	}
	return true, output
}

// RunRemoteSimple — упрощённая версия с дефолтным таймаутом 30 сек
func RunRemoteSimple(vpsCfg map[string]string, command string) (bool, string) {
	return RunRemote(vpsCfg, command, 30*time.Second)
}

// FindVPSByDomain ищет VPS, на который указывает домен
func FindVPSByDomain(domain string) string {
	ip := GetDomainIP(domain)
	if ip == "" {
		return ""
	}

	if _, err := os.Stat(VPSDir); os.IsNotExist(err) {
		return ""
	}

	entries, err := os.ReadDir(VPSDir)
	if err != nil {
		return ""
	}

	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".conf") {
			continue
		}
		cfg := LoadConfig(filepath.Join(VPSDir, e.Name()))
		if cfg["VPS_HOST"] == ip {
			return strings.TrimSuffix(e.Name(), ".conf")
		}
	}
	return ""
}

// SetupVPS выполняет первичную настройку окружения на удаленном VPS
func SetupVPS(vpsCfg map[string]string) (bool, string) {
	setupScript := `
export DEBIAN_FRONTEND=noninteractive
mkdir -p /etc/nginx/sites-enabled
mkdir -p /etc/nginx/streams-enabled

if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq nginx libnginx-mod-stream certbot python3-certbot-nginx psmisc socat curl
elif command -v yum >/dev/null 2>&1; then
    yum install -y epel-release && yum install -y nginx nginx-mod-stream certbot python3-certbot-nginx psmisc socat curl
fi

grep -q 'sites-enabled' /etc/nginx/nginx.conf || sed -i '/http {/a\    include /etc/nginx/sites-enabled/*.conf;' /etc/nginx/nginx.conf

if ! grep -q 'streams-enabled' /etc/nginx/nginx.conf; then
    if grep -q 'stream {' /etc/nginx/nginx.conf; then
         echo "include /etc/nginx/streams-enabled/*.conf;" >> /etc/nginx/nginx.conf
    else
         printf "\nstream {\n    include /etc/nginx/streams-enabled/*.conf;\n}\n" >> /etc/nginx/nginx.conf
    fi
fi

systemctl enable nginx && systemctl restart nginx

sed -i 's/^#*GatewayPorts.*/GatewayPorts yes/' /etc/ssh/sshd_config
sed -i 's/^#*AllowTcpForwarding.*/AllowTcpForwarding yes/' /etc/ssh/sshd_config
systemctl restart ssh || systemctl restart sshd

(crontab -l 2>/dev/null; echo "0 0,12 * * * certbot renew -q --deploy-hook 'systemctl reload nginx'") | sort -u | crontab -
`
	Msg(fmt.Sprintf("Настройка окружения на VPS %s...", vpsCfg["VPS_HOST"]))
	return RunRemote(vpsCfg, setupScript, 300*time.Second)
}

// CheckSSLExists проверяет наличие SSL сертификата для домена на VPS
func CheckSSLExists(vpsCfg map[string]string, domain string) bool {
	success, _ := RunRemoteSimple(vpsCfg, fmt.Sprintf("[ -d /etc/letsencrypt/live/%s ]", domain))
	return success
}

// UploadContent загружает текстовый контент в файл на VPS через SCP
func UploadContent(vpsCfg map[string]string, content, remotePath string) (bool, string) {
	host := vpsCfg["VPS_HOST"]
	user := vpsCfg["VPS_USER"]
	if user == "" {
		user = "root"
	}
	port := vpsCfg["VPS_PORT"]
	if port == "" {
		port = "22"
	}

	scpBin := ResolveBin("scp")

	// Создаём временный файл
	tmpFile, err := os.CreateTemp("", "rproxy-upload-*")
	if err != nil {
		return false, fmt.Sprintf("Не удалось создать временный файл: %v", err)
	}
	tmpPath := tmpFile.Name()
	defer os.Remove(tmpPath)

	if _, err := tmpFile.WriteString(content); err != nil {
		tmpFile.Close()
		return false, fmt.Sprintf("Ошибка записи: %v", err)
	}
	tmpFile.Close()

	args := GetSSHArgs(scpBin, host, user, port, SSHKeyPath, true)
	cmdArgs := append([]string{"-q"}, args...)
	cmdArgs = append(cmdArgs, tmpPath, fmt.Sprintf("%s@%s:%s", user, host, remotePath))

	cmd := exec.Command(scpBin, cmdArgs...)
	cmd.Env = GetProcessEnv()

	if out, err := cmd.CombinedOutput(); err != nil {
		return false, string(out)
	}
	return true, ""
}

// DeployVhost деплоит конфиг Nginx на VPS
func DeployVhost(vpsCfg map[string]string, name, content, path string) (bool, string) {
	if path == "" {
		path = "/etc/nginx/sites-enabled"
	}

	remotePath := fmt.Sprintf("%s/rproxy_%s.conf", path, name)
	success, errMsg := UploadContent(vpsCfg, content, remotePath)
	if !success {
		return false, errMsg
	}

	return RunRemoteSimple(vpsCfg, "nginx -t && systemctl reload nginx")
}

// RemoveVhost удаляет конфиг Nginx с VPS
func RemoveVhost(vpsCfg map[string]string, name string) (bool, string) {
	cmd := fmt.Sprintf("rm -f /etc/nginx/sites-enabled/rproxy_%s.conf /etc/nginx/streams-enabled/rproxy_%s.conf && (nginx -t && systemctl reload nginx || true)", name, name)
	return RunRemoteSimple(vpsCfg, cmd)
}

// RunCertbot запускает Certbot для получения SSL
func RunCertbot(vpsCfg map[string]string, domain string) (bool, string) {
	isIP := regexp.MustCompile(`^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$`).MatchString(domain)

	profile := ""
	if isIP {
		profile = "--cert-profile shortlived"
	}

	cmd := fmt.Sprintf("certbot certonly --nginx -d %s %s --non-interactive --agree-tos --register-unsafely-without-email", domain, profile)
	return RunRemote(vpsCfg, cmd, 120*time.Second)
}

// CleanupVPS — умная очистка VPS от фантомных конфигов
func CleanupVPS(vpsCfg map[string]string, activeServices []string) (bool, string) {
	success, output := RunRemoteSimple(vpsCfg, "ls /etc/nginx/sites-enabled/rproxy_*.conf /etc/nginx/streams-enabled/rproxy_*.conf 2>/dev/null")
	if !success || output == "" {
		return true, "No files found for cleanup"
	}

	files := strings.Split(output, "\n")
	var deleted []string

	for _, f := range files {
		f = strings.TrimSpace(f)
		if f == "" {
			continue
		}
		base := filepath.Base(f)
		sName := strings.TrimPrefix(base, "rproxy_")
		sName = strings.TrimSuffix(sName, ".conf")

		// Проверяем, есть ли в списке активных
		found := false
		for _, active := range activeServices {
			if active == sName {
				found = true
				break
			}
		}

		if !found {
			RunRemoteSimple(vpsCfg, fmt.Sprintf("rm -f %s", f))
			deleted = append(deleted, base)
		}
	}

	if len(deleted) > 0 {
		RunRemoteSimple(vpsCfg, "nginx -t && systemctl reload nginx")
		return true, fmt.Sprintf("Deleted: %s", strings.Join(deleted, ", "))
	}
	return true, "VPS is clean"
}

// HealthCheck — проверка состояния VPS: Nginx, SSL, Certbot
func HealthCheck(vpsCfg map[string]string) map[string]interface{} {
	results := map[string]interface{}{
		"nginx":     "Unknown",
		"ssl_timer": "Unknown",
		"certs":     []map[string]interface{}{},
	}

	// 1. Проверка Nginx
	success, output := RunRemoteSimple(vpsCfg, "systemctl is-active nginx")
	if success && strings.Contains(output, "active") {
		results["nginx"] = "Запущен"
	} else {
		results["nginx"] = "Остановлен"
	}

	// 2. Проверка Certbot Timer
	success, output = RunRemoteSimple(vpsCfg, "systemctl list-timers | grep certbot")
	if success && strings.Contains(output, "certbot") {
		results["ssl_timer"] = "Активен (Systemd)"
		parts := strings.Fields(output)
		if len(parts) > 1 {
			results["next_run"] = parts[0] + " " + parts[1]
		}
	} else {
		results["ssl_timer"] = "Не найден"
	}

	// 3. Список сертификатов
	success, output = RunRemoteSimple(vpsCfg, "certbot certificates")
	if success && strings.Contains(output, "Found the following certs") {
		blocks := strings.Split(output, "Certificate Name:")
		var certs []map[string]interface{}

		for _, block := range blocks[1:] {
			cert := make(map[string]interface{})

			domainsRe := regexp.MustCompile(`Domains:\s+(.*)`)
			expiryRe := regexp.MustCompile(`Expiry Date:\s+(.*?)\s+\(VALID:\s+(\d+)\s+days\)`)

			if m := domainsRe.FindStringSubmatch(block); len(m) > 1 {
				cert["domains"] = strings.TrimSpace(m[1])
			}
			if m := expiryRe.FindStringSubmatch(block); len(m) > 2 {
				cert["expiry"] = strings.TrimSpace(m[1])
				var days int
				fmt.Sscanf(m[2], "%d", &days)
				cert["days"] = days
			}

			if len(cert) > 0 {
				certs = append(certs, cert)
			}
		}
		results["certs"] = certs
	}

	return results
}

// SetupSSHWithPassword настраивает доступ по ключу с использованием временного пароля
func SetupSSHWithPassword(vpsCfg map[string]string, password string) (bool, string) {
	EnsureSSHKey()

	pubKeyPath := SSHKeyPath + ".pub"
	if _, err := os.Stat(pubKeyPath); os.IsNotExist(err) {
		pubKeyPath = "id_ed25519.pub"
	}

	pubKey, err := os.ReadFile(pubKeyPath)
	if err != nil {
		return false, "Не удалось прочитать локальный публичный ключ: " + err.Error()
	}

	sshpassCmd := "sshpass"
	if _, err := os.Stat("/opt/bin/sshpass"); err == nil {
		sshpassCmd = "/opt/bin/sshpass"
	} else if _, err := exec.LookPath("sshpass"); err != nil {
		// Пытаемся установить sshpass если его нет через opkg
		exec.Command("/opt/bin/opkg", "update").Run()
		exec.Command("/opt/bin/opkg", "install", "sshpass").Run()
		if _, err := os.Stat("/opt/bin/sshpass"); err == nil {
			sshpassCmd = "/opt/bin/sshpass"
		} else {
			return false, "Утилита sshpass не найдена и не удалось установить через opkg. Установите её вручную: opkg install sshpass"
		}
	}

	host := vpsCfg["VPS_HOST"]
	user := vpsCfg["VPS_USER"]
	if user == "" {
		user = "root"
	}
	port := vpsCfg["VPS_PORT"]
	if port == "" {
		port = "22"
	}

	// Команда для записи публичного ключа в authorized_keys на удаленном сервере.
	// Используем StrictHostKeyChecking=no для обхода подтверждения `yes/no`.
	cmdLines := fmt.Sprintf(`mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "%s" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`, strings.TrimSpace(string(pubKey)))

	cmd := exec.Command(sshpassCmd, "-p", password, "ssh", "-p", port, "-o", "StrictHostKeyChecking=no", fmt.Sprintf("%s@%s", user, host), cmdLines)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return false, fmt.Sprintf("Ошибка sshpass: %v\nВывод: %s", err, string(out))
	}

	return true, "Ключ успешно скопирован на сервер!"
}
