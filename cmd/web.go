package cmd

import (
	"encoding/json"
	"fmt"
	"math/rand"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"rproxy/core"
	"sort"
	"strings"
	"sync"
	"time"
)

func isIP(host string) bool {
	return net.ParseIP(host) != nil
}

// vpsStatusCache — кэш статусов VPS (online/offline)
var vpsStatusCache = sync.Map{}

// StartWebServer запускает HTTP-сервер на указанном порту
func StartWebServer(port int, indexHTML []byte, loginHTML []byte) {
	mux := http.NewServeMux()

	// Страница входа
	mux.HandleFunc("/login", func(w http.ResponseWriter, r *http.Request) {
		content := strings.ReplaceAll(string(loginHTML), "{{version}}", core.VERSION)
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write([]byte(content))
	})

	// Главная (защищенная)
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		
		content := strings.ReplaceAll(string(indexHTML), "{{version}}", core.VERSION)
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		w.Write([]byte(content))
	})

	// ==================== API: Авторизация ====================

	mux.HandleFunc("/api/login", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", 405)
			return
		}

		var data map[string]string
		json.NewDecoder(r.Body).Decode(&data)
		login := data["login"]
		password := data["password"]
		ip := strings.Split(r.RemoteAddr, ":")[0]

		// 1. Проверка брутфорса
		if blocked, until := core.CheckBruteForce(ip); blocked {
			jsonResponse(w, map[string]string{
				"status":  "error",
				"message": fmt.Sprintf("Слишком много попыток. IP заблокирован до %s", until.Format("15:04:05")),
			})
			return
		}

		// 2. Определяем тип авторизации для конкретного сервиса
		host := strings.Split(r.Host, ":")[0]
		fullHost := r.Host
		svcCfg := core.GetServiceByDomain(fullHost)

		gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
		gCfg := core.LoadConfig(gPath)

		isRouterAuth := false
		loginRequired := false
		expectedUser := ""
		expectedPass := ""

		if svcCfg != nil {
			if svcCfg["SVC_ROUTER_AUTH"] == "yes" {
				isRouterAuth = true
				loginRequired = true
			} else if svcCfg["SVC_AUTH_USER"] != "" {
				isRouterAuth = false
				loginRequired = true
				expectedUser = svcCfg["SVC_AUTH_USER"]
				expectedPass = svcCfg["SVC_AUTH_PASS"]
			}
		} else {
			// Для самой панели управления — проверяем глобальные настройки
			if gCfg["ROUTER_AUTH"] == "yes" {
				isRouterAuth = true
				loginRequired = true
			}
		}

		ok := false
		var err error

		if loginRequired {
			if isRouterAuth {
				routerIP := gCfg["ROUTER_AUTH_IP"]
				if routerIP == "" {
					routerIP = core.GetRouterIP()
				}
				fmt.Printf("[AUTH] Using Router Auth (IP: %s) for host: %s\n", routerIP, fullHost)
				ok, err = core.KeeneticAuth(routerIP, login, password)
			} else {
				fmt.Printf("[AUTH] Using Local Auth for host: %s (User: %s)\n", fullHost, expectedUser)
				if login == expectedUser && password == expectedPass {
					ok = true
				}
			}
		} else {
			// Если логин не требуется — разрешаем вход для TOTP фазы
			fmt.Printf("[AUTH] Skipping login phase for host: %s\n", fullHost)
			ok = true
		}

		if ok {
			sid := core.CreateSession()
			core.ClearAttempts(ip)
			
			// Проверяем TOTP
			totpRequired := false
			if svcCfg != nil {
				totpMode := svcCfg["SVC_TOTP_MODE"]
				if totpMode != "" && totpMode != "none" {
					totpRequired = true
				}
			} else if gCfg["GLOBAL_TOTP_SECRET"] != "" {
				totpRequired = true
			}

			hostParts := strings.Split(host, ".")
			domain := ""
			if len(hostParts) >= 2 && !isIP(host) {
				domain = "." + strings.Join(hostParts[len(hostParts)-2:], ".")
			}

			http.SetCookie(w, &http.Cookie{
				Name:     "rproxy_session",
				Value:    sid,
				Path:     "/",
				Domain:   domain,
				HttpOnly: true,
				MaxAge:   86400 * 30,
			})

			if totpRequired {
				fmt.Printf("[LOGIN] Phase 1 OK, TOTP required for %s\n", host)
				jsonResponse(w, map[string]string{"status": "totp_required"})
			} else {
				core.SetTotpVerified(sid, host)
				fmt.Printf("[LOGIN] Complete success for %s\n", host)
				jsonResponse(w, map[string]string{"status": "success"})
			}
		} else {
			core.RecordAttempt(ip)
			errMsg := "Неверный логин или пароль"
			if err != nil {
				errMsg = err.Error()
			}
			jsonResponse(w, map[string]string{"status": "error", "message": errMsg})
		}
	})

	mux.HandleFunc("/api/check-auth", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", 405)
			return
		}

		var data map[string]string
		json.NewDecoder(r.Body).Decode(&data)
		login := data["login"]
		password := data["password"]
		routerIP := defaultStr(data["router_ip"], "127.0.0.1")

		ok, err := core.KeeneticAuth(routerIP, login, password)
		if ok {
			jsonResponse(w, map[string]string{"status": "success"})
		} else {
			if err != nil {
				jsonResponse(w, map[string]string{"status": "error", "message": err.Error()})
			} else {
				jsonResponse(w, map[string]string{"status": "error", "message": "Неверный логин или пароль"})
			}
		}
	})

	mux.HandleFunc("/api/logout", func(w http.ResponseWriter, r *http.Request) {
		if cookie, err := r.Cookie("rproxy_session"); err == nil {
			core.DeleteSession(cookie.Value)
		}
		host := strings.Split(r.Host, ":")[0]
		parts := strings.Split(host, ".")
		domain := ""
		if len(parts) >= 2 && !isIP(host) {
			domain = "." + strings.Join(parts[len(parts)-2:], ".")
		}

		http.SetCookie(w, &http.Cookie{
			Name:     "rproxy_session",
			Value:    "",
			Path:     "/",
			Domain:   domain,
			HttpOnly: true,
			MaxAge:   -1,
		})
		jsonResponse(w, map[string]string{"status": "success"})
	})

	mux.HandleFunc("/api/auth/requirements", func(w http.ResponseWriter, r *http.Request) {
		host := r.Host
		svcCfg := core.GetServiceByDomain(host)

		loginRequired := false
		totpRequired := false

		gCfg := core.LoadConfig(filepath.Join(core.RProxyRoot, "rproxy.conf"))

		if svcCfg != nil {
			if svcCfg["SVC_ROUTER_AUTH"] == "yes" || svcCfg["SVC_AUTH_USER"] != "" {
				loginRequired = true
			}
			if svcCfg["SVC_TOTP_MODE"] != "" && svcCfg["SVC_TOTP_MODE"] != "none" {
				totpRequired = true
			}
		} else {
			if gCfg["ROUTER_AUTH"] == "yes" {
				loginRequired = true
			}
			if gCfg["GLOBAL_TOTP_SECRET"] != "" {
				totpRequired = true
			}
		}

		jsonResponse(w, map[string]interface{}{
			"login_required": loginRequired,
			"totp_required":  totpRequired,
			"debug": map[string]interface{}{
				"host":       host,
				"svc_found":  svcCfg != nil,
				"svc_domain": func() string { if svcCfg != nil { return svcCfg["SVC_DOMAIN"] }; return "" }(),
				"svc_port":   func() string { if svcCfg != nil { return svcCfg["SVC_EXT_PORT"] }; return "" }(),
				"v":          core.VERSION,
			},
		})
	})

	mux.HandleFunc("/api/verify", func(w http.ResponseWriter, r *http.Request) {
		cookie, err := r.Cookie("rproxy_session")
		host := r.Host
		svcCfg := core.GetServiceByDomain(host)
		
		gCfg := core.LoadConfig(filepath.Join(core.RProxyRoot, "rproxy.conf"))

		loginRequired := false
		if svcCfg != nil {
			if svcCfg["SVC_ROUTER_AUTH"] == "yes" || svcCfg["SVC_AUTH_USER"] != "" {
				loginRequired = true
			}
		} else {
			if gCfg["ROUTER_AUTH"] == "yes" {
				loginRequired = true
			}
		}

		if err == nil {
			sid := cookie.Value
			if core.IsSessionValid(sid) {
				if svcCfg != nil {
					totpMode := svcCfg["SVC_TOTP_MODE"]
					if totpMode != "" && totpMode != "none" {
						if !core.IsTotpVerified(sid, host) {
							fmt.Printf("[AUTH] FAIL: TOTP required but not verified for %s\n", host)
							http.Error(w, "Unauthorized (TOTP Required)", http.StatusUnauthorized)
							return
						}
					}
				} else {
					if gCfg["GLOBAL_TOTP_SECRET"] != "" {
						if !core.IsTotpVerified(sid, host) {
							http.Error(w, "Unauthorized (Global TOTP Required)", http.StatusUnauthorized)
							return
						}
					}
				}
				w.WriteHeader(http.StatusOK)
				return
			}
		}

		totpRequired := false
		if svcCfg != nil {
			if svcCfg["SVC_TOTP_MODE"] != "" && svcCfg["SVC_TOTP_MODE"] != "none" {
				totpRequired = true
			}
		} else if gCfg["GLOBAL_TOTP_SECRET"] != "" {
			totpRequired = true
		}

		if !loginRequired && !totpRequired {
			w.WriteHeader(http.StatusOK)
			return
		}

		http.Error(w, "Unauthorized", http.StatusUnauthorized)
	})

	mux.HandleFunc("/api/totp/verify", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", 405)
			return
		}

		cookie, err := r.Cookie("rproxy_session")
		if err != nil || !core.IsSessionValid(cookie.Value) {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		sid := cookie.Value

		var data map[string]string
		json.NewDecoder(r.Body).Decode(&data)
		code := data["code"]
		host := r.Host
		
		svcCfg := core.GetServiceByDomain(host)
		// Если svcCfg == nil, это обращение к панели управления (Dashboard)

		secret := ""
		if svcCfg != nil {
			totpMode := svcCfg["SVC_TOTP_MODE"]
			if totpMode == "local" {
				secret = svcCfg["SVC_TOTP_SECRET"]
			} else if totpMode == "global" {
				gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
				gCfg := core.LoadConfig(gPath)
				secret = gCfg["GLOBAL_TOTP_SECRET"]
			}
		} else {
			// Панель управления (dashboard) всегда использует глобальный секрет
			gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
			gCfg := core.LoadConfig(gPath)
			secret = gCfg["GLOBAL_TOTP_SECRET"]
		}

		if secret == "" {
			jsonResponse(w, map[string]string{"status": "error", "message": "TOTP не настроен"})
			return
		}

		if core.ValidateTOTP(secret, code) {
			core.SetTotpVerified(sid, host)
			fmt.Printf("[TOTP] SUCCESS for domain %s\n", host)
			jsonResponse(w, map[string]string{"status": "success"})
		} else {
			fmt.Printf("[TOTP] FAIL for domain %s (code: %s)\n", host, code)
			jsonResponse(w, map[string]string{"status": "error", "message": "Неверный код"})
		}
	})

	// ==================== API: Система ====================

	mux.HandleFunc("/api/stats", func(w http.ResponseWriter, r *http.Request) {
		svcCount := 0
		onlineCount := 0

		if entries, err := os.ReadDir(core.ServicesDir); err == nil {
			for _, e := range entries {
				if strings.HasSuffix(e.Name(), ".conf") {
					svcCount++
					name := strings.TrimSuffix(e.Name(), ".conf")
					if core.IsRunning(name) {
						onlineCount++
					}
				}
			}
		}

		vpsCount := 0
		vpsOnline := 0
		if entries, err := os.ReadDir(core.VPSDir); err == nil {
			for _, e := range entries {
				if strings.HasSuffix(e.Name(), ".conf") {
					vpsCount++
					name := strings.TrimSuffix(e.Name(), ".conf")
					if v, ok := vpsStatusCache.Load(name); ok {
						if v.(string) == "online" {
							vpsOnline++
						}
					}
				}
			}
		}

		jsonResponse(w, map[string]interface{}{
			"services":   svcCount,
			"online":     onlineCount,
			"vps":        vpsCount,
			"vps_online": vpsOnline,
			"version":    core.VERSION,
		})
	})

	// ==================== API: Сервисы ====================

	mux.HandleFunc("/api/services", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case "GET":
			handleListServices(w, r)
		case "POST":
			handleCreateService(w, r)
		default:
			http.Error(w, "Method not allowed", 405)
		}
	})

	// Роутинг для /api/services/<name>
	mux.HandleFunc("/api/services/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/api/services/")
		parts := strings.Split(path, "/")
		name := parts[0]

		if len(parts) == 1 {
			// /api/services/<name>
			switch r.Method {
			case "GET":
				handleGetService(w, r, name)
			case "POST":
				handleUpdateService(w, r, name)
			default:
				http.Error(w, "Method not allowed", 405)
			}
			return
		}

		if len(parts) >= 2 {
			switch parts[1] {
			case "deploy":
				if len(parts) == 2 && r.Method == "POST" {
					handleDeployService(w, r, name)
				} else if len(parts) == 3 && parts[2] == "log" && r.Method == "GET" {
					handleDeployLog(w, r, name)
				}
			case "logs":
				handleServiceLogs(w, r, name)
			}
		}
	})

	// ==================== API: Действия ====================

	mux.HandleFunc("/api/action/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/api/action/")
		parts := strings.Split(path, "/")

		if len(parts) >= 2 {
			name := parts[0]
			action := parts[1]

			if len(parts) == 2 && r.Method == "POST" {
				handleServiceAction(w, r, name, action)
			} else if len(parts) == 3 && parts[2] == "log" && r.Method == "GET" {
				handleActionLog(w, r, name, action)
			}
		}
	})

	// ==================== API: VPS ====================

	mux.HandleFunc("/api/vps", func(w http.ResponseWriter, r *http.Request) {
		switch r.Method {
		case "GET":
			handleListVPS(w, r)
		case "POST":
			handleCreateVPS(w, r)
		default:
			http.Error(w, "Method not allowed", 405)
		}
	})

	mux.HandleFunc("/api/vps/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/api/vps/")
		parts := strings.Split(path, "/")
		name := parts[0]

		if len(parts) == 1 && r.Method == "DELETE" {
			handleDeleteVPS(w, r, name)
			return
		}

		if len(parts) >= 2 {
			switch parts[1] {
			case "health":
				handleVPSHealth(w, r, name)
			case "cleanup":
				handleVPSCleanup(w, r, name)
			case "repair":
				handleVPSRepair(w, r, name)
			case "setup":
				handleVPSSetup(w, r, name)
			case "task":
				if len(parts) >= 4 && parts[3] == "log" {
					handleVPSTaskLog(w, r, name, parts[2])
				}
			}
		}
	})

	// ==================== API: Настройки ====================

	mux.HandleFunc("/api/settings/auth", func(w http.ResponseWriter, r *http.Request) {
		gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
		gCfg := core.LoadConfig(gPath)
		// Для обратной совместимости возвращаем первый из списка или из конфига
		user := gCfg["CUSTOM_AUTH_USER"]
		pass := gCfg["CUSTOM_AUTH_PASS"]

		jsonResponse(w, map[string]string{
			"custom_user": user,
			"custom_pass": pass,
		})
	})

	mux.HandleFunc("/api/settings/auth/list", func(w http.ResponseWriter, r *http.Request) {
		authPath := filepath.Join(core.RProxyRoot, "custom_auth.json")
		
		if r.Method == "GET" {
			var list []map[string]string
			if data, err := os.ReadFile(authPath); err == nil {
				json.Unmarshal(data, &list)
			}
			if list == nil { list = []map[string]string{} }
			jsonResponse(w, list)
			return
		}

		if r.Method == "POST" {
			var list []map[string]string
			if err := json.NewDecoder(r.Body).Decode(&list); err != nil {
				http.Error(w, "Invalid JSON", 400)
				return
			}
			data, _ := json.MarshalIndent(list, "", "  ")
			os.WriteFile(authPath, data, 0644)
			
			// Синхронизируем первый элемент с rproxy.conf для обратной совместимости
			if len(list) > 0 {
				gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
				gCfg := core.LoadConfig(gPath)
				gCfg["CUSTOM_AUTH_USER"] = list[0]["user"]
				gCfg["CUSTOM_AUTH_PASS"] = list[0]["pass"]
				core.SaveConfig(gPath, gCfg)
			}

			jsonResponse(w, map[string]string{"status": "success"})
		}
	})

	mux.HandleFunc("/api/settings/global", func(w http.ResponseWriter, r *http.Request) {
		gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
		gCfg := core.LoadConfig(gPath)

		if r.Method == "GET" {
			jsonResponse(w, map[string]string{
				"boot_delay":  defaultStr(gCfg["BOOT_DELAY"], "60"),
				"router_auth": defaultStr(gCfg["ROUTER_AUTH"], "no"),
				"router_ip":   defaultStr(gCfg["ROUTER_AUTH_IP"], "127.0.0.1"),
			})
			return
		}

		if r.Method == "POST" {
			var data map[string]string
			json.NewDecoder(r.Body).Decode(&data)

			if val, ok := data["boot_delay"]; ok {
				gCfg["BOOT_DELAY"] = val
			}
			if val, ok := data["router_auth"]; ok {
				gCfg["ROUTER_AUTH"] = val
			}
			if val, ok := data["router_ip"]; ok {
				gCfg["ROUTER_AUTH_IP"] = val
			}
			if val, ok := data["custom_auth_user"]; ok {
				gCfg["CUSTOM_AUTH_USER"] = val
			}
			if val, ok := data["custom_auth_pass"]; ok {
				gCfg["CUSTOM_AUTH_PASS"] = val
			}
			if val, ok := data["totp_name"]; ok {
				gCfg["DASHBOARD_TOTP_NAME"] = val
			}
			core.SaveConfig(gPath, gCfg)
			jsonResponse(w, map[string]string{"status": "success"})
		}
	})

	mux.HandleFunc("/api/settings/totp", func(w http.ResponseWriter, r *http.Request) {
		gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
		gCfg := core.LoadConfig(gPath)

		if r.Method == "GET" {
			secret := gCfg["GLOBAL_TOTP_SECRET"]
			name := gCfg["DASHBOARD_TOTP_NAME"]
			if name == "" {
				name = "Admin"
			}
			if secret == "" {
				secret, _, _ = core.GenerateTOTPSecret(name)
				gCfg["GLOBAL_TOTP_SECRET"] = secret
				core.SaveConfig(gPath, gCfg)
			}
			url := core.GenerateTOTPURL(name, secret)

			jsonResponse(w, map[string]string{
				"secret": secret,
				"url":    url,
				"name":   name,
			})
			return
		}

		if r.Method == "POST" {
			// Ресет глобального ключа
			name := gCfg["DASHBOARD_TOTP_NAME"]
			if name == "" {
				name = "Admin"
			}
			secret, url, _ := core.GenerateTOTPSecret(name)
			gCfg["GLOBAL_TOTP_SECRET"] = secret
			core.SaveConfig(gPath, gCfg)
			jsonResponse(w, map[string]string{
				"status": "success",
				"secret": secret,
				"url":    url,
			})
		}
	})

	// Эндпоинт для настройки локального TOTP сервиса
	mux.HandleFunc("/api/totp/setup", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", 405)
			return
		}

		var data map[string]string
		json.NewDecoder(r.Body).Decode(&data)
		name := data["name"]
		action := data["action"] // 'get' or 'reset'

		cfgPath := filepath.Join(core.ServicesDir, name+".conf")
		cfg := core.LoadConfig(cfgPath)
		if len(cfg) == 0 {
			jsonResponse(w, map[string]string{"status": "error", "message": "Сервис не найден"})
			return
		}

		secret := cfg["SVC_TOTP_SECRET"]
		url := ""

		if action == "reset" || secret == "" {
			var err error
			secret, url, err = core.GenerateTOTPSecret(name)
			if err != nil {
				jsonResponse(w, map[string]string{"status": "error", "message": err.Error()})
				return
			}
			cfg["SVC_TOTP_SECRET"] = secret
			core.SaveConfig(cfgPath, cfg)
		} else {
			url = core.GenerateTOTPURL(name, secret)
		}

		jsonResponse(w, map[string]string{
			"status": "success",
			"secret": secret,
			"url":    url,
		})
	})

	// ==================== API: Обновление ====================

	mux.HandleFunc("/api/system/action", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", 405)
			return
		}
		var data map[string]string
		json.NewDecoder(r.Body).Decode(&data)

		switch data["action"] {
		case "restart":
			go func() {
				time.Sleep(1 * time.Second)
				exec.Command("/opt/etc/init.d/S99rproxy", "restart").Run()
			}()
			jsonResponse(w, map[string]string{"status": "success"})
		case "stop":
			go func() {
				time.Sleep(1 * time.Second)
				exec.Command("/opt/etc/init.d/S99rproxy", "stop").Run()
			}()
			jsonResponse(w, map[string]string{"status": "success"})
		case "reboot":
			go func() {
				time.Sleep(1 * time.Second)
				exec.Command("reboot").Run()
			}()
			jsonResponse(w, map[string]string{"status": "success"})
		default:
			http.Error(w, "Unknown action", 400)
		}
	})

	mux.HandleFunc("/api/system/update", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != "POST" {
			http.Error(w, "Method not allowed", 405)
			return
		}
		go core.SelfUpdate(true)
		jsonResponse(w, map[string]string{"status": "success"})
	})

	mux.HandleFunc("/api/system/update/log", func(w http.ResponseWriter, r *http.Request) {
		logPath := "/tmp/rproxy_updater.log"
		if data, err := os.ReadFile(logPath); err == nil {
			jsonResponse(w, map[string]string{"log": string(data)})
		} else {
			jsonResponse(w, map[string]string{"log": "Ожидание запуска установщика..."})
		}
	})

	mux.HandleFunc("/api/system/check_update", func(w http.ResponseWriter, r *http.Request) {
		// Проверка обновлений из GitHub
		resp, err := http.Get(fmt.Sprintf("https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/install.sh?t=%d", time.Now().Unix()))
		if err != nil {
			jsonResponse(w, map[string]string{"error": err.Error()})
			return
		}
		defer resp.Body.Close()

		body := make([]byte, 4096)
		n, _ := resp.Body.Read(body)
		content := string(body[:n])

		// Ищем VERSION="..."
		if idx := strings.Index(content, `VERSION="`); idx >= 0 {
			start := idx + len(`VERSION="`)
			end := strings.Index(content[start:], `"`)
			if end > 0 {
				latest := content[start : start+end]
				jsonResponse(w, map[string]interface{}{
					"latest":           latest,
					"current":          core.VERSION,
					"update_available": latest != core.VERSION,
				})
				return
			}
		}
		jsonResponse(w, map[string]string{"error": "Version not found in repo"})
	})

	mux.HandleFunc("/api/dns/resolve", func(w http.ResponseWriter, r *http.Request) {
		domain := r.URL.Query().Get("domain")
		if domain == "" {
			jsonResponse(w, map[string]interface{}{"ip": nil})
			return
		}
		ip := core.GetDomainIP(domain)
		if ip == "" {
			jsonResponse(w, map[string]interface{}{"ip": nil})
		} else {
			jsonResponse(w, map[string]string{"ip": ip})
		}
	})

	// Запуск фонового мониторинга VPS
	go vpsHealthMonitor()

	// Middleware для авторизации
	authMiddleware := func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			// Публичные маршруты
			if r.URL.Path == "/login" || r.URL.Path == "/api/login" || r.URL.Path == "/api/logout" || r.URL.Path == "/api/verify" {
				next.ServeHTTP(w, r)
				return
			}

			// Проверка настроек
			gPath := filepath.Join(core.RProxyRoot, "rproxy.conf")
			gCfg := core.LoadConfig(gPath)

			// Если авторизация через роутер включена
			if gCfg["ROUTER_AUTH"] == "yes" {
				cookie, err := r.Cookie("rproxy_session")
				validSession := false
				if err == nil {
					if core.IsSessionValid(cookie.Value) {
						validSession = true
					}
				}

				if !validSession {
					if strings.HasPrefix(r.URL.Path, "/api/") {
						http.Error(w, `{"error": "unauthorized"}`, http.StatusUnauthorized)
					} else {
						// Сохраняем путь для возврата после логина
						nextPath := r.URL.Path
						if r.URL.RawQuery != "" {
							nextPath += "?" + r.URL.RawQuery
						}
						http.Redirect(w, r, "/login?next="+nextPath, http.StatusFound)
					}
					return
				}
			}

			// Если ROUTER_AUTH != "yes", мы не проверяем куки (остается Basic Auth от Nginx)
			next.ServeHTTP(w, r)
		})
	}

	core.Msg(fmt.Sprintf("Веб-сервер запущен на порту %d", port))
	if err := http.ListenAndServe(fmt.Sprintf("0.0.0.0:%d", port), authMiddleware(mux)); err != nil {
		core.Err(fmt.Sprintf("Ошибка запуска веб-сервера: %v", err))
	}
}

