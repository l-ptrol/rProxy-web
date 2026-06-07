package core

import (
	"fmt"
	"os"
	"path"
	"path/filepath"
	"strings"
)

// GetNginxPath возвращает путь для конфигов Nginx на VPS в зависимости от типа сервиса
func GetNginxPath(svcType string) string {
	switch svcType {
	case "tcp", "ssh", "udp":
		return "/etc/nginx/streams-enabled"
	default:
		return "/etc/nginx/sites-enabled"
	}
}

// GenerateNginxConf генерирует конфигурацию Nginx для сервиса
func GenerateNginxConf(svcCfg map[string]string, useSSLPaths bool) string {
	svcType := svcCfg["SVC_TYPE"]
	if svcType == "" {
		svcType = "http"
	}

	name := svcCfg["SVC_NAME"]
	domain := svcCfg["SVC_DOMAIN"]
	tunnelPort := svcCfg["SVC_TUNNEL_PORT"]
	extPort := svcCfg["SVC_EXT_PORT"]
	if extPort == "" {
		extPort = "80"
	}
	targetHost := svcCfg["SVC_TARGET_HOST"]
	if targetHost == "" {
		targetHost = "127.0.0.1"
	}
	targetPort := svcCfg["SVC_TARGET_PORT"]
	if targetPort == "" {
		targetPort = "80"
	}

	switch svcType {
	case "http", "ttyd":
		apiPort := svcCfg["SVC_API_PORT"]
		if apiPort == "" {
			apiPort = "28181"
		}
		totpMode := svcCfg["SVC_TOTP_MODE"]
		return httpProxyConf(name, domain, tunnelPort, extPort, svcCfg["SVC_AUTH_USER"], useSSLPaths, targetHost, targetPort, svcCfg["SVC_ROUTER_AUTH"], apiPort, totpMode)
	case "tcp", "ssh":
		domainForSSL := ""
		// Оборачиваем в SSL только если это не SSH (SSH имеет собственное шифрование)
		if useSSLPaths && svcType != "ssh" {
			domainForSSL = domain
		}
		return streamProxyConf(extPort, tunnelPort, domainForSSL, "tcp")
	}

	return ""
}

// httpProxyConf генерирует конфиг для HTTP/HTTPS прокси (v1.9.3-go)
func httpProxyConf(name, domain, localPort, extPort, authUser string, useSSL bool, targetHost, targetPort string, routerAuth string, apiTunnelPort string, totpMode string) string {
	svcCfg := map[string]string{
		"SVC_NAME":        name,
		"SVC_DOMAIN":      domain,
		"SVC_TUNNEL_PORT": localPort,
		"SVC_EXT_PORT":    extPort,
		"SVC_AUTH_USER":   authUser,
		"SVC_TARGET_HOST": targetHost,
		"SVC_TARGET_PORT": targetPort,
		"SVC_ROUTER_AUTH": routerAuth,
		"SVC_API_PORT":    apiTunnelPort,
		"SVC_TOTP_MODE":   totpMode,
	}
	return generateHttpProxyConf([]map[string]string{svcCfg}, useSSL)
}

func streamProxyConf(port, localPort, domain, proto string) string {
	if proto == "" {
		proto = "tcp"
	}
	if domain != "" && proto == "tcp" {
		isIP := strings.Contains(domain, ".") && !strings.ContainsAny(domain, "abcdefghijklmnopqrstuvwxyz")
		certPath := fmt.Sprintf("/etc/letsencrypt/live/%s/fullchain.pem", domain)
		keyPath := fmt.Sprintf("/etc/letsencrypt/live/%s/privkey.pem", domain)
		
		if isIP {
			certPath = fmt.Sprintf("/etc/nginx/ssl/rproxy_%s.crt", domain)
			keyPath = fmt.Sprintf("/etc/nginx/ssl/rproxy_%s.key", domain)
		}

		return fmt.Sprintf(`
server {
    listen %s ssl;
    proxy_pass 127.0.0.1:%s;
    ssl_certificate %s;
    ssl_certificate_key %s;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_handshake_timeout 15s;
    ssl_session_cache shared:SSLSTREAM:10m;
    ssl_session_timeout 1h;
}
`, port, localPort, certPath, keyPath)
	}
	listenOpts := port
	if proto == "udp" {
		listenOpts = port + " udp"
	}
	return fmt.Sprintf(`
server {
    listen %s;
    proxy_pass 127.0.0.1:%s;
}
`, listenOpts, localPort)
}

