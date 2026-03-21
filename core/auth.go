package core

import (
	"bytes"
	"crypto/md5"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"os/exec"
	"regexp"
	"strings"
	"time"
)

func md5Hex(data string) string {
	h := md5.Sum([]byte(data))
	return fmt.Sprintf("%x", h)
}

func sha256Hex(data string) string {
	h := sha256.Sum256([]byte(data))
	return fmt.Sprintf("%x", h)
}

// KeeneticAuth выполняет аутентификацию через API роутера Keenetic
// Использует алгоритм X-NDM-Challenge (MD5 + SHA256)
func KeeneticAuth(routerIP, login, password string) (bool, error) {
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:     jar,
		Timeout: 5 * time.Second,
	}

	fmt.Printf("[AUTH] Start: routerIP=%q, login=%q\n", routerIP, login)

	// Определяем IP если авто или 127.0.0.1 (который часто не работает для NDM)
	if routerIP == "" || routerIP == "auto" || routerIP == "127.0.0.1" {
		routerIP = DetectRouterIP()
	}

	// Гарантируем наличие порта
	if !strings.Contains(routerIP, ":") {
		routerIP = routerIP + ":80"
	}

	authURL := fmt.Sprintf("http://%s/auth", routerIP)
	fmt.Printf("[AUTH] Using URL: %s\n", authURL)

	// Шаг 1: GET запрос для получения Challenge и Realm
	reqGet, _ := http.NewRequest("GET", authURL, nil)
	respGet, err := client.Do(reqGet)
	if err != nil {
		return false, fmt.Errorf("ошибка связи с роутером (%s): %v", routerIP, err)
	}
	defer respGet.Body.Close()

	challenge := respGet.Header.Get("X-NDM-Challenge")
	realm := respGet.Header.Get("X-NDM-Realm")

	if challenge == "" {
		// Попытка вытащить из Www-Authenticate
		authHeader := respGet.Header.Get("Www-Authenticate")
		if strings.Contains(authHeader, "challenge=") {
			re := regexp.MustCompile(`realm="([^"]*)"`)
			rm := re.FindStringSubmatch(authHeader)
			if len(rm) > 1 {
				realm = rm[1]
			}
			re2 := regexp.MustCompile(`challenge="([^"]*)"`)
			cm := re2.FindStringSubmatch(authHeader)
			if len(cm) > 1 {
				challenge = cm[1]
			}
		}
	}

	if challenge == "" {
		return false, fmt.Errorf("не удалось получить X-NDM-Challenge (status=%d)", respGet.StatusCode)
	}
	if realm == "" {
		realm = "Keenetic"
	}

	// Шаг 2: Расчет хэшей
	s1 := login + ":" + realm + ":" + password
	h1 := md5Hex(s1)
	finalHash := sha256Hex(challenge + h1)

	// Шаг 3: POST запрос
	payload := map[string]string{
		"login":    login,
		"password": finalHash,
	}
	jsonData, _ := json.Marshal(payload)

	reqPost, _ := http.NewRequest("POST", authURL, bytes.NewBuffer(jsonData))
	reqPost.Header.Set("Content-Type", "application/json")
	// Важные заголовки для предотвращения CSRF-блока
	reqPost.Header.Set("Origin", fmt.Sprintf("http://%s", routerIP))
	reqPost.Header.Set("Referer", fmt.Sprintf("http://%s/auth", routerIP))

	respPost, err := client.Do(reqPost)
	if err != nil {
		return false, fmt.Errorf("ошибка POST-авторизации: %v", err)
	}
	defer respPost.Body.Close()

	if respPost.StatusCode == http.StatusOK {
		fmt.Printf("[AUTH] SUCCESS: Access granted for %s\n", login)
		return true, nil
	}

	fmt.Printf("[AUTH] FAILED: status=%d\n", respPost.StatusCode)
	return false, nil
}

// DetectRouterIP пытается автоматически найти IP роутера
func DetectRouterIP() string {
	client := http.Client{Timeout: 1 * time.Second}
	ports := []string{"80", "81", "8080"}

	// 1. Пробуем найти через ip route (самый надежный способ для Keenetic/Entware)
	out, err := exec.Command("ip", "route", "show", "default").Output()
	if err == nil {
		re := regexp.MustCompile(`via\s+([0-9.]+)`)
		match := re.FindStringSubmatch(string(out))
		if len(match) > 1 {
			gw := match[1]
			for _, p := range ports {
				url := fmt.Sprintf("http://%s:%s/auth", gw, p)
				resp, err := client.Get(url)
				if err == nil {
					resp.Body.Close()
					if resp.StatusCode == 401 {
						return gw + ":" + p
					}
				}
			}
		}
	}

	// 2. Пробуем 127.0.0.1 (запасной вариант)
	for _, p := range ports {
		url := fmt.Sprintf("http://127.0.0.1:%s/auth", p)
		resp, err := client.Get(url)
		if err == nil {
			resp.Body.Close()
			if resp.StatusCode == 401 {
				return "127.0.0.1:" + p
			}
		}
	}

	// 3. Крайний случай - стандартные IP
	defaults := []string{"192.168.1.1", "192.168.0.1", "192.168.10.1", "192.168.60.1"}
	for _, ip := range defaults {
		for _, p := range ports {
			url := fmt.Sprintf("http://%s:%s/auth", ip, p)
			resp, err := client.Get(url)
			if err == nil {
				resp.Body.Close()
				if resp.StatusCode == 401 {
					return ip + ":" + p
				}
			}
		}
	}

	return "192.168.1.1"
}