// ==================== Обработчики ====================

func handleListServices(w http.ResponseWriter, r *http.Request) {
	var services []map[string]interface{}

	if entries, err := os.ReadDir(core.ServicesDir); err == nil {
		var names []string
		for _, e := range entries {
			if strings.HasSuffix(e.Name(), ".conf") {
				names = append(names, e.Name())
			}
		}
		sort.Strings(names)

		for _, f := range names {
			name := strings.TrimSuffix(f, ".conf")
			cfg := core.LoadConfig(filepath.Join(core.ServicesDir, f))

			status := "offline"
			if core.IsRunning(name) {
				status = "online"
			}

			services = append(services, map[string]interface{}{
				"id":       name,
				"name":     name,
				"type":     cfg["SVC_TYPE"],
				"target":   fmt.Sprintf("%s:%s", defaultStr(cfg["SVC_TARGET_HOST"], "127.0.0.1"), cfg["SVC_TARGET_PORT"]),
				"ext_port": cfg["SVC_EXT_PORT"],
				"domain":   cfg["SVC_DOMAIN"],
				"ssl":      cfg["SVC_SSL"] == "yes",
				"auth":     cfg["SVC_AUTH_USER"] != "" || cfg["SVC_ROUTER_AUTH"] == "yes" || (cfg["SVC_TOTP_MODE"] != "" && cfg["SVC_TOTP_MODE"] != "none"),
				"r_auth":   cfg["SVC_ROUTER_AUTH"] == "yes",
				"totp":     cfg["SVC_TOTP_MODE"],
				"status":   status,
			})
		}
	}

	if services == nil {
		services = []map[string]interface{}{}
	}
	jsonResponse(w, map[string]interface{}{"services": services})
}

