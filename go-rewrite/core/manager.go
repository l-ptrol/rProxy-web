package core

import (
	"fmt"
	"math/rand"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"syscall"
	"time"
)

// Директории для PID-файлов и логов
const (
	PIDDir = "/opt/var/run/rproxy"
	LogDir = "/opt/var/log"
)

// ServicesDir — директория конфигов сервисов
var ServicesDir = filepath.Join(RProxyRoot, "services")

// IsRunning проверяет, запущен ли сервис по PID-файлу
func IsRunning(name string) bool {
	pidFile := filepath.Join(PIDDir, name+".pid")

	data, err := os.ReadFile(pidFile)
	if err != nil {
		return false
	}

	pidStr := strings.TrimSpace(string(data))
	if pidStr == "" {
		return false
	}

	pid, err := strconv.Atoi(pidStr)
	if err != nil {
		os.Remove(pidFile)
		return false
	}

	// Проверяем существование процесса через сигнал 0
	process, err := os.FindProcess(pid)
	if err != nil {
		os.Remove(pidFile)
		return false
	}

	// На Linux kill(pid, 0) проверяет существование процесса
	err = process.Signal(os.Signal(nil))
	if err != nil {
		// Попробуем через /proc
		if _, err := os.Stat(fmt.Sprintf("/proc/%d", pid)); os.IsNotExist(err) {
			os.Remove(pidFile)
			return false
		}
	}

	return true
}

