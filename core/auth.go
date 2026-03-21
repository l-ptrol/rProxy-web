package core

import (
	"bytes"
	"crypto/md5"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/cookiejar"
	"os"
	"os/exec"
	"regexp"
	"strings"
	"sync"
	"time"
)

// --- Вспомогательные функции криптографии ---

func md5Hex(data string) string {
	h := md5.Sum([]byte(data))
	return fmt.Sprintf("%x", h)
}

func sha256Hex(data string) string {
	h := sha256.Sum256([]byte(data))
	return fmt.Sprintf("%x", h)
}

// --- Авторизация Keenetic (NDM API) ---

func KeeneticAuth(routerIP, login, password string) (bool, error) {
	jar, _ := cookiejar.New(nil)
	client := &http.Client{
		Jar:     jar,
		Timeout: 5 * time.Second,
	}

	fmt.Printf("[AUTH] Start: routerIP=%q, login=%q\n", routerIP, login)

	if routerIP == "" || routerIP == "auto" {
		routerIP = DetectRouterIP()
	} else if routerIP == "127.0.0.1" {
		clientCheck := &http.Client{Timeout: 1 * time.Second}
		if r, err := clientCheck.Get("http://127.0.0.1:80/auth"); err == nil {
			r.Body.Close()
			if r.StatusCode == 403 {
				routerIP = DetectRouterIP()
			}
		} else {
			routerIP = DetectRouterIP()
		}
	}

	if !strings.Contains(routerIP, ":") {
		routerIP = routerIP + ":80"
	}

	authURL := fmt.Sprintf("http://%s/auth", routerIP)
	fmt.Printf("[AUTH] Using URL: %s\n", authURL)

	reqGet, _ := http.NewRequest("GET", authURL, nil)
	respGet, err := client.Do(reqGet)
	if err != nil {
		return false, fmt.Errorf("ошибка связи с роутером (%s): %v", routerIP, err)
	}
	defer respGet.Body.Close()

	challenge := respGet.Header.Get("X-NDM-Challenge")
	realm := respGet.Header.Get("X-NDM-Realm")

	if challenge == "" {
		authHeader := respGet.Header.Get("Www-Authenticate")
		if strings.Contains(authHeader, "challenge=") {
			re := regexp.MustCompile(`realm="([^"]*)"`)
			if rm := re.FindStringSubmatch(authHeader); len(rm) > 1 {
				realm = rm[1]
			}
			re2 := regexp.MustCompile(`challenge="([^"]*)"`)
			if cm := re2.FindStringSubmatch(authHeader); len(cm) > 1 {
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

	s1 := login + ":" + realm + ":" + password
	h1 := md5Hex(s1)
	finalHash := sha256Hex(challenge + h1)

	payload := map[string]string{
		"login":    login,
		"password": finalHash,
	}
	jsonData, _ := json.Marshal(payload)

	reqPost, _ := http.NewRequest("POST", authURL, bytes.NewBuffer(jsonData))
	reqPost.Header.Set("Content-Type", "application/json")
	
	cleanIP := routerIP
	if strings.HasSuffix(cleanIP, ":80") {
		cleanIP = strings.TrimSuffix(cleanIP, ":80")
	}
	
	reqPost.Header.Set("Origin", fmt.Sprintf("http://%s", cleanIP))
	reqPost.Header.Set("Referer", fmt.Sprintf("http://%s/", cleanIP))

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

var cachedRouterIP string

func DetectRouterIP() string {
	if cachedRouterIP != "" {
		return cachedRouterIP
	}

	client := http.Client{Timeout: 1 * time.Second}
	ports := []string{"80", "81", "8080"}

	for _, p := range ports {
		url := fmt.Sprintf("http://127.0.0.1:%s/auth", p)
		if resp, err := client.Get(url); err == nil {
			resp.Body.Close()
			if resp.StatusCode == 401 {
				cachedRouterIP = "127.0.0.1:" + p
				return cachedRouterIP
			}
		}
	}

	out, err := exec.Command("ip", "addr", "show", "br0").Output()
	if err == nil {
		re := regexp.MustCompile(`inet\s+([0-9.]+)/`)
		if match := re.FindStringSubmatch(string(out)); len(match) > 1 {
			br0IP := match[1]
			for _, p := range ports {
				url := fmt.Sprintf("http://%s:%s/auth", br0IP, p)
				if resp, err := client.Get(url); err == nil {
					resp.Body.Close()
					if resp.StatusCode == 401 {
						cachedRouterIP = br0IP + ":" + p
						return cachedRouterIP
					}
				}
			}
		}
	}

	out, err = exec.Command("ip", "route", "show", "default").Output()
	if err == nil {
		re := regexp.MustCompile(`via\s+([0-9.]+)`)
		if match := re.FindStringSubmatch(string(out)); len(match) > 1 {
			gw := match[1]
			for _, p := range ports {
				url := fmt.Sprintf("http://%s:%s/auth", gw, p)
				if resp, err := client.Get(url); err == nil {
					resp.Body.Close()
					if resp.StatusCode == 401 {
						cachedRouterIP = gw + ":" + p
						return cachedRouterIP
					}
				}
			}
		}
	}

	defaults := []string{"192.168.1.1", "192.168.0.1", "192.168.10.1", "192.168.60.1"}
	for _, ip := range defaults {
		for _, p := range ports {
			url := fmt.Sprintf("http://%s:%s/auth", ip, p)
			if resp, err := client.Get(url); err == nil {
				resp.Body.Close()
				if resp.StatusCode == 401 {
					cachedRouterIP = ip + ":" + p
					return cachedRouterIP
				}
			}
		}
	}

	cachedRouterIP = "192.168.1.1:80"
	return cachedRouterIP
}

// --- СИСТЕМА СЕССИЙ И ЗАЩИТА ОТ БРУТФОРСА (v1.2.0) ---

type Session struct {
	ID        string
	ExpiresAt time.Time
}

var (
	sessions   = make(map[string]Session)
	sessionsMu sync.RWMutex

	loginAttempts = make(map[string]struct {
		Count      int
		BlockUntil time.Time
	})
	attemptsMu sync.Mutex
)

func CreateSession() string {
	sessionsMu.Lock()
	defer sessionsMu.Unlock()

	seed := fmt.Sprintf("%d-%d", time.Now().UnixNano(), os.Getpid())
	token := sha256Hex(seed)

	sessions[token] = Session{
		ID:        token,
		ExpiresAt: time.Now().Add(24 * time.Hour),
	}
	return token
}

func IsSessionValid(token string) bool {
	sessionsMu.RLock()
	defer sessionsMu.RUnlock()

	sess, ok := sessions[token]
	if !ok || time.Now().After(sess.ExpiresAt) {
		return false
	}
	return true
}

func DeleteSession(token string) {
	sessionsMu.Lock()
	defer sessionsMu.Unlock()
	delete(sessions, token)
}

func CheckBruteForce(ip string) (bool, time.Time) {
	attemptsMu.Lock()
	defer attemptsMu.Unlock()

	data, ok := loginAttempts[ip]
	if !ok {
		return false, time.Time{}
	}

	if time.Now().Before(data.BlockUntil) {
		return true, data.BlockUntil
	}

	if data.Count >= 5 && time.Now().After(data.BlockUntil) {
		delete(loginAttempts, ip)
		return false, time.Time{}
	}

	return false, time.Time{}
}

func RecordAttempt(ip string) {
	attemptsMu.Lock()
	defer attemptsMu.Unlock()

	data := loginAttempts[ip]
	data.Count++
	if data.Count >= 5 {
		data.BlockUntil = time.Now().Add(5 * time.Minute)
		fmt.Printf("[AUTH] IP %s blocked for 5 minutes (brute-force)\n", ip)
	}
	loginAttempts[ip] = data
}

func ClearAttempts(ip string) {
	attemptsMu.Lock()
	defer attemptsMu.Unlock()
	delete(loginAttempts, ip)
}