func handleCreateService(w http.ResponseWriter, r *http.Request) {
	var data map[string]string
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		http.Error(w, "Пустой запрос", 400)
		return
	}

	name := strings.TrimSpace(data["name"])
	if name == "" {
		http.Error(w, "Название обязательно", 400)
		return
	}

	svcPath := filepath.Join(core.ServicesDir, name+".conf")
	if _, err := os.Stat(svcPath); err == nil {
		http.Error(w, "Сервис с таким именем уже существует", 409)
		return
	}

	os.MkdirAll(core.ServicesDir, 0755)
	tunnelPort := rand.Intn(5000) + 10000

	svcType := defaultStr(data["type"], "http")
	targetPort := defaultStr(data["target_port"], "80")
	if svcType == "ttyd" && targetPort == "" {
		targetPort = fmt.Sprintf("%d", rand.Intn(100)+7682)
	}

	cfg := map[string]string{
		"SVC_NAME":        name,
		"SVC_TYPE":        svcType,
		"SVC_TARGET_HOST": defaultStr(data["target_host"], "127.0.0.1"),
		"SVC_TARGET_PORT": targetPort,
		"SVC_VPS":         data["vps"],
		"SVC_EXT_PORT":    defaultStr(data["ext_port"], "443"),
		"SVC_DOMAIN":      data["domain"],
		"SVC_SSL":         defaultStr(data["ssl"], "no"),
		"SVC_ROUTER_AUTH": defaultStr(data["router_auth"], "no"),
		"SVC_TOTP_MODE":   defaultStr(data["totp_mode"], "none"),
		"SVC_TOTP_SECRET": data["totp_secret"],
		"SVC_TUNNEL_PORT": fmt.Sprintf("%d", tunnelPort),
		"SVC_ENABLED":     "yes",
	}

	authUser := strings.TrimSpace(data["auth_user"])
	authPass := strings.TrimSpace(data["auth_pass"])
	if authUser != "" && authPass != "" {
		cfg["SVC_AUTH_USER"] = authUser
		cfg["SVC_AUTH_PASS"] = authPass
	}

	core.SaveConfig(svcPath, cfg)
	jsonResponse(w, map[string]string{"status": "success", "name": name})
}