// StartService — комплексный запуск сервиса: SSL, Auth, Nginx и Туннель
func StartService(svcCfg, vpsCfg map[string]string) bool {
	name := svcCfg["SVC_NAME"]
	if IsRunning(name) {
		Msg(fmt.Sprintf("Сервис '%s' уже запущен.", name))
		return true
	}

	os.MkdirAll(PIDDir, 0755)
	os.MkdirAll(LogDir, 0755)

	// 0. ПРЕДВАРИТЕЛЬНАЯ ОЧИСТКА
	Msg(fmt.Sprintf("Подготовка окружения для '%s'...", name))
	StopService(name, svcCfg)

	// Очистка старых конфигов Nginx на VPS
	cleanupCmd := fmt.Sprintf("rm -f /etc/nginx/sites-enabled/rproxy_%s.conf /etc/nginx/streams-enabled/rproxy_%s.conf && (nginx -t && systemctl reload nginx || true)", name, name)
	RunRemoteSimple(vpsCfg, cleanupCmd)

	// 1. ОБРАБОТКА BASIC AUTH
	authUser := svcCfg["SVC_AUTH_USER"]
	authPass := svcCfg["SVC_AUTH_PASS"]
	if authUser != "" && authPass != "" {
		Msg(fmt.Sprintf("Генерация доступа для %s...", authUser))
		htContent := GenHtpasswd(authUser, authPass)
		success, errMsg := UploadContent(vpsCfg, htContent+"\n", fmt.Sprintf("/etc/nginx/rproxy_%s.htpasswd", name))
		if success {
			RunRemoteSimple(vpsCfg, fmt.Sprintf("chmod 644 /etc/nginx/rproxy_%s.htpasswd", name))
		} else {
			Warn(fmt.Sprintf("Не удалось загрузить файл авторизации: %s", errMsg))
		}
	}

	// 2. ОБРАБОТКА SSL (CERTBOT)
	domain := svcCfg["SVC_DOMAIN"]
	useSSL := svcCfg["SVC_SSL"] == "yes"
	hasCertificate := false

	if useSSL && domain != "" {
		if CheckSSLExists(vpsCfg, domain) {
			hasCertificate = true
			Msg(fmt.Sprintf("✅ Сертификат для %s уже существует. Пропускаю перевыпуск.", domain))
		} else {
			// Проверка DNS
			vpsIP := vpsCfg["VPS_HOST"]
			domainIP := GetDomainIP(domain)

			if domainIP != "" && domainIP != vpsIP {
				Warn(fmt.Sprintf("ВНИМАНИЕ! Домен '%s' указывает на IP %s,", domain, domainIP))
				Warn(fmt.Sprintf("но ваш текущий VPS имеет IP %s.", vpsIP))
				Warn("Certbot НЕ СМОЖЕТ выпустить сертификат, пока DNS не обновится.")
			}

			Msg("Выпуск нового сертификата через Certbot...")
			// Сначала деплоим базовый конфиг для валидации
			vContent := CertbotValidationVhost(domain)
			DeployVhost(vpsCfg, name, vContent, "")
			success, output := RunCertbot(vpsCfg, domain)
			if success {
				hasCertificate = true
			} else {
				Warn(fmt.Sprintf("Certbot не смог выпустить сертификат: %s", output))
			}
		}
	}

	// 3. ПОДГОТОВКА ПАРАМЕТРОВ
	nginxPath := GetNginxPath(svcCfg["SVC_TYPE"])

	// 4. ЗАПУСК TTYD (если нужно)
	targetHost := svcCfg["SVC_TARGET_HOST"]
	if targetHost == "" {
		targetHost = "127.0.0.1"
	}
	targetPort := svcCfg["SVC_TARGET_PORT"]
	if targetPort == "" {
		targetPort = "80"
	}

	if svcCfg["SVC_TYPE"] == "ttyd" {
		ttydPort := svcCfg["SVC_TARGET_PORT"]
		if ttydPort == "" {
			ttydPort = "7682"
		}
		ttydCmd := svcCfg["SVC_TTYD_CMD"]
		if ttydCmd == "" {
			ttydCmd = "login"
		}
		ok, actualPort := StartTTYD(ttydPort, ttydCmd, name)
		if ok {
			targetHost = "127.0.0.1"
			targetPort = actualPort
			// Если порт изменился, сохраняем его в конфиг для будущих запусков
			if actualPort != svcCfg["SVC_TARGET_PORT"] {
				svcCfg["SVC_TARGET_PORT"] = actualPort
				SaveConfig(filepath.Join(ServicesDir, name+".conf"), svcCfg)
			}
		} else {
			logPath := filepath.Join(LogDir, fmt.Sprintf("ttyd_%s.log", name))
			Err(fmt.Sprintf("Не удалось запустить ttyd. Подробности см. в логе: %s", logPath))
			return false
		}
	}

	// 5. ЗАПУСК ТУННЕЛЯ (AUTOSSH)
	remoteTunnelPort := svcCfg["SVC_TUNNEL_PORT"]
	vpsHost := vpsCfg["VPS_HOST"]
	vpsUser := vpsCfg["VPS_USER"]
	if vpsUser == "" {
		vpsUser = "root"
	}
	vpsPort := vpsCfg["VPS_PORT"]
	if vpsPort == "" {
		vpsPort = "22"
	}
	sshKey := SSHKeyPath

	monPort := rand.Intn(1000) + 20000

	// 5.1 СПЕЦИФИКАЦИЯ ТУННЕЛЯ
	var tunnelSpec string
	svcType := svcCfg["SVC_TYPE"]
	switch {
	case svcType == "udp":
		tunnelSpec = fmt.Sprintf("%s:127.0.0.1:%s", remoteTunnelPort, remoteTunnelPort)
	case svcType == "http" || svcType == "ttyd":
		tunnelSpec = fmt.Sprintf("%s:%s:%s", remoteTunnelPort, targetHost, targetPort)
	default:
		tunnelSpec = fmt.Sprintf("0.0.0.0:%s:%s:%s", remoteTunnelPort, targetHost, targetPort)
	}

	// Настройка окружения
	env := GetProcessEnv()
	// Добавляем переменные AUTOSSH
	env = append(env,
		"AUTOSSH_GATETIME=0",
	)

	sshBin := "/opt/bin/ssh"
	if _, err := os.Stat(sshBin); os.IsNotExist(err) {
		sshBin = "ssh"
	}
	env = append(env,
		"AUTOSSH_PATH="+sshBin,
		"AUTOSSH_LOGFILE="+filepath.Join(LogDir, fmt.Sprintf("autossh_%s.log", name)),
	)

	logPath := filepath.Join(LogDir, fmt.Sprintf("tunnel_%s.log", name))

	autosshBin := "/opt/bin/autossh"
	if _, err := os.Stat(autosshBin); os.IsNotExist(err) {
		autosshBin = "autossh"
	}

	cmdArgs := []string{
		"-M", strconv.Itoa(monPort), "-f", "-N",
		"-o", "ConnectTimeout=10",
		"-o", "ServerAliveInterval=30",
		"-o", "ServerAliveCountMax=3",
		"-o", "ExitOnForwardFailure=yes",
		"-o", "StrictHostKeyChecking=no",
		"-o", "UserKnownHostsFile=/dev/null",
		"-o", "BatchMode=yes",
		"-E", logPath,
		"-i", sshKey,
		"-p", vpsPort,
		"-R", tunnelSpec,
		fmt.Sprintf("%s@%s", vpsUser, vpsHost),
	}

	Msg(fmt.Sprintf("Запуск туннеля '%s' (Target: %s:%s)...", name, targetHost, targetPort))

	cmd := exec.Command(autosshBin, cmdArgs...)
	cmd.Env = env
	if err := cmd.Run(); err != nil {
		Err(fmt.Sprintf("Ошибка при запуске туннеля '%s': %v", name, err))
		return false
	}

	// Даем время на инициализацию
	time.Sleep(2 * time.Second)

	// Ищем PID нового процесса
	pgrepBin := ResolveBin("pgrep")
	pgrepCmd := exec.Command(pgrepBin, "-f", fmt.Sprintf("autossh.*-M %d", monPort))
	pgrepCmd.Env = env
	pgrepOut, err := pgrepCmd.Output()

	var pid string
	if err == nil {
		lines := strings.Split(strings.TrimSpace(string(pgrepOut)), "\n")
		if len(lines) > 0 {
			pid = lines[0]
		}
	}

	if pid != "" {
		// Сохраняем PID
		os.WriteFile(filepath.Join(PIDDir, name+".pid"), []byte(pid), 0644)

		Msg(fmt.Sprintf("Туннель '%s' запущен (PID: %s). Ожидание сетевой готовности...", name, pid))
		time.Sleep(3 * time.Second)

		// 6. ДЕПЛОЙ NGINX / UDP BRIDGE
		if svcType == "udp" {
			startUDPBridge(name, svcCfg, vpsCfg, remoteTunnelPort, env)
		} else {
			useSSLFinal := hasCertificate && useSSL
			Msg(fmt.Sprintf("Применение конфигурации Nginx (SSL: %v)...", useSSLFinal))
			nginxConf := GenerateNginxConf(svcCfg, useSSLFinal)

			success, output := DeployVhost(vpsCfg, name, nginxConf, nginxPath)
			if !success {
				Warn(fmt.Sprintf("Nginx reload warning: %s", output))
			}
		}

		Msg(fmt.Sprintf("Туннель '%s' запущен %s(PID: %s, MonPort: %d)%s", name, DIM, pid, monPort, NC))
		Msg(fmt.Sprintf("Сервис '%s' успешно проброшен!", name))
		return true
	}

	Err(fmt.Sprintf("Туннель '%s' не запустился за 20 сек.", name))
	return false
}

