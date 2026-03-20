package core

import (
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"
)

// Цвета ANSI для терминала
const (
	RED    = "\033[0;31m"
	GREEN  = "\033[0;32m"
	YELLOW = "\033[1;33m"
	CYAN   = "\033[0;36m"
	BOLD   = "\033[1m"
	DIM    = "\033[2m"
	NC     = "\033[0m"
)

// Версия приложения
const VERSION = "1.0.10-go"

// logHookPath — путь к файлу для лог-хука (запись при деплое из веба)
var logHookPath string

// SetLogHook устанавливает лог-хук: все Msg/Warn/Err будут писать в файл
func SetLogHook(path string) {
	logHookPath = path
}

// ClearLogHook снимает лог-хук
func ClearLogHook() {
	logHookPath = ""
}

// writeToHook записывает текст в файл лог-хука (без ANSI-кодов)
func writeToHook(text string) {
	if logHookPath == "" {
		return
	}
	// Удаляем ANSI-коды
	re := regexp.MustCompile(`\x1B\[[0-9;]*[a-zA-Z]`)
	clean := re.ReplaceAllString(text, "")

	f, err := os.OpenFile(logHookPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	fmt.Fprintln(f, clean)
}

// Msg выводит информационное сообщение
func Msg(text string) {
	fmt.Printf("%s▸%s %s\n", GREEN, NC, text)
	writeToHook("▸ " + text)
}

// Warn выводит предупреждение
func Warn(text string) {
	fmt.Printf("%s⚠%s %s\n", YELLOW, NC, text)
	writeToHook("⚠ " + text)
}

// Err выводит ошибку
func Err(text string) {
	fmt.Fprintf(os.Stderr, "%s✖%s %s\n", RED, NC, text)
	writeToHook("✖ " + text)
}

// Header выводит заголовок секции
func Header(text string) {
	fmt.Printf("\n%s%s%s%s\n", CYAN, BOLD, text, NC)
}

// DrawSeparator рисует разделитель
func DrawSeparator() {
	fmt.Printf("%s──────────────────────────────────────────────────%s\n", DIM, NC)
}

// Pause ожидает нажатия Enter
func Pause() {
	fmt.Printf("\n%sНажмите Enter, чтобы продолжить...%s", BOLD, NC)
	fmt.Scanln()
}

// ResolveBin находит абсолютный путь к бинарнику (приоритет Entware)
func ResolveBin(name string) string {
	paths := []string{"/opt/bin", "/opt/sbin", "/usr/bin", "/usr/sbin", "/bin", "/sbin"}
	for _, p := range paths {
		full := filepath.Join(p, name)
		if _, err := os.Stat(full); err == nil {
			return full
		}
	}
	return name
}

// GetSSHType определяет тип SSH клиента (openssh или dropbear)
func GetSSHType(binPath string) string {
	// Проверяем через -V
	out, err := exec.Command(binPath, "-V").CombinedOutput()
	if err == nil || out != nil {
		combined := string(out)
		if strings.Contains(combined, "Dropbear") || strings.Contains(combined, "dbclient") {
			return "dropbear"
		}
	}

	// Проверяем через -h
	out, err = exec.Command(binPath, "-h").CombinedOutput()
	if err == nil || out != nil {
		combined := string(out)
		if strings.Contains(combined, "Dropbear") || strings.Contains(combined, "dbclient") {
			return "dropbear"
		}
	}

	return "openssh"
}

// GetSSHArgs формирует аргументы SSH в зависимости от типа клиента
func GetSSHArgs(binPath, host, user, port, keyPath string, isSCP bool) []string {
	sshType := GetSSHType(binPath)
	var args []string

	if sshType == "dropbear" {
		args = append(args, "-y") // Принять ключ хоста
		if keyPath != "" {
			args = append(args, "-i", keyPath)
		}
		if isSCP {
			args = append(args, "-P", port)
		} else {
			args = append(args, "-p", port)
		}
	} else {
		// OpenSSH
		args = append(args,
			"-o", "StrictHostKeyChecking=no",
			"-o", "UserKnownHostsFile=/dev/null",
		)
		if keyPath != "" {
			args = append(args, "-o", "BatchMode=yes")
		} else {
			args = append(args, "-o", "BatchMode=no", "-o", "PasswordAuthentication=yes")
		}
		args = append(args, "-o", "ConnectTimeout=15")

		if keyPath != "" {
			args = append(args, "-i", keyPath)
		}
		if isSCP {
			args = append(args, "-P", port)
		} else {
			args = append(args, "-p", port)
		}
	}

	return args
}

// GenHtpasswd генерирует строку htpasswd через openssl
func GenHtpasswd(user, password string) string {
	out, err := exec.Command("openssl", "passwd", "-apr1", password).Output()
	if err == nil {
		hash := strings.TrimSpace(string(out))
		return fmt.Sprintf("%s:%s", user, hash)
	}
	// Фоллбэк — plaintext (nginx может не принять)
	return fmt.Sprintf("%s:%s", user, password)
}

// GetRouterIP определяет IP роутера
func GetRouterIP() string {
	// 1. ndmq (Keenetic)
	out, err := exec.Command("ndmq", "-p", "show interface Bridge0", "-path", "address").Output()
	if err == nil {
		ip := strings.TrimSpace(string(out))
		if ip != "" && ip != "0.0.0.0" {
			return ip
		}
	}

	// 2. ip route
	out, err = exec.Command("ip", "route", "show").Output()
	if err == nil {
		for _, line := range strings.Split(string(out), "\n") {
			if strings.Contains(line, "default via") {
				parts := strings.Fields(line)
				if len(parts) > 2 {
					return parts[2]
				}
			}
		}
	}

	return "192.168.1.1"
}

// IsPortBusy проверяет, занят ли TCP порт на localhost
func IsPortBusy(port int) bool {
	conn, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", port), 500*time.Millisecond)
	if err != nil {
		return false
	}
	conn.Close()
	return true
}

// GetDomainIP получает IP-адрес по доменному имени
func GetDomainIP(domain string) string {
	ips, err := net.LookupHost(domain)
	if err != nil || len(ips) == 0 {
		return ""
	}
	return ips[0]
}

// GetProcessEnv возвращает окружение с путями Entware и библиотеками
func GetProcessEnv() []string {
	env := os.Environ()
	envMap := make(map[string]string)

	for _, e := range env {
		parts := strings.SplitN(e, "=", 2)
		if len(parts) == 2 {
			envMap[parts[0]] = parts[1]
		}
	}

	// Добавляем пути Entware
	entwarePaths := "/opt/bin:/opt/sbin:/bin:/usr/bin"
	currentPath := envMap["PATH"]
	if !strings.Contains(currentPath, "/opt/bin") {
		envMap["PATH"] = entwarePaths + ":" + currentPath
	}

	// Пути к библиотекам Entware
	envMap["LD_LIBRARY_PATH"] = "/opt/lib:/opt/usr/lib:/lib:/usr/lib"
	envMap["TERMINFO"] = "/opt/share/terminfo"
	envMap["TERMINFO_DIRS"] = "/opt/share/terminfo:/etc/terminfo:/usr/share/terminfo"

	if envMap["HOME"] == "" {
		envMap["HOME"] = "/opt/root"
	}
	if envMap["TERM"] == "" {
		envMap["TERM"] = "xterm-256color"
	}

	// Собираем обратно в слайс
	result := make([]string, 0, len(envMap))
	for k, v := range envMap {
		result = append(result, k+"="+v)
	}
	return result
}