func handleGetService(w http.ResponseWriter, r *http.Request, name string) {
	svcPath := filepath.Join(core.ServicesDir, name+".conf")
	if _, err := os.Stat(svcPath); os.IsNotExist(err) {
		http.Error(w, "Сервис не найден", 404)
		return
	}

	cfg := core.LoadConfig(svcPath)
	jsonResponse(w, map[string]string{
		"name":        defaultStr(cfg["SVC_NAME"], name),
		"type":        defaultStr(cfg["SVC_TYPE"], "http"),
		"target_host": defaultStr(cfg["SVC_TARGET_HOST"], "127.0.0.1"),
		"target_port": cfg["SVC_TARGET_PORT"],
		"vps":         cfg["SVC_VPS"],
		"ext_port":    defaultStr(cfg["SVC_EXT_PORT"], "443"),
		"domain":      cfg["SVC_DOMAIN"],
		"ssl":         defaultStr(cfg["SVC_SSL"], "no"),
		"auth_user":   cfg["SVC_AUTH_USER"],
		"auth_pass":   cfg["SVC_AUTH_PASS"],
		"router_auth": defaultStr(cfg["SVC_ROUTER_AUTH"], "no"),
		"totp_mode":   defaultStr(cfg["SVC_TOTP_MODE"], "none"),
		"totp_secret": cfg["SVC_TOTP_SECRET"],
		"totp_url":    core.GetTotpUrl(cfg, name),
		"tunnel_port": cfg["SVC_TUNNEL_PORT"],
	})
}