// startUDPBridge запускает мост UDP-TCP через socat
func startUDPBridge(name string, svcCfg, vpsCfg map[string]string, remoteTunnelPort string, env []string) {
	Msg("Подготовка UDP-TCP моста...")

	extPort := svcCfg["SVC_EXT_PORT"]
	targetHost := svcCfg["SVC_TARGET_HOST"]
	if targetHost == "" {
		targetHost = "127.0.0.1"
	}
	targetPort := svcCfg["SVC_TARGET_PORT"]

	// 1. Проверка socat на VPS
	Msg("Проверка socat на VPS...")
	sSoc, _ := RunRemoteSimple(vpsCfg, "which socat")
	if !sSoc {
		Warn("socat не найден на VPS. Установка...")
		RunRemote(vpsCfg, "apt-get update && apt-get install -y socat || yum install -y socat", 300*time.Second)
		sSoc, _ = RunRemoteSimple(vpsCfg, "which socat")
		if !sSoc {
			Err("НЕ УДАЛОСЬ установить socat на VPS!")
			return
		}
	}

	// 2. Запуск на VPS (UDP -> TCP)
	logVPS := fmt.Sprintf("/tmp/rproxy_socat_%s.vps.log", name)
	socatCmdVPS := fmt.Sprintf("touch %s && nohup socat UDP4-LISTEN:%s,fork,reuseaddr TCP4:127.0.0.1:%s >> %s 2>&1 &", logVPS, extPort, remoteTunnelPort, logVPS)
	Msg(fmt.Sprintf("Запуск socat на VPS (UDP:%s -> TCP:%s)...", extPort, remoteTunnelPort))
	RunRemoteSimple(vpsCfg, fmt.Sprintf("pkill -f 'UDP4-LISTEN:%s' || true", extPort))
	time.Sleep(1 * time.Second)
	RunRemoteSimple(vpsCfg, socatCmdVPS)

	// 3. Запуск на Роутере (TCP -> UDP)
	Msg("Запуск socat на роутере...")
	socatPathRouter := "/opt/bin/socat"
	if _, err := os.Stat(socatPathRouter); os.IsNotExist(err) {
		socatPathRouter = "socat"
	}

	pkillBin := ResolveBin("pkill")
	exec.Command(pkillBin, "-f", fmt.Sprintf("TCP4-LISTEN:%s", remoteTunnelPort)).Run()
	time.Sleep(1 * time.Second)

	logRouter := fmt.Sprintf("/tmp/rproxy_socat_%s.router.log", name)
	logFile, err := os.Create(logRouter)
	if err != nil {
		Err(fmt.Sprintf("Не удалось создать лог: %v", err))
		return
	}

	socArgs := []string{
		fmt.Sprintf("TCP4-LISTEN:%s,fork,reuseaddr", remoteTunnelPort),
		fmt.Sprintf("UDP4-DATAGRAM:%s:%s", targetHost, targetPort),
	}

	cmd := exec.Command(socatPathRouter, socArgs...)
	cmd.Env = env
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	if err := cmd.Start(); err != nil {
		Err(fmt.Sprintf("Не удалось запустить socat: %v", err))
		return
	}

	Msg(fmt.Sprintf("%sПроцесс socat инициирован.%s", GREEN, NC))

	// Проверка запуска
	time.Sleep(2 * time.Second)
	pgrepBin := ResolveBin("pgrep")
	pgResult := exec.Command(pgrepBin, "-f", fmt.Sprintf("TCP4-LISTEN:%s", remoteTunnelPort))
	pgResult.Env = env
	if pgResult.Run() == nil {
		Msg(fmt.Sprintf("%sМост на роутере успешно запущен.%s", GREEN, NC))
	} else {
		Warn(fmt.Sprintf("Мост на роутере не отвечает. Проверьте лог: %s", logRouter))
	}
}

