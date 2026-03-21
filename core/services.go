package core

import (
	"fmt"
	"os"
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
		return httpProxyConf(name, domain, tunnelPort, extPort, svcCfg["SVC_AUTH_USER"], useSSLPaths, targetHost, targetPort, svcCfg["SVC_ROUTER_AUTH"], apiPort)
	case "tcp", "ssh":
		domainForSSL := ""
		if useSSLPaths {
			domainForSSL = domain
		}
		return streamProxyConf(extPort, tunnelPort, domainForSSL, "tcp")
	}

	return ""
}

// httpProxyConf генерирует конфиг для HTTP/HTTPS прокси
func httpProxyConf(name, domain, localPort, extPort, authUser string, useSSL bool, targetHost, targetPort string, routerAuth string, apiTunnelPort string) string {
	// Блок авторизации (Унифицированный Identity Provider v1.2.2)
	authDirectives := ""
	authHelpers := ""

	if routerAuth == "yes" || authUser != "" {
		authDirectives = `
        auth_request /rproxy_auth_verify;
        error_page 401 = @rproxy_login;`

		authHelpers = fmt.Sprintf(`
    # Проверка сессии через Identity Provider
    location = /rproxy_auth_verify {
        internal;
        proxy_pass http://127.0.0.1:%s/api/verify;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header Cookie $http_cookie;
        proxy_set_header Host $http_host; # Передаем оригинальный домен и ПОРТ
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    # Эндпоинты входа
    location = /login {
        auth_request off;
        proxy_pass http://127.0.0.1:%s/login;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location = /api/login {
        auth_request off;
        proxy_pass http://127.0.0.1:%s/api/login;
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Редирект на логин при 401 Unauthorized
    location @rproxy_login {
        return 302 $scheme://$http_host/login?next=$scheme://$http_host$request_uri;
    }`, apiTunnelPort, apiTunnelPort, apiTunnelPort)
	}

	listen80 := ""
	if useSSL && domain != "" && extPort == "443" {
		listen80 = fmt.Sprintf(`
server {
    listen 80;
    server_name %s;
    return 301 https://$host$request_uri;
}`, domain)
	}

	listenMain := fmt.Sprintf("listen %s;", extPort)
	if useSSL {
		listenMain = fmt.Sprintf("listen %s ssl;", extPort)
	}

	sslConfig := ""
	if useSSL {
		sslConfig = fmt.Sprintf(`
    ssl_certificate /etc/letsencrypt/live/%s/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/%s/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    `, domain, domain)
	}

	stealthHost := targetHost
	if targetPort != "80" {
		stealthHost = fmt.Sprintf("%s:%s", targetHost, targetPort)
	}

	serverName := domain
	if serverName == "" {
		serverName = "_"
	}

	proto := "http"
	if useSSL {
		proto = "https"
	}

	return fmt.Sprintf(`%s
server {
    %s
    server_name %s;
    %s
    
    proxy_buffering off;
    proxy_request_buffering off;

    location / {
        %s
        proxy_pass http://127.0.0.1:%s/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
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
        proxy_send_timeout 7d;
    }
    
    %s

    error_page 497 301 =307 https://$host:$server_port$request_uri;
}
`,
		listen80,
		listenMain,
		serverName,
		sslConfig,
		authDirectives,
		localPort,
		stealthHost,
		proto,
		extPort,
		stealthHost,
		stealthHost,
		targetHost,
		authHelpers,
	)
}

func streamProxyConf(port, localPort, domain, proto string) string {
	if proto == "" {
		proto = "tcp"
	}
	if domain != "" && proto == "tcp" {
		return fmt.Sprintf(`
server {
    listen %s ssl;
    proxy_pass 127.0.0.1:%s;
    ssl_certificate /etc/letsencrypt/live/%s/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/%s/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_handshake_timeout 15s;
    ssl_session_cache shared:SSLSTREAM:10m;
    ssl_session_timeout 1h;
}
`, port, localPort, domain, domain)
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
    location / {
        return 200 "Certbot validation window";
    }
}
`, domain)
}

// GetServiceByDomain ищет конфиг сервиса по его домену и порту
func GetServiceByDomain(host string) map[string]string {
	if host == "" {
		return nil
	}

	parts := strings.Split(host, ":")
	domain := parts[0]
	port := "80"
	if len(parts) > 1 {
		port = parts[1]
	}

	entries, err := os.ReadDir(ServicesDir)
	if err != nil {
		return nil
	}

	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".conf") {
			path := filepath.Join(ServicesDir, e.Name())
			cfg := LoadConfig(path)
			
			cfgDomain := cfg["SVC_DOMAIN"]
			cfgPort := cfg["SVC_EXT_PORT"]
			if cfgPort == "" {
				cfgPort = "80"
			}

			if cfgDomain == domain && cfgPort == port {
				return cfg
			}
		}
	}
	return nil
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