func handleUpdateService(w http.ResponseWriter, r *http.Request, name string) {
	var data map[string]string
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		http.Error(w, "Пустой запрос", 400)
		return
	}

	oldName := name
	newName := strings.TrimSpace(data["name"])
	if newName == "" {
		newName = oldName
	}

	svcPath := filepath.Join(core.ServicesDir, oldName+".conf")
	if _, err := os.Stat(svcPath); os.IsNotExist(err) {
		http.Error(w, "Сервис не найден", 404)
		return
	}

	newPath := filepath.Join(core.ServicesDir, newName+".conf")
	// Если имя изменилось, проверяем, не занято ли новое
	if newName != oldName {
		if _, err := os.Stat(newPath); err == nil {
			http.Error(w, "Сервис с таким именем уже существует", 409)
			return
		}
	}

	oldCfg := core.LoadConfig(svcPath)

	newCfg := map[string]string{
		"SVC_NAME":        newName,
		"SVC_TYPE":        defaultStr(data["type"], "http"),
		"SVC_TARGET_HOST": defaultStr(data["target_host"], "127.0.0.1"),
		"SVC_TARGET_PORT": data["target_port"],
		"SVC_VPS":         data["vps"],
		"SVC_EXT_PORT":    defaultStr(data["ext_port"], "443"),
		"SVC_DOMAIN":      data["domain"],
		"SVC_SSL":         defaultStr(data["ssl"], "no"),
		"SVC_ROUTER_AUTH": defaultStr(data["router_auth"], "no"),
		"SVC_TOTP_MODE":   defaultStr(data["totp_mode"], "none"),
		"SVC_TOTP_SECRET": data["totp_secret"],
		"SVC_TUNNEL_PORT": oldCfg["SVC_TUNNEL_PORT"],
		"SVC_ENABLED":     defaultStr(oldCfg["SVC_ENABLED"], "yes"),
	}

	authUser := strings.TrimSpace(data["auth_user"])
	authPass := strings.TrimSpace(data["auth_pass"])
	if authUser != "" && authPass != "" {
		newCfg["SVC_AUTH_USER"] = authUser
		newCfg["SVC_AUTH_PASS"] = authPass
	}

	// Если имя изменилось, удаляем старый файл после сохранения нового
	if newName != oldName {
		core.SaveConfig(newPath, newCfg)
		os.Remove(svcPath)
	} else {
		core.SaveConfig(svcPath, newCfg)
	}

	jsonResponse(w, map[string]string{"status": "success", "name": newName})
}