// StopService — остановка сервиса и очистка ресурсов
func StopService(name string, svcCfg map[string]string) {
	// 1. Останавливаем туннель
	pidFile := filepath.Join(PIDDir, name+".pid")
	if data, err := os.ReadFile(pidFile); err == nil {
		pidStr := strings.TrimSpace(string(data))
		if pid, err := strconv.Atoi(pidStr); err == nil {
			if process, err := os.FindProcess(pid); err == nil {
				process.Signal(os.Interrupt) // SIGTERM
				time.Sleep(1 * time.Second)
				if IsRunning(name) {
					process.Kill() // SIGKILL
				}
			}
		}
		os.Remove(pidFile)
	}

	// 2. TTYD
	if svcCfg != nil {
		ttydPort := svcCfg["SVC_TTYD_PORT"]
		if ttydPort == "" {
			ttydPort = "7682"
		}
		StopTTYD(ttydPort)

		// 3. SOCAT (UDP мост)
		if svcCfg["SVC_TYPE"] == "udp" {
			extPort := svcCfg["SVC_EXT_PORT"]
			tunPort := svcCfg["SVC_TUNNEL_PORT"]
			vID := svcCfg["SVC_VPS"]
			vPath := filepath.Join(VPSDir, vID+".conf")
			if _, err := os.Stat(vPath); err == nil {
				vCfg := LoadConfig(vPath)
				RunRemoteSimple(vCfg, fmt.Sprintf("pkill -f 'UDP4-LISTEN:%s'", extPort))
			}
			pkillBin := ResolveBin("pkill")
			cmd := exec.Command(pkillBin, "-f", fmt.Sprintf("TCP4-LISTEN:%s", tunPort))
			cmd.Env = GetProcessEnv()
			cmd.Run()
		}
	} else {
		StopTTYD("7682")
	}

	Msg(fmt.Sprintf("Сервис '%s' остановлен.", name))
}

