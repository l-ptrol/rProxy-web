package core

import (
	"bytes"
	"crypto/md5"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/cookiejar"
	"time"
	"os/exec"
	"regexp"
	"strings"
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

	if routerIP == "" || routerIP == "auto" || routerIP == "127.0.0.1" {
		routerIP = DetectRouterIP()
	}

	// Если в IP нет порта, попробуем добавить :80 или прозондировать
	if !strings.Contains(routerIP, ":") {
		// Простой зонд: если на 80 порту не 401, пробуем 81
		testURL := fmt.Sprintf("http://%s/auth", routerIP)
		resp, err := client.Get(testURL)
		if err != nil || resp.StatusCode != 401 {
			if err == nil { resp.Body.Close() }
			// Пробуем 81
			testURL81 := fmt.Sprintf("http://%s:81/auth", routerIP)
			resp81, err81 := client.Get(testURL81)
			if err81 == nil {
				resp81.Body.Close()
				if resp81.StatusCode == 401 {
					routerIP = routerIP + ":81"
				}
			}
		} else {
			resp.Body.Close()
		}
	}

	authURL := fmt.Sprintf("http://%s/auth", routerIP)
	fmt.Printf("[AUTH] Probing NDM at: %s\n", authURL)
	
	// Шаг 1: GET запрос для получения Challenge и Realm
	reqGet, _ := http.NewRequest("GET", authURL, nil)
	respGet, err := client.Do(reqGet)
	if err != nil {
		return false, fmt.Errorf("ошибка связи с роутером (%s): %v", routerIP, err)
	}
	respGet.Body.Close()

	challenge := respGet.Header.Get("X-NDM-Challenge")
	realm := respGet.Header.Get("X-NDM-Realm")

	if challenge == "" {
		// Попытка вытащить из Www-Authenticate
		authHeader := respGet.Header.Get("Www-Authenticate")
		fmt.Sscanf(authHeader, `x-ndw2-interactive realm="%s" challenge="%s"`, &realm, &challenge)
		// Убираем кавычки из realm если они захватились
		if len(realm) > 0 && realm[len(realm)-1] == '"' {
			realm = realm[:len(realm)-1]
		}
	}

	if challenge == "" {
		return false, fmt.Errorf("не удалось получить X-NDM-Challenge")
	}
	if realm == "" {
		realm = "Keenetic" // Дефолт, если вдруг не отдался
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
	reqPost.Header.Set("Origin", fmt.Sprintf("http://%s", routerIP))
	reqPost.Header.Set("Referer", fmt.Sprintf("http://%s/auth", routerIP))
	
	respPost, err := client.Do(reqPost)
	if err != nil {
		return false, fmt.Errorf("ошибка POST-авторизации: %v", err)
	}
	respPost.Body.Close()

	if respPost.StatusCode == http.StatusOK {
		return true, nil
	}

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
				resp, err := client.Get(fmt.Sprintf("http://%s:%s/auth", gw, p))
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
		resp, err := client.Get(fmt.Sprintf("http://127.0.0.1:%s/auth", p))
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
			resp, err := client.Get(fmt.Sprintf("http://%s:%s/auth", ip, p))
			if err == nil {
				resp.Body.Close()
				if resp.StatusCode == 401 {
					return ip + ":" + p
				}
			}
		}
	}

	return "127.0.0.1"
}