func handleDeployService(w http.ResponseWriter, r *http.Request, name string) {
	svcPath := filepath.Join(core.ServicesDir, name+".conf")
	if _, err := os.Stat(svcPath); os.IsNotExist(err) {
		http.Error(w, "Сервис не найден", 404)
		return
	}

	logFile := fmt.Sprintf("/tmp/rproxy_deploy_%s.log", name)
	os.WriteFile(logFile, []byte(fmt.Sprintf("▸ Начало деплоя сервиса '%s'...\n", name)), 0644)

	go func() {
		core.SetLogHook(logFile)
		defer core.ClearLogHook()

		cfg := core.LoadConfig(svcPath)
		vpsID := cfg["SVC_VPS"]
		if vpsID == "" {
			appendToFile(logFile, "❌ Ошибка: VPS не указан в конфигурации сервиса.\n__DEPLOY_STATUS__:error\n")
			return
		}

		vpsPath := filepath.Join(core.VPSDir, vpsID+".conf")
		if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
			appendToFile(logFile, fmt.Sprintf("❌ Ошибка: VPS '%s' не найден.\n__DEPLOY_STATUS__:error\n", vpsID))
			return
		}

		vpsCfg := core.LoadConfig(vpsPath)

		// Если сервис уже запущен — остановить
		if core.IsRunning(name) {
			appendToFile(logFile, fmt.Sprintf("▸ Остановка текущего экземпляра '%s'...\n", name))
			core.StopService(name, cfg)
			time.Sleep(1 * time.Second)
		}

		// Пересобираем конфиг Nginx
		appendToFile(logFile, "▸ Генерация и загрузка новой конфигурации Nginx...\n")
		core.RedeployNginx(cfg, vpsCfg)

		result := core.StartService(cfg, vpsCfg, false)

		if !result {
			appendToFile(logFile, "\n❌ Деплой завершён с ошибками.\n__DEPLOY_STATUS__:error\n")
		} else {
			appendToFile(logFile, "\n✅ Сервис успешно развернут и запущен!\n__DEPLOY_STATUS__:success\n")
		}
	}()

	jsonResponse(w, map[string]string{"status": "started", "log": logFile})
}

func handleDeployLog(w http.ResponseWriter, r *http.Request, name string) {
	logFile := fmt.Sprintf("/tmp/rproxy_deploy_%s.log", name)
	if data, err := os.ReadFile(logFile); err == nil {
		content := string(data)
		status := "running"
		if strings.Contains(content, "__DEPLOY_STATUS__:success") {
			status = "success"
			content = strings.ReplaceAll(content, "__DEPLOY_STATUS__:success\n", "")
		} else if strings.Contains(content, "__DEPLOY_STATUS__:error") {
			status = "error"
			content = strings.ReplaceAll(content, "__DEPLOY_STATUS__:error\n", "")
		}
		jsonResponse(w, map[string]string{"log": content, "status": status})
	} else {
		jsonResponse(w, map[string]string{"log": "Ожидание запуска деплоя...", "status": "pending"})
	}
}

