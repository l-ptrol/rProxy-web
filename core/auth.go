package core

import (
	"bytes"
	"crypto/md5"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"

	otp_totp "github.com/pquerna/otp/totp"
)

var keeneticHTTPClient = &http.Client{
	Timeout: 5 * time.Second,
	CheckRedirect: func(req *http.Request, via []*http.Request) error {
		return http.ErrUseLastResponse
	},
}

// --- Вспомогательные функции криптографии ---

// ValidateTOTP проверяет 6-значный код (v1.7.1-go)
func ValidateTOTP(secret, code string) bool {
	return otp_totp.Validate(code, secret)
}

// GenerateTOTPSecret создает новый секрет (v1.7.1-go)
func GenerateTOTPSecret(accountName string) (string, string, error) {
	key, err := otp_totp.Generate(otp_totp.GenerateOpts{
		Issuer:      "rProxy",
		AccountName: accountName,
	})
	if err != nil {
		return "", "", err
	}
	return key.Secret(), key.URL(), nil
}

// GenerateTOTPURL формирует URL для существующего секрета без генерации нового (v1.7.1-go)
func GenerateTOTPURL(accountName, secret string) string {
	return fmt.Sprintf("otpauth://totp/rProxy:%s?secret=%s&issuer=rProxy", accountName, secret)
}

func md5Hex(data string) string {
	h := md5.Sum([]byte(data))
	return fmt.Sprintf("%x", h)
}

func sha256Hex(data string) string {
	h := sha256.Sum256([]byte(data))
	return fmt.Sprintf("%x", h)
}

// --- Авторизация Keenetic (NDM API) ---

// getLinuxDefaultGateway парсит /proc/net/route для нахождения шлюза по умолчанию
func getLinuxDefaultGateway() string {
	data, err := os.ReadFile("/proc/net/route")
	if err != nil {
		return ""
	}
	lines := strings.Split(string(data), "\n")
	for _, line := range lines {
		fields := strings.Fields(line)
		if len(fields) >= 3 && fields[1] == "00000000" {
			gwHex := fields[2]
			if len(gwHex) == 8 {
				// Парсим hex-строку (little-endian порядок байт)
				var ip [4]byte
				for i := 0; i < 4; i++ {
					b, err := hex.DecodeString(gwHex[8-i*2-2 : 8-i*2])
					if err != nil || len(b) != 1 {
						return ""
					}
					ip[i] = b[0]
				}
				return fmt.Sprintf("%d.%d.%d.%d", ip[0], ip[1], ip[2], ip[3])
			}
		}
	}
	return ""
}

