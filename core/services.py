class ServiceTemplate:
    """Генератор конфигураций Nginx для удаленного VPS"""

    @staticmethod
    def http_proxy(name, domain, local_port, auth_user=None, auth_pass_file=None):
        """Конфиг для HTTP/HTTPS прокси"""
        auth_config = ""
        if auth_user:
            auth_config = f"""
    auth_basic "Restricted Access";
    auth_basic_user_file /etc/nginx/rproxy_{name}.htpasswd;
    """
        
        return f"""
server {{
    listen 80;
    server_name {domain};
    
    location / {{
        {auth_config}
        proxy_pass http://127.0.0.1:{local_port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }}
}}
"""

    @staticmethod
    def tcp_proxy(port, local_port):
        """Конфиг для TCP (Stream) прокси"""
        return f"""
server {{
    listen {port};
    proxy_pass 127.0.0.1:{local_port};
}}
"""

class ServiceManager:
    """Логика формирования параметров для различных типов сервисов"""
    
    @staticmethod
    def get_nginx_path(svc_type):
        if svc_type == 'tcp':
            return "/etc/nginx/streams-enabled"
        return "/etc/nginx/sites-enabled"

    @staticmethod
    def generate_conf(svc_cfg):
        svc_type = svc_cfg.get('SVC_TYPE', 'http')
        name = svc_cfg.get('SVC_NAME')
        domain = svc_cfg.get('SVC_DOMAIN', '')
        # Порт, на котором будет висеть SSH-туннель на VPS (127.0.0.1)
        tunnel_port = svc_cfg.get('SVC_TUNNEL_PORT')
        
        if svc_type == 'http':
            return ServiceTemplate.http_proxy(
                name, domain, tunnel_port, 
                svc_cfg.get('SVC_AUTH_USER'), 
                svc_cfg.get('SVC_AUTH_PASS')
            )
        elif svc_type == 'tcp':
            ext_port = svc_cfg.get('SVC_EXT_PORT')
            return ServiceTemplate.tcp_proxy(ext_port, tunnel_port)
        
        return ""