func handleServiceAction(w http.ResponseWriter, r *http.Request, name, action string) {
	svcPath := filepath.Join(core.ServicesDir, name+".conf")
	if _, err := os.Stat(svcPath); os.IsNotExist(err) {
		http.Error(w, "Сервис не найден", 404)
		return
	}

	// Удаление — синхронно
	if action == "delete" {
		cfg := core.LoadConfig(svcPath)
		var vpsCfg map[string]string
		if vpsID := cfg["SVC_VPS"]; vpsID != "" {
			vpsPath := filepath.Join(core.VPSDir, vpsID+".conf")
			if _, err := os.Stat(vpsPath); err == nil {
				vpsCfg = core.LoadConfig(vpsPath)
			}
		}
		core.StopService(name, cfg)
		if vpsCfg != nil {
			core.RemoveVhost(vpsCfg, name)
		}
		os.Remove(svcPath)
		jsonResponse(w, map[string]string{"status": "success"})
		return
	}

	// Остальные — фоновые
	go serviceActionWorker(name, action)
	jsonResponse(w, map[string]string{"status": "started"})
}

func serviceActionWorker(name, action string) {
	logFile := fmt.Sprintf("/tmp/rproxy_action_%s_%s.log", name, action)
	core.SetLogHook(logFile)
	defer core.ClearLogHook()

	os.WriteFile(logFile, []byte(fmt.Sprintf("▸ Начало выполнения действия '%s' для сервиса '%s'...\n", action, name)), 0644)

	svcPath := filepath.Join(core.ServicesDir, name+".conf")
	if _, err := os.Stat(svcPath); os.IsNotExist(err) {
		appendToFile(logFile, "❌ Сервис удален или не найден.\nФИНИШ\n")
		return
	}

	cfg := core.LoadConfig(svcPath)
	vpsID := cfg["SVC_VPS"]
	var vpsCfg map[string]string
	if vpsID != "" {
		vpsPath := filepath.Join(core.VPSDir, vpsID+".conf")
		if _, err := os.Stat(vpsPath); err == nil {
			vpsCfg = core.LoadConfig(vpsPath)
		}
	}

	switch action {
	case "start":
		if vpsCfg == nil {
			appendToFile(logFile, "❌ VPS не найден\n")
		} else {
			core.StartService(cfg, vpsCfg, true)
		}
	case "stop":
		core.StopService(name, cfg)
	case "restart":
		core.StopService(name, cfg)
		time.Sleep(1 * time.Second)
		if vpsCfg != nil {
			core.StartService(cfg, vpsCfg, true)
		}
	case "redeploy_nginx":
		if vpsCfg != nil {
			core.RedeployNginx(cfg, vpsCfg)
		}
	case "ssl":
		if vpsCfg != nil {
			core.RunCertbotForService(cfg, vpsCfg)
		}
	}

	appendToFile(logFile, fmt.Sprintf("\n✅ Действие '%s' успешно завершено!\nФИНИШ\n", action))
}

func handleActionLog(w http.ResponseWriter, r *http.Request, name, action string) {
	logPath := fmt.Sprintf("/tmp/rproxy_action_%s_%s.log", name, action)
	if data, err := os.ReadFile(logPath); err == nil {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write(data)
	} else {
		w.Write([]byte("Ожидание начала задачи..."))
	}
}

func handleServiceLogs(w http.ResponseWriter, r *http.Request, name string) {
	result := make(map[string]string)
	logDir := "/opt/var/log"

	for _, prefix := range []string{"tunnel", "ttyd", "autossh"} {
		logPath := filepath.Join(logDir, fmt.Sprintf("%s_%s.log", prefix, name))
		if data, err := os.ReadFile(logPath); err == nil {
			lines := strings.Split(string(data), "\n")
			start := 0
			if len(lines) > 100 {
				start = len(lines) - 100
			}
			result[prefix] = strings.Join(lines[start:], "\n")
		}
	}

	jsonResponse(w, result)
}

// ==================== VPS обработчики ====================

func handleListVPS(w http.ResponseWriter, r *http.Request) {
	var vpsList []map[string]interface{}

	if entries, err := os.ReadDir(core.VPSDir); err == nil {
		for _, e := range entries {
			if strings.HasSuffix(e.Name(), ".conf") {
				name := strings.TrimSuffix(e.Name(), ".conf")
				cfg := core.LoadConfig(filepath.Join(core.VPSDir, e.Name()))

				status := "unknown"
				if v, ok := vpsStatusCache.Load(name); ok {
					status = v.(string)
				}

				vpsList = append(vpsList, map[string]interface{}{
					"id":     name,
					"name":   name,
					"host":   cfg["VPS_HOST"],
					"user":   defaultStr(cfg["VPS_USER"], "root"),
					"port":   defaultStr(cfg["VPS_PORT"], "22"),
					"status": status,
				})
			}
		}
	}

	if vpsList == nil {
		vpsList = []map[string]interface{}{}
	}
	jsonResponse(w, map[string]interface{}{"vps": vpsList})
}

func handleCreateVPS(w http.ResponseWriter, r *http.Request) {
	var data map[string]string
	if err := json.NewDecoder(r.Body).Decode(&data); err != nil {
		http.Error(w, "Пустой запрос", 400)
		return
	}

	name := strings.TrimSpace(data["name"])
	host := strings.TrimSpace(data["host"])
	if name == "" || host == "" {
		http.Error(w, "Название и IP обязательны", 400)
		return
	}

	os.MkdirAll(core.VPSDir, 0755)
	vpsPath := filepath.Join(core.VPSDir, name+".conf")

	cfg := map[string]string{
		"VPS_HOST": host,
		"VPS_USER": defaultStr(strings.TrimSpace(data["user"]), "root"),
		"VPS_PORT": defaultStr(strings.TrimSpace(data["port"]), "22"),
		"VPS_AUTH": "key",
	}
	core.SaveConfig(vpsPath, cfg)
	jsonResponse(w, map[string]string{"status": "success", "name": name})
}