// StartTTYD запускает ttyd с Watchdog-скриптом
// StartTTYD — запуск ttyd терминала. Возвращает успех и реально использованный порт.
func StartTTYD(requestedPort, command, name string) (bool, string) {
	port := requestedPort
	pInt, _ := strconv.Atoi(port)

	// Автоподбор порта если занят
	for i := 0; i < 100; i++ {
		if !IsPortBusy(pInt) {
			port = strconv.Itoa(pInt)
			break
		}
		pInt++
	}

	StopTTYD(port)

	// Агрессивная очистка порта
	fuserBin := ResolveBin("fuser")
	if _, err := os.Stat(fuserBin); err == nil {
		cmd := exec.Command(fuserBin, "-k", port+"/tcp")
		cmd.Env = GetProcessEnv()
		cmd.Run()
	}
	time.Sleep(500 * time.Millisecond)

	// Проверка наличия ttyd
	ttydBin := ResolveBin("ttyd")
	if _, err := exec.LookPath(ttydBin); err != nil {
		Msg("ttyd не найден. Пытаюсь установить через opkg...")
		opkgBin := ResolveBin("opkg")
		exec.Command(opkgBin, "update").Run()
		if err := exec.Command(opkgBin, "install", "ttyd").Run(); err != nil {
			Err("Не удалось установить ttyd. Установите вручную: opkg install ttyd")
			return false, port
		}
		Msg("ttyd успешно установлен.")
	}

	pidFile := filepath.Join(PIDDir, fmt.Sprintf("ttyd_%s.pid", port))
	logFile := filepath.Join(LogDir, fmt.Sprintf("ttyd_%s.log", name))
	watchdogScript := filepath.Join(PIDDir, fmt.Sprintf("ttyd_watchdog_%s.sh", port))

	// Используем переданную команду без жестких путей (ttyd сам найдет через PATH)
	realCmd := command

	Msg(fmt.Sprintf("Запуск ttyd на порту %s [команда: %s]...", port, realCmd))

	ttydPath := ResolveBin("ttyd")

	// Генерируем watchdog-скрипт (в точности как в старой версии)
	scriptContent := fmt.Sprintf(`#!/bin/sh
trap 'exit 0' TERM INT

while true; do
	if [ -x "%s" ]; then
		"%s" -W --max-clients 10 -i 0.0.0.0 -p "%s" -- %s >> "%s" 2>&1
	else
		echo "$(date) Error: ttyd lost during runtime!" >> "%s"
		exit 1
	fi
	
	exit_code=$?
	echo "$(date) ttyd stopped with exit code $exit_code, restarting in 2s..." >> "%s"
	sleep 2
done
`, ttydPath, ttydPath, port, realCmd, logFile, logFile, logFile)

	os.WriteFile(watchdogScript, []byte(scriptContent), 0755)

	// Запускаем watchdog-скрипт независимо
	setsidBin := ResolveBin("setsid")
	var cmd *exec.Cmd
	if _, err := os.Stat(setsidBin); err == nil {
		cmd = exec.Command(setsidBin, "sh", watchdogScript)
	} else {
		cmd = exec.Command("sh", watchdogScript)
		cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	}

	cmd.Env = GetProcessEnv()

	if err := cmd.Start(); err != nil {
		Err(fmt.Sprintf("Ошибка запуска watchdog ttyd: %v", err))
		return false, port
	}

	// Сохраняем PID watchdog'а
	watchdogPid := cmd.Process.Pid
	os.WriteFile(pidFile, []byte(strconv.Itoa(watchdogPid)), 0644)

	// Очищаем процесс зомби (так как мы его не ждем)
	go func() {
		cmd.Wait()
		os.Remove(watchdogScript)
	}()

	// Верификация порта
	Msg("Ожидание готовности порта...")
	portInt, _ := strconv.Atoi(port)
	for i := 1; i <= 10; i++ {
		if IsPortBusy(portInt) {
			Msg(fmt.Sprintf("ttyd успешно запущен на порту %s (Watchdog PID %d)", port, watchdogPid))
			return true, port
		}
		time.Sleep(1 * time.Second)
	}
	
	// Если порт не поднялся - убиваем watchdog
	exec.Command("kill", "-9", strconv.Itoa(watchdogPid)).Run()
	os.Remove(pidFile)
	os.Remove(watchdogScript)
	return false, port
}