func CertbotValidationVhost(domain string) string {
	return fmt.Sprintf(`
server {
    listen 80;
    server_name %s;
    
    location ~ ^/.well-known/acme-challenge/ {
        allow all;
        root /var/www/letsencrypt;
    }

    location / {
        return 200 "SSL validation window (rProxy)";
    }
}
`, domain)
}

// IsHTTPType проверяет, является ли тип сервиса HTTP-совместимым (v1.9.3-go)
func IsHTTPType(svcType string) bool {
	return svcType == "http" || svcType == "ttyd"
}

// GetDomainConfName возвращает стандартизированное имя файла для конфига домена (v1.9.3-go)
func GetDomainConfName(domain, port string) string {
	safe := strings.ReplaceAll(domain, ".", "_")
	safe = strings.ReplaceAll(safe, "-", "_")
	if port == "" || port == "80" || port == "443" {
		return "dom_" + safe
	}
	return "dom_" + safe + "_" + port
}

// FindHTTPServicesForDomain находит все HTTP-совместимые сервисы на одном домене, VPS и порту (v1.9.3-go)
func FindHTTPServicesForDomain(domain, vps, port string) []map[string]string {
	var group []map[string]string
	entries, err := os.ReadDir(ServicesDir)
	if err != nil {
		return group
	}

	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".conf") {
			continue
		}
		cfg := LoadConfig(filepath.Join(ServicesDir, e.Name()))
		if IsHTTPType(cfg["SVC_TYPE"]) && cfg["SVC_DOMAIN"] == domain && cfg["SVC_VPS"] == vps {
			p := cfg["SVC_EXT_PORT"]
			if p == "" {
				p = "80"
			}
			if p == port {
				group = append(group, cfg)
			}
		}
	}
	return group
}

// GetAllActiveDomainPortPairs возвращает карту активных пар домен:порт на конкретном VPS (v1.9.3-go)
func GetAllActiveDomainPortPairs(vpsID string) map[string]bool {
	pairs := make(map[string]bool)
	entries, err := os.ReadDir(ServicesDir)
	if err != nil {
		return pairs
	}

	for _, e := range entries {
		if !strings.HasSuffix(e.Name(), ".conf") {
			continue
		}
		cfg := LoadConfig(filepath.Join(ServicesDir, e.Name()))
		if cfg["SVC_VPS"] == vpsID && cfg["SVC_DOMAIN"] != "" {
			p := cfg["SVC_EXT_PORT"]
			if p == "" {
				p = "80"
			}
			pairs[cfg["SVC_DOMAIN"]+":"+p] = true
		}
	}
	return pairs
}

// GenerateCombinedHttpConf создает единый server блок Nginx для нескольких сервисов на одном домене (v1.9.3-go)
func GenerateCombinedHttpConf(group []map[string]string, useSSL bool) string {
	return generateHttpProxyConf(group, useSSL)
}