func handleDeleteVPS(w http.ResponseWriter, r *http.Request, name string) {
	vpsPath := filepath.Join(core.VPSDir, name+".conf")
	if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
		http.Error(w, "VPS не найден", 404)
		return
	}
	os.Remove(vpsPath)
	jsonResponse(w, map[string]string{"status": "success"})
}

func handleVPSHealth(w http.ResponseWriter, r *http.Request, name string) {
	vpsPath := filepath.Join(core.VPSDir, name+".conf")
	if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
		http.Error(w, "VPS не найден", 404)
		return
	}

	vpsCfg := core.LoadConfig(vpsPath)
	result := core.HealthCheck(vpsCfg)
	jsonResponse(w, result)
}

func handleVPSCleanup(w http.ResponseWriter, r *http.Request, name string) {
	vpsPath := filepath.Join(core.VPSDir, name+".conf")
	if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
		http.Error(w, "VPS не найден", 404)
		return
	}

	go vpsTaskWorker(name, "cleanup", "")
	jsonResponse(w, map[string]string{"status": "success"})
}

func handleVPSRepair(w http.ResponseWriter, r *http.Request, name string) {
	vpsPath := filepath.Join(core.VPSDir, name+".conf")
	if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
		http.Error(w, "VPS не найден", 404)
		return
	}

	go vpsTaskWorker(name, "repair", "")
	jsonResponse(w, map[string]string{"status": "success"})
}

func handleVPSSetup(w http.ResponseWriter, r *http.Request, name string) {
	vpsPath := filepath.Join(core.VPSDir, name+".conf")
	if _, err := os.Stat(vpsPath); os.IsNotExist(err) {
		http.Error(w, "VPS не найден", 404)
		return
	}

	var data map[string]string
	if r.Body != nil {
		json.NewDecoder(r.Body).Decode(&data)
	}

	pass := ""
	if data != nil && data["pass"] != "" {
		pass = data["pass"]
	}

	go vpsTaskWorker(name, "setup", pass)
	jsonResponse(w, map[string]string{"status": "success"})
}

func handleVPSTaskLog(w http.ResponseWriter, r *http.Request, name, action string) {
	logPath := filepath.Join(core.VPSDir, fmt.Sprintf("%s_%s.log", name, action))
	if data, err := os.ReadFile(logPath); err == nil {
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")
		w.Write(data)
	} else {
		w.Write([]byte("Ожидание начала задачи..."))
	}
}

func vpsTaskWorker(name, action, pass string) {
	logPath := filepath.Join(core.VPSDir, fmt.Sprintf("%s_%s.log", name, action))
	vpsPath := filepath.Join(core.VPSDir, name+".conf")
	vpsCfg := core.LoadConfig(vpsPath)

	os.WriteFile(logPath, []byte(fmt.Sprintf("▸ Начало задачи '%s' для VPS '%s'...\n", action, name)), 0644)

	switch action {
	case "cleanup":
		var active []string
		if entries, err := os.ReadDir(core.ServicesDir); err == nil {
			for _, e := range entries {
				if strings.HasSuffix(e.Name(), ".conf") {
					cfg := core.LoadConfig(filepath.Join(core.ServicesDir, e.Name()))
					if cfg["SVC_VPS"] == name {
						active = append(active, strings.TrimSuffix(e.Name(), ".conf"))
					}
				}
			}
		}
		_, msg := core.CleanupVPS(vpsCfg, active)
		appendToFile(logPath, msg+"\n")

	case "repair":
		appendToFile(logPath, "Проверка SSH доступа...\n")
		successSSH, outSSH := core.RunRemoteSimple(vpsCfg, "echo OK")
		if !successSSH {
			appendToFile(logPath, fmt.Sprintf("❌ Ошибка SSH: %s\nФИНИШ: Ошибка доступа\n", outSSH))
			return
		}

		appendToFile(logPath, "✅ SSH доступ подтвержден. Запускаю настройку окружения...\n")
		_, output := core.SetupVPS(vpsCfg)
		appendToFile(logPath, output+"\n")

	case "setup":
		if pass != "" {
			appendToFile(logPath, "🔑 Настройка доступа по временному паролю...\n")
			success, msg := core.SetupSSHWithPassword(name, vpsCfg, pass)
			appendToFile(logPath, msg+"\n")
			if !success {
				appendToFile(logPath, "ФИНИШ: Ошибка проброса SSH ключей\n")
				return
			}
		} else {
			appendToFile(logPath, "Внимание: пароль не передан. Проверка доступа по ключу...\n")
		}

		appendToFile(logPath, "Проверка SSH доступа...\n")
		successSSH, outSSH := core.RunRemoteSimple(vpsCfg, "echo OK")
		if !successSSH {
			appendToFile(logPath, fmt.Sprintf("❌ Ошибка SSH: %s\nФИНИШ: Ошибка доступа\n", outSSH))
			return
		}

		appendToFile(logPath, "✅ SSH доступ подтвержден. Запускаю настройку Nginx и Certbot...\n")
		_, output := core.SetupVPS(vpsCfg)
		appendToFile(logPath, output+"\n")
	}

	appendToFile(logPath, fmt.Sprintf("\n✅ Задача '%s' успешно завершена!\nФИНИШ\n", action))
}

// vpsHealthMonitor — фоновый мониторинг VPS
func vpsHealthMonitor() {
	for {
		if entries, err := os.ReadDir(core.VPSDir); err == nil {
			for _, e := range entries {
				if strings.HasSuffix(e.Name(), ".conf") {
					name := strings.TrimSuffix(e.Name(), ".conf")
					vpsCfg := core.LoadConfig(filepath.Join(core.VPSDir, e.Name()))
					success, _ := core.RunRemote(vpsCfg, "echo 1", 5*time.Second)
					if success {
						vpsStatusCache.Store(name, "online")
					} else {
						vpsStatusCache.Store(name, "offline")
					}
				}
			}
		}
		time.Sleep(180 * time.Second)
	}
}

// ==================== Утилиты ====================

func jsonResponse(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	json.NewEncoder(w).Encode(data)
}

func defaultStr(val, def string) string {
	if val == "" {
		return def
	}
	return val
}

func appendToFile(path, text string) {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	defer f.Close()
	f.WriteString(text)
}
