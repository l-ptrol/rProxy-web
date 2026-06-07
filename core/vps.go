package core

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"

	"golang.org/x/crypto/ssh"
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
	output := filterSSHOutput(strings.TrimSpace(string(outBytes)))

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

// SetupVPS выполняет первичную настройку окружения на удаленном VPS (v1.9.3-go)
func SetupVPS(vpsCfg map[string]string) (bool, string) {
	// Берём email для acme.sh из глобальных настроек
	gPath := filepath.Join(RProxyRoot, "rproxy.conf")
	gCfg := LoadConfig(gPath)
	acmeEmail := gCfg["ACME_EMAIL"]
	if acmeEmail == "" {
		acmeEmail = "admin@example.com"
	}

	setupScript := fmt.Sprintf(`
export DEBIAN_FRONTEND=noninteractive
mkdir -p /etc/nginx/sites-enabled
mkdir -p /etc/nginx/streams-enabled
mkdir -p /etc/nginx/ssl
chmod 755 /etc/nginx/ssl

if command -v apt-get >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y -qq nginx libnginx-mod-stream psmisc socat curl cron
elif command -v yum >/dev/null 2>&1; then
    yum install -y epel-release && yum install -y nginx nginx-mod-stream psmisc socat curl cron
fi

# Открытие портов 80 и 443 в брандмауэре для получения SSL
if command -v ufw >/dev/null 2>&1; then
    ufw allow 80/tcp || true
    ufw allow 443/tcp || true
    ufw reload || true
elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-service=http || true
    firewall-cmd --permanent --add-service=https || true
    firewall-cmd --reload || true
fi
iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || true

# Удаляем стандартный конфиг Nginx, чтобы избежать конфликта default_server
rm -f /etc/nginx/sites-enabled/default

# Настройка default server для блокировки левых доменов (Best Practice)
cat <<EOF > /etc/nginx/sites-enabled/00-default.conf
server {
    listen 80 default_server;
    server_name _;
    access_log off;
    log_not_found off;
    return 444; 
}
EOF

# Установка acme.sh (Pattern: rProxy-web)
if [ ! -f ~/.acme.sh/acme.sh ]; then
    curl -sL https://get.acme.sh | sh -s email=%s --force || true
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
`, acmeEmail)
	Msg(fmt.Sprintf("Настройка окружения на VPS %s...", vpsCfg["VPS_HOST"]))
	return RunRemote(vpsCfg, setupScript, 300*time.Second)
}

// CheckSSLExists проверяет наличие SSL сертификата для домена на VPS (v1.9.3-go)
func CheckSSLExists(vpsCfg map[string]string, domain string) bool {
	// Проверяем наличие, размер файлов сертификата/ключа и валидность самого сертификата через openssl
	checkCmd := fmt.Sprintf(
		"[ -s /etc/nginx/ssl/%[1]s.crt ] && [ -s /etc/nginx/ssl/%[1]s.key ] && openssl x509 -in /etc/nginx/ssl/%[1]s.crt -noout 2>/dev/null",
		domain,
	)
	success, _ := RunRemoteSimple(vpsCfg, checkCmd)
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

	cmd := "nginx -t && systemctl reload nginx"
	if strings.Contains(path, "stream") {
		// Для стрим-конфигов (TCP/UDP) требуется полный перезапуск и открытие портов в брандмауэре VPS
		firewallCmd := "iptables -I INPUT -p tcp --dport 40000:50000 -j ACCEPT 2>/dev/null; (command -v ufw >/dev/null && ufw allow 40000:50000/tcp || true)"
		cmd = fmt.Sprintf("%s; nginx -t && systemctl restart nginx", firewallCmd)
	}
	return RunRemoteSimple(vpsCfg, cmd)
}

