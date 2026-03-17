class ServiceTemplate:
    """Генератор конфигураций Nginx для удаленного VPS"""

    @staticmethod
    def http_proxy(name, domain, local_port, ext_port=80, auth_user=None, use_ssl=False, target_host="127.0.0.1", target_port=80):
        """Конфиг для HTTP/HTTPS прокси"""
        auth_config = ""
        if auth_user:
            auth_config = f"""
    auth_basic "rProxy: {name}";
    auth_basic_user_file /etc/nginx/rproxy_{name}.htpasswd;
    # ТОТАЛЬНАЯ ИЗОЛЯЦИЯ: Бэкенд никогда не видит пароль Nginx
    proxy_set_header Authorization ""; 
    proxy_set_header X-Forwarded-User $remote_user;
    """
        listen_80 = f"""
server {{
    listen 80;
    server_name {domain};
    return 301 https://$host$request_uri;
}}""" if use_ssl and domain and str(ext_port) == "443" else ""

        listen_main = f"listen {ext_port} ssl;" if use_ssl else f"listen {ext_port};"
        ssl_config = f"""
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;
    """ if use_ssl else ""

        # "Стелс-режим": для бэкенда прикидываемся, что зашли по его внутреннему IP
        # Это критично для Keenetic и других систем с защитой от DNS Rebinding
        stealth_host = f"{target_host}:{target_port}" if str(target_port) != "80" else target_host

        return f"""{listen_80}
server {{
    {listen_main}
    server_name {domain if domain else "_"};
    {ssl_config}
    
    proxy_buffering off;
    proxy_request_buffering off;

    location / {{
        {auth_config}
        proxy_pass http://127.0.0.1:{local_port};
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host "{stealth_host}";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto {"https" if use_ssl else "http"};
        proxy_set_header X-Forwarded-Port {ext_port};
        
        # СТЕЛС-РЕЖИМ 2.0: Прикидываемся локальным браузером
        # Убираем внешнее имя хоста из X-Forwarded-Host, чтобы не смущать CSRF
        proxy_set_header X-Forwarded-Host "";
        
        # Origin и Referer строго на внутренний IP
        # Учитываем протокол целевого порта (обычно http, но может быть https)
        set $p_proto "http";
        if ($server_port = 443) {{ set $p_proto "https"; }}

        proxy_set_header Origin "$p_proto://{stealth_host}";
        proxy_set_header Referer "$p_proto://{stealth_host}/";
        
        proxy_hide_header 'Access-Control-Allow-Origin';
        proxy_hide_header WWW-Authenticate;
        proxy_hide_header x-ndw2-interactive; # Для Keenetic
        
        # Предотвращаем конфликты сессий
        proxy_buffer_size 128k;
        proxy_buffers 4 256k;
        proxy_busy_buffers_size 256k;
        proxy_hide_header X-Frame-Options;
        proxy_hide_header Content-Security-Policy;
        proxy_cookie_domain "{target_host}" "$host";
        proxy_read_timeout 7d;
        proxy_send_timeout 7d;
    }}
    
    # Редирект с некорректного HTTPS порта (ошибка 497 -> 301)
    error_page 497 301 =307 https://$host:$server_port$request_uri;
}}
"""

    @staticmethod
    def stream_proxy(port, local_port, domain=None, proto="tcp"):
        """Конфиг для TCP/UDP (Stream) прокси. Если есть домен — используем SSL (только для TCP)."""
        listen_opts = f"{port} {proto}" if proto == "udp" else str(port)
        
        if domain and proto == "tcp":
            return f"""
server {{
    listen {port} ssl;
    proxy_pass 127.0.0.1:{local_port};

    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_handshake_timeout 15s;
    ssl_session_cache shared:SSLSTREAM:10m;
    ssl_session_timeout 1h;
}}
"""
        return f"""
server {{
    listen {listen_opts};
    proxy_pass 127.0.0.1:{local_port};
}}
"""

    @staticmethod
    def certbot_validation_vhost(domain):
        """Временный конфиг для валидации домена через Certbot"""
        return f"""
server {{
    listen 80;
    server_name {domain};
    location / {{
        return 200 "Certbot validation window";
    }}
}}
"""

class ServiceManager:
    """Логика формирования параметров для различных типов сервисов"""
    
    @staticmethod
    def get_nginx_path(svc_type):
        if svc_type in ['tcp', 'ssh', 'udp']:
            return "/etc/nginx/streams-enabled"
        return "/etc/nginx/sites-enabled"

    @staticmethod
    def generate_conf(svc_cfg, use_ssl_paths=False):
        svc_type = svc_cfg.get('SVC_TYPE', 'http')
        name = svc_cfg.get('SVC_NAME')
        domain = svc_cfg.get('SVC_DOMAIN', '')
        tunnel_port = svc_cfg.get('SVC_TUNNEL_PORT')
        ext_port = svc_cfg.get('SVC_EXT_PORT', 80)
        target_host = svc_cfg.get('SVC_TARGET_HOST', '127.0.0.1')
        target_port = svc_cfg.get('SVC_TARGET_PORT', 80)
        
        if svc_type in ['http', 'ttyd']:
            return ServiceTemplate.http_proxy(
                name, domain, tunnel_port, 
                ext_port=ext_port,
                auth_user=svc_cfg.get('SVC_AUTH_USER'),
                use_ssl=use_ssl_paths,
                target_host=target_host,
                target_port=target_port
            )
        elif svc_type in ['tcp', 'ssh']:
            # Если это TCP и мы хотим SSL (через домен)
            return ServiceTemplate.stream_proxy(
                ext_port, tunnel_port, 
                domain if use_ssl_paths else None,
                proto="tcp"
            )
        
        return ""