// StopTTYD — остановка ttyd по порту
func StopTTYD(port string) {
	pidFile := filepath.Join(PIDDir, fmt.Sprintf("ttyd_%s.pid", port))
	if data, err := os.ReadFile(pidFile); err == nil {
		if pid, err := strconv.Atoi(strings.TrimSpace(string(data))); err == nil {
			if process, err := os.FindProcess(pid); err == nil {
				process.Kill()
			}
		}
		os.Remove(pidFile)
	}

	// Агрессивно прибиваем ttyd на порту и его watchdog
	env := GetProcessEnv()
	pkillBin := ResolveBin("pkill")
	cmd1 := exec.Command(pkillBin, "-9", "-f", fmt.Sprintf("ttyd.*-p %s", port))
	cmd1.Env = env
	cmd1.Run()

	cmd2 := exec.Command(pkillBin, "-9", "-f", fmt.Sprintf("ttyd_watchdog_%s.sh", port))
	cmd2.Env = env
	cmd2.Run()

	fuserBin := ResolveBin("fuser")
	if _, err := os.Stat(fuserBin); err == nil {
		cmd3 := exec.Command(fuserBin, "-k", port+"/tcp")
		cmd3.Env = env
		cmd3.Run()
	}
}

// RedeployNginx — перезапись конфигурации Nginx без остановки туннеля
func RedeployNginx(svcCfg, vpsCfg map[string]string) bool {
	name := svcCfg["SVC_NAME"]
	domain := svcCfg["SVC_DOMAIN"]
	useSSL := svcCfg["SVC_SSL"] == "yes"

	Msg(fmt.Sprintf("Перезапись конфигурации Nginx для '%s'...", name))

	hasCertificate := false
	if useSSL && domain != "" {
		hasCertificate = CheckSSLExists(vpsCfg, domain)
	}

	nginxConf := GenerateNginxConf(svcCfg, hasCertificate)
	nginxPath := GetNginxPath(svcCfg["SVC_TYPE"])

	success, output := DeployVhost(vpsCfg, name, nginxConf, nginxPath)
	if success {
		Msg(fmt.Sprintf("Конфигурация Nginx для '%s' успешно обновлена.", name))
		Msg("Принудительный перезапуск сервиса...")
		StopService(name, nil)
		time.Sleep(1 * time.Second)
		StartService(svcCfg, vpsCfg)
	} else {
		Err(fmt.Sprintf("Ошибка при обновлении Nginx: %s", output))
	}
	return success
}

// RunCertbotForService — ручной запуск Certbot для сервиса
func RunCertbotForService(svcCfg, vpsCfg map[string]string) bool {
	name := svcCfg["SVC_NAME"]
	domain := svcCfg["SVC_DOMAIN"]
	if domain == "" {
		Warn(fmt.Sprintf("Сервис '%s' не имеет домена.", name))
		return false
	}

	Msg(fmt.Sprintf("Запуск Certbot для домена '%s'...", domain))
	success, output := RunCertbot(vpsCfg, domain)
	if success {
		Msg(fmt.Sprintf("Сертификат для '%s' успешно получен.", domain))
		RedeployNginx(svcCfg, vpsCfg)
	} else {
		Err(fmt.Sprintf("Ошибка Certbot: %s", output))
	}
	return success
}

// SelfUpdate — обновление rProxy из GitHub
func SelfUpdate(isWeb bool) {
	url := fmt.Sprintf("https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/install.sh?t=%d", time.Now().Unix())
	logUpd := "/tmp/rproxy_updater.log"

	os.Remove(logUpd)
	os.WriteFile(logUpd, []byte("Загрузка install.sh...\n"), 0644)

	shellCmd := fmt.Sprintf("curl -sL '%s' -o /tmp/rproxy_update.sh && sh /tmp/rproxy_update.sh", url)

	logF, _ := os.Create(logUpd)
	cmd := exec.Command("sh", "-c", shellCmd)
	cmd.Stdout = logF
	cmd.Stderr = logF
	cmd.Start()

	if !isWeb {
		time.Sleep(1 * time.Second)
		os.Exit(0)
	}
}

// HardReset — полная очистка всех конфигураций rProxy
func HardReset() {
	Msg("Выполнение глубокой очистки...")

	env := GetProcessEnv()
	pkillBin := ResolveBin("pkill")

	cmd := exec.Command(pkillBin, "-f", "autossh")
	cmd.Env = env
	cmd.Run()

	cmd = exec.Command(pkillBin, "-f", "ttyd")
	cmd.Env = env
	cmd.Run()

	// Удаляем директории
	paths := []string{"/opt/etc/rproxy", "/opt/var/run/rproxy", "/opt/share/rproxy-web"}
	for _, p := range paths {
		os.RemoveAll(p)
	}

	Msg("Система очищена. Перезапустите инсталлятор для новой настройки.")
	os.Exit(0)
}