// RemoveVhost удаляет конфиг Nginx с VPS
func RemoveVhost(vpsCfg map[string]string, name string) (bool, string) {
	cmd := fmt.Sprintf("rm -f /etc/nginx/sites-enabled/rproxy_%s.conf /etc/nginx/streams-enabled/rproxy_%s.conf && (nginx -t && systemctl reload nginx || true)", name, name)
	return RunRemoteSimple(vpsCfg, cmd)
}

// RunCertbot запускает выпуск SSL через acme.sh в режиме --nginx (v1.9.3-go)
func RunCertbot(vpsCfg map[string]string, domain string) (bool, string) {
	domain = strings.TrimSpace(domain)
	isIP := regexp.MustCompile(`^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$`).MatchString(domain)
	acmePath := "$HOME/.acme.sh/acme.sh"

	// Параметры выпуска
	profile := ""
	if isIP {
		profile = "--certificate-profile shortlived --days 3"
	}

	// Команда выпуска через acme.sh в режиме --nginx
	cmd := fmt.Sprintf("%s --issue --nginx --server letsencrypt -d %s %s --force", acmePath, domain, profile)
	
	crtPath := fmt.Sprintf("/etc/nginx/ssl/%s.crt", domain)
	keyPath := fmt.Sprintf("/etc/nginx/ssl/%s.key", domain)
	
	// Команда установки сертификата в системную папку Nginx с проверкой результата
	verifyCmd := fmt.Sprintf("[ -f %s ] && [ -f %s ]", crtPath, keyPath)
	installCmd := fmt.Sprintf("mkdir -p /etc/nginx/ssl && %s --install-cert -d %s --key-file %s --fullchain-file %s --reloadcmd 'systemctl reload nginx' && %s", acmePath, domain, keyPath, crtPath, verifyCmd)

	// Bash-скрипт с проверкой 80 и 443 портов, временным отключением конфликтующих служб и автозапуском Nginx
	scriptTemplate := `bash -c '
RESTORE_SERVICES=""
restore() {
    for s in $RESTORE_SERVICES; do
        echo "▸ Восстановление службы $s..."
        systemctl start "$s" || true
    done
}
trap restore EXIT

# 1. Открытие портов в брандмауэре перед выпуском
if command -v ufw >/dev/null 2>&1; then
    ufw allow 80/tcp || true
    ufw allow 443/tcp || true
    ufw reload || true
elif command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-service=http || true
    firewall-cmd --permanent --add-service=https || true
    firewall-cmd --reload || true
fi
iptables -I INPUT -p tcp --dport 80 -j ACCEPT 2>/dev/null || true
iptables -I INPUT -p tcp --dport 443 -j ACCEPT 2>/dev/null || true

# 2. Проверка, не заняты ли порты 80 и 443 сторонними процессами
for port in 80 443; do
    PORT_PID=""
    if command -v ss >/dev/null 2>&1; then
        PORT_PID=$(ss -tlnp sport = :$port 2>/dev/null | grep -oE "pid=[0-9]+" | cut -d= -f2 | head -n1)
    elif command -v netstat >/dev/null 2>&1; then
        PORT_PID=$(netstat -tlnp 2>/dev/null | grep -E ":$port\s" | grep -oE "[0-9]+/[-a-zA-Z0-9_]+" | cut -d/ -f1 | head -n1)
    elif command -v lsof >/dev/null 2>&1; then
        PORT_PID=$(lsof -t -i :$port 2>/dev/null | head -n1)
    fi

    if [ -n "$PORT_PID" ]; then
        PROC_NAME=$(ps -p "$PORT_PID" -o comm= 2>/dev/null | xargs)
        if [ "$PROC_NAME" != "nginx" ] && [ "$PROC_NAME" != "" ]; then
            echo "⚠️ Порт $port занят сторонним процессом: $PROC_NAME (PID: $PORT_PID)"
            UNIT=""
            if [ -f "/proc/$PORT_PID/cgroup" ]; then
                UNIT=$(cat "/proc/$PORT_PID/cgroup" 2>/dev/null | grep -oE "[^/]+\.service" | head -n1)
            fi
            if [ -z "$UNIT" ]; then
                UNIT=$(systemctl status "$PORT_PID" 2>/dev/null | grep -oE "^[● ]* ([^ ]+\.service)" | head -n1 | sed "s/[● ]*//g")
            fi
            
            if [ -n "$UNIT" ]; then
                # Проверим, не добавили ли уже эту службу в список восстановления
                if ! echo "$RESTORE_SERVICES" | grep -q "$UNIT"; then
                    echo "▸ Временно останавливаем службу $UNIT на время выпуска SSL..."
                    systemctl stop "$UNIT"
                    RESTORE_SERVICES="$RESTORE_SERVICES $UNIT"
                fi
            else
                echo "⚠️ Процесс $PROC_NAME не управляется systemd. Завершаем его принудительно (kill)..."
                kill -9 "$PORT_PID" || true
            fi
        fi
    fi
done

# Убедимся, что Nginx запущен
if ! systemctl is-active nginx >/dev/null 2>&1; then
    echo "▸ Запуск Nginx..."
    systemctl start nginx || true
fi

# 3. Выпуск сертификата через acme.sh
%s

# 4. Установка сертификата
%s
'`

	fullCmd := fmt.Sprintf(scriptTemplate, cmd, installCmd)
	Msg(fmt.Sprintf("Выпуск SSL для %s (режим: nginx, IP: %v)...", domain, isIP))
	
	success, output := RunRemote(vpsCfg, fullCmd, 300*time.Second)
	if success {
		if CheckSSLExists(vpsCfg, domain) {
			Msg(fmt.Sprintf("✅ SSL для %s успешно выпущен и установлен.", domain))
			return true, output
		} else {
			return false, "Certbot сообщил об успехе, но файлы в /etc/nginx/ssl/ отсутствуют!"
		}
	}
	return false, output
}