// generateHttpProxyConf генерирует объединенный server блок Nginx для группы HTTP-сервисов (v1.9.3-go)
func generateHttpProxyConf(group []map[string]string, useSSL bool) string {
	if len(group) == 0 {
		return ""
	}

	first := group[0]
	domain := first["SVC_DOMAIN"]
	extPort := first["SVC_EXT_PORT"]
	if extPort == "" {
		extPort = "80"
	}

	proto := "http"
	if useSSL {
		proto = "https"
	}

	locationsConf := ""
	var authHelpers []string
	var authHelpersAdded = make(map[string]bool)
	var firstAuthSvc map[string]string

	for _, svc := range group {
		svcName := svc["SVC_NAME"]
		safeName := strings.ReplaceAll(svcName, "-", "_")
		localPort := svc["SVC_TUNNEL_PORT"]
		targetHost := svc["SVC_TARGET_HOST"]
		if targetHost == "" {
			targetHost = "127.0.0.1"
		}
		targetPort := svc["SVC_TARGET_PORT"]
		if targetPort == "" {
			targetPort = "80"
		}
		apiPort := svc["SVC_API_PORT"]
		if apiPort == "" {
			apiPort = "28181"
		}

		svcPath := svc["SVC_PATH"]
		if svcPath == "" {
			svcPath = "/"
		}

		stealthHost := targetHost
		if targetPort != "80" {
			stealthHost = fmt.Sprintf("%s:%s", targetHost, targetPort)
		}

		// СТЕЛС-РЕЖИМ 2.0 (по умолчанию для rProxy-web)
		nginxDirectives := fmt.Sprintf(`
        proxy_set_header Host "%s";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto %s;
        proxy_set_header X-Forwarded-Port %s;
        
        # СТЕЛС-РЕЖИМ 2.0
        proxy_set_header X-Forwarded-Host "";
        proxy_set_header Origin "http://%s";
        proxy_set_header Referer "http://%s/";
        
        proxy_hide_header 'Access-Control-Allow-Origin';
        proxy_hide_header WWW-Authenticate;
        proxy_hide_header x-ndw2-interactive;
        
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
        proxy_cookie_domain "%s" "$host";
        proxy_read_timeout 7d;
        proxy_send_timeout 7d;`, stealthHost, proto, extPort, stealthHost, stealthHost, targetHost)

		authDirectives := ""
		requireAuth := svc["SVC_ROUTER_AUTH"] == "yes" || svc["SVC_AUTH_USER"] != "" || (svc["SVC_TOTP_MODE"] != "" && svc["SVC_TOTP_MODE"] != "none")
		if requireAuth {
			authDirectives = fmt.Sprintf(`
        auth_request /_rp_auth_%s;
        error_page 401 = @rproxy_login;`, safeName)

			if firstAuthSvc == nil {
				firstAuthSvc = svc
			}

			if !authHelpersAdded[safeName] {
				authHelpersAdded[safeName] = true
				authHelpers = append(authHelpers, fmt.Sprintf(`
    # Проверка сессии через Identity Provider для %s
    location = /_rp_auth_%s {
        internal;
        proxy_pass http://127.0.0.1:%s/api/verify;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Cookie $http_cookie;
        proxy_set_header Host $http_host; 
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header X-Forwarded-For $remote_addr;
    }`, svcName, safeName, apiPort))
			}
		}

		cleanPath := path.Clean("/" + svcPath)
		passURL := fmt.Sprintf("http://127.0.0.1:%s", localPort)
		if cleanPath == "/" {
			passURL += "/"
		} else {
			cleanPath += "/"
			passURL += "/"
		}

		locationsConf += fmt.Sprintf(`
    location %s {
        %s
        proxy_pass %s;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        %s
    }`, cleanPath, authDirectives, passURL, nginxDirectives)
	}

	// Если в группе несколько сервисов, и ни один не привязан к корню "/", 
	// добавим автоматический фолбэк/редирект на первый сервис для корня
	if len(group) > 1 {
		hasRoot := false
		for _, svc := range group {
			if svc["SVC_PATH"] == "/" || svc["SVC_PATH"] == "" {
				hasRoot = true
				break
			}
		}

		if !hasRoot {
			firstSvc := group[0]
			localPort := firstSvc["SVC_TUNNEL_PORT"]
			targetHost := firstSvc["SVC_TARGET_HOST"]
			if targetHost == "" {
				targetHost = "127.0.0.1"
			}
			targetPort := firstSvc["SVC_TARGET_PORT"]
			if targetPort == "" {
				targetPort = "80"
			}
			safeName := strings.ReplaceAll(firstSvc["SVC_NAME"], "-", "_")

			stealthHost := targetHost
			if targetPort != "80" {
				stealthHost = fmt.Sprintf("%s:%s", targetHost, targetPort)
			}

			nginxDirectives := fmt.Sprintf(`
        proxy_set_header Host "%s";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto %s;
        proxy_set_header X-Forwarded-Port %s;
        proxy_set_header X-Forwarded-Host "";
        proxy_set_header Origin "http://%s";
        proxy_set_header Referer "http://%s/";
        proxy_cookie_domain "%s" "$host";
        proxy_read_timeout 7d;
        proxy_send_timeout 7d;`, stealthHost, proto, extPort, stealthHost, stealthHost, targetHost)

			authDirectives := ""
			requireAuth := firstSvc["SVC_ROUTER_AUTH"] == "yes" || firstSvc["SVC_AUTH_USER"] != "" || (firstSvc["SVC_TOTP_MODE"] != "" && firstSvc["SVC_TOTP_MODE"] != "none")
			if requireAuth {
				authDirectives = fmt.Sprintf(`
        auth_request /_rp_auth_%s;
        error_page 401 = @rproxy_login;`, safeName)
			}

			locationsConf += fmt.Sprintf(`
    location / {
        %s
        proxy_pass http://127.0.0.1:%s/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        %s
    }`, authDirectives, localPort, nginxDirectives)
		}
	}

	var authHelpersConf string
	if firstAuthSvc != nil {
		apiPort := firstAuthSvc["SVC_API_PORT"]
		if apiPort == "" {
			apiPort = "28181"
		}

		authHelpersConf = strings.Join(authHelpers, "\n") + fmt.Sprintf(`
 
    # Глобальные эндпоинты входа для домена %[1]s
    location = /login {
        auth_request off;
        proxy_pass http://127.0.0.1:%[2]s/login;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
 
    location = /api/login {
        auth_request off;
        proxy_pass http://127.0.0.1:%[2]s/api/login;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
 
    location = /api/auth/requirements {
        auth_request off;
        proxy_pass http://127.0.0.1:%[2]s/api/auth/requirements;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
 
    location = /api/totp/verify {
        auth_request off;
        proxy_pass http://127.0.0.1:%[2]s/api/totp/verify;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
 
    # Редирект на логин при 401 Unauthorized
    location @rproxy_login {
        return 302 $scheme://$http_host/login?next=$scheme://$http_host$request_uri;
    }`, domain, apiPort)
	}

	listen80 := ""
	if domain != "" && extPort != "80" {
		redirect := ""
		if useSSL && extPort == "443" {
			redirect = "return 301 https://$host$request_uri;"
		}
		listen80 = fmt.Sprintf(`
server {
    listen 80;
    server_name %s;
    %s
}`, domain, redirect)
	}

	listenMain := fmt.Sprintf("listen %s;", extPort)
	if useSSL {
		listenMain = fmt.Sprintf("listen %s ssl;", extPort)
	}

	sslConfig := ""
	if useSSL {
		certPath := fmt.Sprintf("/etc/nginx/ssl/%s.crt", domain)
		keyPath := fmt.Sprintf("/etc/nginx/ssl/%s.key", domain)

		sslConfig = fmt.Sprintf(`
    ssl_certificate %s;
    ssl_certificate_key %s;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;`, certPath, keyPath)
	}

	return fmt.Sprintf(`%s
server {
    %s
    server_name %s;
    %s
    
    proxy_buffering off;
    proxy_request_buffering off;
    client_max_body_size 0;
 
    %s
    
    %s
 
    error_page 497 301 =307 https://$host:$server_port$request_uri;
}
`, listen80, listenMain, domain, sslConfig, locationsConf, authHelpersConf)
}

