package core

import (
	"fmt"
	"os"
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
		return httpProxyConf(name, domain, tunnelPort, extPort, svcCfg["SVC_AUTH_USER"], useSSLPaths, targetHost, targetPort, svcCfg["SVC_ROUTER_AUTH"])
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
func httpProxyConf(name, domain, localPort, extPort, authUser string, useSSL bool, targetHost, targetPort string, routerAuth string) string {
	// Блок авторизации
	authConfig := ""
	if authUser != "" {
		authConfig = fmt.Sprintf(`
    auth_basic "rProxy: %s";
    auth_basic_user_file /etc/nginx/rproxy_%s.htpasswd;
    # ТОТАЛЬНАЯ ИЗОЛЯЦИЯ: Бэкенд никогда не видит пароль Nginx
    proxy_set_header Authorization "";
    proxy_set_header X-Forwarded-User $remote_user;
    `, name, name)
	}

	// Блок Router Auth
	rAuthDirectives := ""
	rAuthHelpers := ""
	if routerAuth == "yes" {
		rAuthDirectives = `
        auth_request /rproxy_verify;
        error_page 401 = @rproxy_login;`

		rAuthHelpers = `
    location = /rproxy_verify {
        internal;
        proxy_pass http://127.0.0.1:81/api/verify;
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";
        proxy_set_header X-Original-URI $request_uri;
        proxy_set_header X-Forwarded-For $remote_addr;
    }

    location @rproxy_login {
        return 302 $scheme://$http_host/login?backUrl=$scheme://$http_host$request_uri;
    }`
	}

	// Блок редиректа HTTP -> HTTPS
	listen80 := ""
	if useSSL && domain != "" && extPort == "443" {
		listen80 = fmt.Sprintf(`
server {
    listen 80;
    server_name %s;
    return 301 https://$host$request_uri;
}`, domain)
	}

	// Блок listen
	listenMain := fmt.Sprintf("listen %s;", extPort)
	if useSSL {
		listenMain = fmt.Sprintf("listen %s ssl;", extPort)
	}

	// Блок SSL сертификатов
	sslConfig := ""
	if useSSL {
		sslConfig = fmt.Sprintf(`
    ssl_certificate /etc/letsencrypt/live/%s/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/%s/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    `, domain, domain)
	}

	// "Стелс-режим": для бэкенда прикидываемся локальным пользователем
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
        %s
        proxy_pass http://127.0.0.1:%s;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host "%s";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto %s;
        proxy_set_header X-Forwarded-Port %s;
        
        # СТЕЛС-РЕЖИМ 2.0: Прикидываемся локальным браузером
        proxy_set_header X-Forwarded-Host "";
        
        # Origin и Referer строго на внутренний IP
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

    # Редирект с некорректного HTTPS порта
    error_page 497 301 =307 https://$host:$server_port$request_uri;
}
`,
		listen80,
		listenMain,
		serverName,
		sslConfig,
		authConfig,
		rAuthDirectives,
		localPort,
		stealthHost,
		proto,
		extPort,
		stealthHost,
		stealthHost,
		targetHost,
		rAuthHelpers,
	)
}

// streamProxyConf генерирует конфиг для TCP/UDP (Stream) прокси
func streamProxyConf(port, localPort, domain, proto string) string {
	if proto == "" {
		proto = "tcp"
	}

	// TCP с SSL (через домен)
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

	// Простой TCP/UDP
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

// CertbotValidationVhost — временный конфиг для валидации домена через Certbot
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

// ListServiceConfigs возвращает список .conf файлов сервисов
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
