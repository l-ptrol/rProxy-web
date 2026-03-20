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

	fmt.Printf("[AUTH] Input routerIP=%q, login=%q\n", routerIP, login)

	if routerIP == "" || routerIP == "auto" || routerIP == "127.0.0.1" {
		routerIP = DetectRouterIP()
		fmt.Printf("[AUTH] DetectRouterIP returned: %s\n", routerIP)
	}

	// Если в IP нет порта, зондируем
	if !strings.Contains(routerIP, ":") {
		testURL := fmt.Sprintf("http://%s/auth", routerIP)
		resp, err := client.Get(testURL)
		if err != nil || resp.StatusCode != 401 {
			if err == nil {
				fmt.Printf("[AUTH] Probe %s -> status %d (not 401)\n", testURL, resp.StatusCode)
				resp.Body.Close()
			} else {
				fmt.Printf("[AUTH] Probe %s -> error: %v\n", testURL, err)
			}
			// Пробуем :81
			testURL81 := fmt.Sprintf("http://%s:81/auth", routerIP)
			resp81, err81 := client.Get(testURL81)
			if err81 == nil {
				fmt.Printf("[AUTH] Probe %s -> status %d\n", testURL81, resp81.StatusCode)
				resp81.Body.Close()
				if resp81.StatusCode == 401 {
					routerIP = routerIP + ":81"
				}
			} else {
				fmt.Printf("[AUTH] Probe %s -> error: %v\n", testURL81, err81)
			}
		} else {
			fmt.Printf("[AUTH] Probe %s -> status 401 OK\n", testURL)
			resp.Body.Close()
		}
	}

	authURL := fmt.Sprintf("http://%s/auth", routerIP)
	fmt.Printf("[AUTH] Final NDM URL: %s\n", authURL)

	// Шаг 1: GET запрос для получения Challenge и Realm
	reqGet, _ := http.NewRequest("GET", authURL, nil)
	respGet, err := client.Do(reqGet)
	if err != nil {
		return false, fmt.Errorf("ошибка связи с роутером (%s): %v", routerIP, err)
	}
	defer respGet.Body.Close()

	fmt.Printf("[AUTH] GET %s -> status %d\n", authURL, respGet.StatusCode)
	// Логируем ВСЕ заголовки ответа
	for key, vals := range respGet.Header {
		fmt.Printf("[AUTH] Header: %s = %s\n", key, strings.Join(vals, "; "))
	}

	challenge := respGet.Header.Get("X-NDM-Challenge")
	realm := respGet.Header.Get("X-NDM-Realm")

	if challenge == "" {
		// Попытка вытащить из Www-Authenticate
		authHeader := respGet.Header.Get("Www-Authenticate")
		fmt.Printf("[AUTH] Www-Authenticate: %q\n", authHeader)

		// Парсинг: x-ndw2-interactive realm="XXX" challenge="YYY"
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

	fmt.Printf("[AUTH] Challenge=%q, Realm=%q\n", challenge, realm)

	if challenge == "" {
		// Читаем тело ответа для диагностики
		body, _ := io.ReadAll(respGet.Body)
		return false, fmt.Errorf("не удалось получить X-NDM-Challenge (status=%d, body=%s)", respGet.StatusCode, string(body[:min(len(body), 200)]))
	}
	if realm == "" {
		realm = "Keenetic"
	}

	// Шаг 2: Расчет хэшей
	s1 := login + ":" + realm + ":" + password
	h1 := md5Hex(s1)
	finalHash := sha256Hex(challenge + h1)

	fmt.Printf("[AUTH] Hash input: %s:%s:<pass>, md5=%s\n", login, realm, h1[:8]+"...")

	// Шаг 3: POST запрос
	payload := map[string]string{
		"login":    login,
		"password": finalHash,
	}
	jsonData, _ := json.Marshal(payload)

	reqPost, _ := http.NewRequest("POST", authURL, bytes.NewBuffer(jsonData))
	reqPost.Header.Set("Content-Type", "application/json")

	respPost, err := client.Do(reqPost)
	if err != nil {
		return false, fmt.Errorf("ошибка POST-авторизации: %v", err)
	}
	defer respPost.Body.Close()

	fmt.Printf("[AUTH] POST %s -> status %d\n", authURL, respPost.StatusCode)

	if respPost.StatusCode == http.StatusOK {
		fmt.Printf("[AUTH] SUCCESS! Login accepted\n")
		return true, nil
	}

	// Читаем тело для диагностики
	body, _ := io.ReadAll(respPost.Body)
	fmt.Printf("[AUTH] FAIL: status=%d, body=%s\n", respPost.StatusCode, string(body[:min(len(body), 200)]))

	return false, nil
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}

// DetectRouterIP пытается автоматически найти IP роутера
func DetectRouterIP() string {
	client := http.Client{Timeout: 1 * time.Second}
	ports := []string{"80", "81", "8080"}

	// 1. Пробуем найти через ip route (самый надежный способ для Keenetic/Entware)
	out, err := exec.Command("ip", "route", "show", "default").Output()
	if err == nil {
		fmt.Printf("[DETECT] ip route output: %s\n", strings.TrimSpace(string(out)))
		re := regexp.MustCompile(`via\s+([0-9.]+)`)
		match := re.FindStringSubmatch(string(out))
		if len(match) > 1 {
			gw := match[1]
			fmt.Printf("[DETECT] Gateway found: %s\n", gw)
			for _, p := range ports {
				url := fmt.Sprintf("http://%s:%s/auth", gw, p)
				resp, err := client.Get(url)
				if err == nil {
					fmt.Printf("[DETECT] Probe %s -> status %d\n", url, resp.StatusCode)
					resp.Body.Close()
					if resp.StatusCode == 401 {
						fmt.Printf("[DETECT] Found NDM at %s:%s\n", gw, p)
						return gw + ":" + p
					}
				} else {
					fmt.Printf("[DETECT] Probe %s -> error: %v\n", url, err)
				}
			}
		}
	} else {
		fmt.Printf("[DETECT] ip route error: %v\n", err)
	}

	// 2. Пробуем 127.0.0.1 (запасной вариант)
	for _, p := range ports {
		url := fmt.Sprintf("http://127.0.0.1:%s/auth", p)
		resp, err := client.Get(url)
		if err == nil {
			fmt.Printf("[DETECT] Probe %s -> status %d\n", url, resp.StatusCode)
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
				fmt.Printf("[DETECT] Probe %s -> status %d\n", url, resp.StatusCode)
				resp.Body.Close()
				if resp.StatusCode == 401 {
					return ip + ":" + p
				}
			}
		}
	}

	fmt.Printf("[DETECT] WARN: No NDM endpoint found, falling back to 127.0.0.1\n")
	return "127.0.0.1"
}