// GetServiceByDomain ищет конфиг сервиса по его домену и порту
func GetServiceByDomain(host string) map[string]string {
	if host == "" {
		return nil
	}

	parts := strings.Split(host, ":")
	domain := strings.ToLower(parts[0])
	port := ""
	if len(parts) > 1 {
		port = parts[1]
	}

	entries, err := os.ReadDir(ServicesDir)
	if err != nil {
		return nil
	}

	var fallbackCfg map[string]string

	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".conf") {
			path := filepath.Join(ServicesDir, e.Name())
			cfg := LoadConfig(path)
			
			cfgDomain := strings.ToLower(cfg["SVC_DOMAIN"])
			cfgPort := cfg["SVC_EXT_PORT"]
			if cfgPort == "" {
				cfgPort = "80"
			}

			if cfgDomain == domain {
				// Если есть полное совпадение домена и порта — возвращаем сразу
				if port != "" && cfgPort == port {
					return cfg
				}
				// Если порт не указан в Host, и конфиг на 80/443 — это тоже точное совпадение
				if port == "" && (cfgPort == "80" || cfgPort == "443") {
					return cfg
				}
				fallbackCfg = cfg
			}
		}
	}
	return fallbackCfg
}

func ListServiceConfigs(servicesDir string) []string {
	entries, err := os.ReadDir(servicesDir)
	if err != nil {
		return nil
	}
	var result []string
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".conf") {
			result = append(result, e.Name())
		}
	}
	return result
}