// CleanupVPS — умная очистка VPS от фантомных конфигов (v1.9.3-go)
func CleanupVPS(vpsCfg map[string]string, activeServices []string) (bool, string) {
	success, output := RunRemoteSimple(vpsCfg, "ls /etc/nginx/sites-enabled/rproxy_*.conf /etc/nginx/streams-enabled/rproxy_*.conf 2>/dev/null")
	
	var deleted []string

	if success && output != "" {
		files := strings.Split(output, "\n")
		for _, f := range files {
			f = strings.TrimSpace(f)
			if f == "" || strings.Contains(f, "rproxy_dom_") {
				continue // Групповые конфиги обрабатываем отдельно ниже
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
	}

	// Очистка групповых доменных конфигов
	CleanupOrphanDomainConfigs(vpsCfg)

	if len(deleted) > 0 {
		RunRemoteSimple(vpsCfg, "nginx -t && systemctl reload nginx")
		return true, fmt.Sprintf("Очищено: %s", strings.Join(deleted, ", "))
	}
	return true, "VPS очищен"
}

// CleanupOrphanDomainConfigs — полная зачистка всех заброшенных доменных конфигов на VPS
func CleanupOrphanDomainConfigs(vpsCfg map[string]string) {
	vpsName := ""
	// Находим имя VPS по его конфигу
	entries, _ := os.ReadDir(VPSDir)
	for _, e := range entries {
		vCfg := LoadConfig(filepath.Join(VPSDir, e.Name()))
		if vCfg["VPS_HOST"] == vpsCfg["VPS_HOST"] {
			vpsName = strings.TrimSuffix(e.Name(), ".conf")
			break
		}
	}
	if vpsName == "" {
		return
	}

	activePairs := GetAllActiveDomainPortPairs(vpsName)
	
	listCmd := "ls /etc/nginx/sites-enabled/rproxy_dom_*.conf 2>/dev/null"
	if success, output := RunRemoteSimple(vpsCfg, listCmd); success && output != "" {
		files := strings.Split(output, "\n")
		for _, f := range files {
			f = strings.TrimSpace(f)
			if f == "" {
				continue
			}
			
			// Ищем соответствие (домен:порт) в активных парах
			// Имя файла: /etc/nginx/sites-enabled/rproxy_dom_DOMAIN_ENCODED_PORT.conf
			base := filepath.Base(f)
			parts := strings.Split(strings.TrimSuffix(base, ".conf"), "_")
			if len(parts) < 4 {
				continue
			}
			
			port := parts[len(parts)-1]
			foundMatch := false
			for pair := range activePairs {
				pParts := strings.Split(pair, ":")
				pDom := pParts[0]
				pPort := pParts[1]
				
				if pPort == port {
					safeDom := strings.ReplaceAll(pDom, ".", "_")
					safeDom = strings.ReplaceAll(safeDom, "-", "_")
					safeDom = strings.ReplaceAll(safeDom, " ", "_")
					if strings.Contains(base, "rproxy_dom_"+safeDom+"_") {
						foundMatch = true
						break
					}
				}
			}
			
			if _, err := strconv.Atoi(port); err == nil && !foundMatch {
				Msg(fmt.Sprintf("Удаление заброшенного доменного конфига: %s", base))
				RunRemoteSimple(vpsCfg, fmt.Sprintf("rm -f %s", f))
			}
		}
	}
}

// HealthCheck выполняет проверку состояния VPS и SSL (v1.5.0-go)
func HealthCheck(vpsCfg map[string]string) map[string]interface{} {
	results := map[string]interface{}{
		"nginx":     "Неизвестно",
		"ssl_timer": "acme.sh (Cron)",
		"certs":     []map[string]interface{}{},
	}

	// 1. Проверка Nginx
	success, output := RunRemoteSimple(vpsCfg, "systemctl is-active nginx")
	if success && strings.Contains(output, "active") {
		results["nginx"] = "Запущен"
	} else {
		results["nginx"] = "Остановлен"
	}

	// 2. Проверка Cron (для acme.sh)
	success, output = RunRemoteSimple(vpsCfg, "crontab -l | grep acme.sh")
	if success && (strings.Contains(output, "acme.sh") || strings.Contains(output, "renew")) {
		results["ssl_timer"] = "Активен (Cron)"
	} else {
		results["ssl_timer"] = "Не настроен (Cron)"
	}

	// 3. Список сертификатов (только acme.sh)
	acmeSuccess, acmeOutput := RunRemoteSimple(vpsCfg, "$HOME/.acme.sh/acme.sh --list")
	if acmeSuccess && strings.Contains(acmeOutput, "Main_Domain") {
		// Очистка вывода от мусора SSH ("Warning: Permanently added...")
		lines := strings.Split(acmeOutput, "\n")
		var certs []map[string]interface{}
		for _, line := range lines {
			line = strings.TrimSpace(line)
			if line == "" || strings.Contains(line, "Main_Domain") || strings.Contains(line, "Warning:") {
				continue
			}
			f := strings.Fields(line)
			// Проверка: минимум 4 поля, домен должен содержать точку и не быть в кавычках (фильтр "ec-256")
			if len(f) >= 4 && strings.Contains(f[0], ".") && !strings.HasPrefix(f[0], "\"") {
				cert := make(map[string]interface{})
				domain := f[0]
				isIP := regexp.MustCompile(`^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$`).MatchString(domain)
				
				label := domain
				if isIP {
					label += " [IP SSL]"
				}
				cert["domains"] = label
				
				// [v1.6.3-go] Двойной контроль: Renew (acme.sh) и Expiry (openssl)
				var renewDate time.Time
				var expiryDate time.Time
				
				// 1. Получаем дату продления (Renew) из acme.sh --list
				rt, rerr := time.Parse("2006-01-02T15:04:05Z", f[len(f)-1])
				if rerr == nil {
					renewDate = rt
				} else if len(f) >= 6 {
					rDateStr := strings.Join(f[len(f)-6:], " ")
					rt2, rerr2 := time.Parse("Mon Jan _2 15:04:05 MST 2006", rDateStr)
					if rerr2 == nil {
						renewDate = rt2
					}
				}

				// 2. Получаем РЕАЛЬНУЮ дату истечения (Expiry) через openssl на VPS
				crtPath := fmt.Sprintf("/etc/nginx/ssl/%s.crt", domain)
				checkCmd := fmt.Sprintf("openssl x509 -enddate -noout -in %s", crtPath)
				_, out := RunRemoteSimple(vpsCfg, checkCmd)
				// Output format: notAfter=Jun 21 16:11:01 2026 GMT
				if strings.Contains(out, "notAfter=") {
					rawDate := strings.TrimSpace(strings.Split(out, "=")[1])
					// OpenSSL date format: "Jan  2 15:04:05 2006 GMT"
					et, eerr := time.Parse("Jan _2 15:04:05 2006 MST", rawDate)
					if eerr == nil {
						expiryDate = et
					}
				}

				// Форматируем вывод
				if !expiryDate.IsZero() {
					cert["expiry"] = expiryDate.Format("02.01.2006 15:04")
					diff := time.Until(expiryDate)
					cert["days"] = int(diff.Hours() / 24)
				} else {
					cert["expiry"] = "Не найдено"
					cert["days"] = 0
				}

				if !renewDate.IsZero() {
					cert["renew"] = renewDate.Format("02.01.2006 15:04")
				} else {
					cert["renew"] = "Не запланировано"
				}
				
				certs = append(certs, cert)
			}
		}
		results["certs"] = certs
	}

	return results
}

// SetupSSHWithPassword настраивает доступ по ключу с использованием временного пароля через встроенный Go SSH-клиент
func SetupSSHWithPassword(vpsName string, vpsCfg map[string]string, password string) (bool, string) {
	// 1. Гарантируем наличие SSH-ключа
	EnsureSSHKey()
	pubKeyPath := SSHKeyPath + ".pub"
	keyData, err := os.ReadFile(pubKeyPath)
	if err != nil {
		return false, "Не удалось прочитать локальный публичный ключ: " + err.Error()
	}
	pubKeyStr := strings.TrimSpace(string(keyData))

	// 2. Параметры подключения
	host := vpsCfg["VPS_HOST"]
	user := vpsCfg["VPS_USER"]
	if user == "" {
		user = "root"
	}
	port := vpsCfg["VPS_PORT"]
	if port == "" {
		port = "22"
	}

	config := &ssh.ClientConfig{
		User: user,
		Auth: []ssh.AuthMethod{
			ssh.Password(password),
		},
		HostKeyCallback: ssh.InsecureIgnoreHostKey(),
		Timeout:         15 * time.Second,
	}

	addr := fmt.Sprintf("%s:%s", host, port)
	client, err := ssh.Dial("tcp", addr, config)
	if err != nil {
		return false, "Ошибка подключения по SSH: " + err.Error()
	}
	defer client.Close()

	session, err := client.NewSession()
	if err != nil {
		return false, "Ошибка создания SSH-сессии: " + err.Error()
	}
	defer session.Close()

	// 3. Настройка .ssh и authorized_keys на удаленном сервере
	// Команда для записи публичного ключа
	setupCmd := fmt.Sprintf(`mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "%s" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys`, pubKeyStr)
	err = session.Run(setupCmd)
	if err != nil {
		return false, "Ошибка при настройке authorized_keys на VPS: " + err.Error()
	}

	// 4. Продолжаем стандартную настройку VPS (Nginx, SSL и т.д.) через ранее созданную функцию SetupVPS
	return SetupVPS(vpsCfg)
}