func KeeneticAuth(routerIP, login, password string) (bool, error) {
	fmt.Printf("[AUTH] Start: routerIP=%q, login=%q\n", routerIP, login)

	if routerIP == "" || routerIP == "auto" {
		routerIP = DetectRouterIP()
	} else if routerIP == "127.0.0.1" {
		clientCheck := &http.Client{
			Timeout: 1 * time.Second,
			CheckRedirect: func(req *http.Request, via []*http.Request) error {
				return http.ErrUseLastResponse
			},
		}
		if r, err := clientCheck.Get("http://127.0.0.1:80/auth"); err == nil {
			r.Body.Close()
			if r.StatusCode == 403 {
				routerIP = DetectRouterIP()
			}
		} else {
			routerIP = DetectRouterIP()
		}
	}

	scheme := "http"
	if strings.HasPrefix(routerIP, "https://") {
		scheme = "https"
		routerIP = strings.TrimPrefix(routerIP, "https://")
	} else if strings.HasPrefix(routerIP, "http://") {
		routerIP = strings.TrimPrefix(routerIP, "http://")
	} else if strings.HasSuffix(routerIP, ":443") || strings.HasSuffix(routerIP, ":8443") {
		scheme = "https"
	}

	if !strings.Contains(routerIP, ":") {
		if scheme == "https" {
			routerIP = routerIP + ":443"
		} else {
			routerIP = routerIP + ":80"
		}
	}

	authURL := fmt.Sprintf("%s://%s/auth", scheme, routerIP)
	fmt.Printf("[AUTH] Using URL: %s\n", authURL)

	reqGet, err := http.NewRequest("GET", authURL, nil)
	if err != nil {
		return false, err
	}
	respGet, err := keeneticHTTPClient.Do(reqGet)
	if err != nil {
		return false, fmt.Errorf("ошибка связи с роутером (%s): %v", routerIP, err)
	}
	defer respGet.Body.Close()

	if respGet.StatusCode == http.StatusOK {
		fmt.Printf("[AUTH] SUCCESS (No auth required): Access granted for %s\n", login)
		return true, nil
	}

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

	reqPost, err := http.NewRequest("POST", authURL, bytes.NewBuffer(jsonData))
	if err != nil {
		return false, err
	}
	reqPost.Header.Set("Content-Type", "application/json")
	
	cleanIP := routerIP
	if strings.Contains(cleanIP, ":") {
		cleanIP = strings.Split(cleanIP, ":")[0]
	}
	
	reqPost.Header.Set("Origin", fmt.Sprintf("%s://%s", scheme, cleanIP))
	reqPost.Header.Set("Referer", fmt.Sprintf("%s://%s/", scheme, cleanIP))

	// Переносим куки с GET запроса на POST запрос
	for _, cookie := range respGet.Cookies() {
		reqPost.AddCookie(cookie)
	}

	respPost, err := keeneticHTTPClient.Do(reqPost)
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

	client := http.Client{
		Timeout: 1 * time.Second,
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
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

	// Нативное определение IP на интерфейсе br0
	iface, err := net.InterfaceByName("br0")
	if err == nil {
		addrs, err := iface.Addrs()
		if err == nil {
			for _, addr := range addrs {
				if ipnet, ok := addr.(*net.IPNet); ok {
					if ip4 := ipnet.IP.To4(); ip4 != nil {
						br0IP := ip4.String()
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
			}
		}
	}

	// Нативное определение шлюза по умолчанию
	if gw := getLinuxDefaultGateway(); gw != "" {
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
	ID           string
	ExpiresAt    time.Time
	VerifiedTotp map[string]bool // [v1.7.0-go] Domain -> verified
}

var (
	sessions   = make(map[string]Session)
	sessionsMu sync.RWMutex

	loginAttempts = make(map[string]attemptData)
	attemptsMu sync.Mutex
)

type attemptData struct {
	Count      int
	BlockUntil time.Time
	LastSeen   time.Time
}

func init() {
	go func() {
		ticker := time.NewTicker(5 * time.Minute)
		for range ticker.C {
			attemptsMu.Lock()
			now := time.Now()
			for ip, data := range loginAttempts {
				if now.Sub(data.LastSeen) > 15*time.Minute {
					delete(loginAttempts, ip)
				}
			}
			attemptsMu.Unlock()
		}
	}()
}

func CreateSession() string {
	sessionsMu.Lock()
	defer sessionsMu.Unlock()

	seed := fmt.Sprintf("%d-%d", time.Now().UnixNano(), os.Getpid())
	token := sha256Hex(seed)

	sessions[token] = Session{
		ID:           token,
		ExpiresAt:    time.Now().Add(24 * time.Hour),
		VerifiedTotp: make(map[string]bool),
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

func IsTotpVerified(token, domain string) bool {
	sessionsMu.RLock()
	defer sessionsMu.RUnlock()

	sess, ok := sessions[token]
	if !ok || time.Now().After(sess.ExpiresAt) {
		return false
	}
	// Если домен пустой (для самого rProxy), считаем проверенным, если есть сессия
	if domain == "" { return true }
	return sess.VerifiedTotp[domain]
}

func SetTotpVerified(token, domain string) {
	sessionsMu.Lock()
	defer sessionsMu.Unlock()

	sess, ok := sessions[token]
	if ok {
		if sess.VerifiedTotp == nil {
			sess.VerifiedTotp = make(map[string]bool)
		}
		sess.VerifiedTotp[domain] = true
		sessions[token] = sess
	}
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
	data.LastSeen = time.Now()
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
