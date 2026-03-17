import os
import subprocess
import socket
from .utils import msg, warn, err, GREEN, RED, CYAN, DIM, NC, YELLOW
from .config import ConfigManager

class VPSManager:
    """Управление удаленными VPS серверами"""
    
    RPROXY_ROOT = "/opt/etc/rproxy"
    VPS_DIR = os.path.join(RPROXY_ROOT, "vps")
    SSH_KEY = os.path.join(RPROXY_ROOT, "id_ed25519")

    @staticmethod
    def ensure_ssh_key():
        """Гарантирует наличие SSH-ключа для работы с VPS"""
        if not os.path.exists(VPSManager.SSH_KEY):
            msg("Генерирую SSH-ключ (ed25519)...")
            try:
                # Пытаемся найти ssh-keygen в путях Entware или системных
                keygen = "/opt/bin/ssh-keygen"
                if not os.path.exists(keygen):
                    keygen = "ssh-keygen"
                
                subprocess.run([keygen, "-t", "ed25519", "-f", VPSManager.SSH_KEY, "-N", "", "-q"], check=True)
                os.chmod(VPSManager.SSH_KEY, 0o600)
                
                # Генерируем публичный ключ, если он не создался автоматически
                pub_key = f"{VPSManager.SSH_KEY}.pub"
                if not os.path.exists(pub_key):
                    subprocess.run([keygen, "-y", "-f", VPSManager.SSH_KEY], 
                                 stdout=open(pub_key, 'w'), check=True)
            except Exception as e:
                err(f"Не удалось сгенерировать SSH-ключ: {e}")

    @staticmethod
    def run_remote(vps_cfg, cmd, timeout=30, echo=False):
        """Выполняет команду на удаленном VPS через SSH"""
        ssh_bin = "/opt/bin/ssh"
        if not os.path.exists(ssh_bin):
            ssh_bin = "ssh"
            
        host = vps_cfg.get('VPS_HOST')
        user = vps_cfg.get('VPS_USER', 'root')
        port = vps_cfg.get('VPS_PORT', '22')
        
        ssh_cmd = [
            ssh_bin, 
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            "-o", "LogLevel=ERROR",
            "-i", VPSManager.SSH_KEY,
            "-p", str(port),
            f"{user}@{host}",
            cmd
        ]
        
        try:
            result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=timeout)
            output = (result.stdout + result.stderr).strip()
            if echo and output:
                for line in output.splitlines():
                    print(f"  {DIM}[vps]{NC} {line}")
            
            if result.returncode != 0:
                return False, output
            return True, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return False, "Превышено время ожидания SSH"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def find_vps_by_domain(domain):
        """Ищет VPS, на который указывает домен (аналог из bash)"""
        try:
            ip = socket.gethostbyname(domain)
        except:
            return None

        if not os.path.exists(VPSManager.VPS_DIR):
            return None

        for f in os.listdir(VPSManager.VPS_DIR):
            if f.endswith(".conf"):
                cfg = ConfigManager.load(os.path.join(VPSManager.VPS_DIR, f))
                if cfg.get('VPS_HOST') == ip:
                    return f.replace(".conf", "")
        return None

    @staticmethod
    def setup_vps(vps_cfg):
        """Первичная настройка окружения на удаленном VPS"""
        setup_script = r"""
        export DEBIAN_FRONTEND=noninteractive
        # Создаем директории заранее
        mkdir -p /etc/nginx/sites-enabled
        mkdir -p /etc/nginx/streams-enabled
        
        # Обновление и установка базовых пакетов
        if command -v apt-get >/dev/null 2>&1; then
            apt-get update -qq && apt-get install -y -qq nginx libnginx-mod-stream certbot python3-certbot-nginx psmisc socat curl
        elif command -v yum >/dev/null 2>&1; then
            yum install -y epel-release && yum install -y nginx nginx-mod-stream certbot python3-certbot-nginx psmisc socat curl
        fi

        # Проверка/Настройка nginx.conf для подключения конфигов
        grep -q 'sites-enabled' /etc/nginx/nginx.conf || sed -i '/http {/a\    include /etc/nginx/sites-enabled/*.conf;' /etc/nginx/nginx.conf
        
        if ! grep -q 'streams-enabled' /etc/nginx/nginx.conf; then
            if grep -q 'stream {' /etc/nginx/nginx.conf; then
                 echo "include /etc/nginx/streams-enabled/*.conf;" >> /etc/nginx/nginx.conf
            else
                 printf "\nstream {\n    include /etc/nginx/streams-enabled/*.conf;\n}\n" >> /etc/nginx/nginx.conf
            fi
        fi
        
        systemctl enable nginx && systemctl restart nginx
        
        # Настройка автообновления SSL (cron)
        (crontab -l 2>/dev/null; echo "0 0,12 * * * certbot renew -q --deploy-hook 'systemctl reload nginx'") | sort -u | crontab -
        """
        msg(f"Настройка окружения на VPS {vps_cfg.get('VPS_HOST')}...")
        success, output = VPSManager.run_remote(vps_cfg, setup_script, timeout=300)
        return success, output

    @staticmethod
    def check_ssl_exists(vps_cfg, domain):
        """Проверяет наличие SSL сертификата для домена на VPS"""
        success, _ = VPSManager.run_remote(vps_cfg, f"[ -d /etc/letsencrypt/live/{domain} ]")
        return success

    @staticmethod
    def upload_content(vps_cfg, content, remote_path):
        """Безопасно загружает текстовый контент в файл на VPS через scp"""
        import tempfile
        host = vps_cfg.get('VPS_HOST')
        user = vps_cfg.get('VPS_USER', 'root')
        port = vps_cfg.get('VPS_PORT', '22')
        scp_bin = "/opt/bin/scp"
        if not os.path.exists(scp_bin):
            scp_bin = "scp"

        with tempfile.NamedTemporaryFile(mode='w', delete=False) as tf:
            tf.write(content)
            tf_path = tf.name

        try:
            scp_cmd = [
                scp_bin, "-q", "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "BatchMode=yes",
                "-o", "LogLevel=ERROR",
                "-i", VPSManager.SSH_KEY,
                "-P", str(port),
                tf_path, f"{user}@{host}:{remote_path}"
            ]
            subprocess.run(scp_cmd, check=True)
            return True, ""
        except Exception as e:
            return False, str(e)
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)

    @staticmethod
    def deploy_vhost(vps_cfg, name, content, path="/etc/nginx/sites-enabled"):
        """Деплоит конфиг Nginx на VPS"""
        remote_path = f"{path}/rproxy_{name}.conf"
        success, err_msg = VPSManager.upload_content(vps_cfg, content, remote_path)
        if success:
            res = VPSManager.run_remote(vps_cfg, "nginx -t && systemctl reload nginx", echo=True)
            # res может быть (bool, str) или None при ошибке
            return res if res else (False, "Ошибка выполнения ssh")
        return False, err_msg

    @staticmethod
    def remove_vhost(vps_cfg, name):
        """Удаляет конфиг Nginx с VPS"""
        cmd = f"rm -f /etc/nginx/sites-enabled/rproxy_{name}.conf /etc/nginx/streams-enabled/rproxy_{name}.conf && (nginx -t && systemctl reload nginx || true)"
        return VPSManager.run_remote(vps_cfg, cmd)

    @staticmethod
    def run_certbot(vps_cfg, domain):
        """Запускает Certbot для получения SSL"""
        import re
        is_ip = re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", domain)
        
        profile = "--cert-profile shortlived" if is_ip else ""
        cmd = f"certbot certonly --nginx -d {domain} {profile} --non-interactive --agree-tos --register-unsafely-without-email"
        return VPSManager.run_remote(vps_cfg, cmd, timeout=120)

    @staticmethod
    def cleanup_vps(vps_cfg, active_services):
        """Умная очистка VPS от фантомных конфигов"""
        cmd = "ls /etc/nginx/sites-enabled/rproxy_*.conf /etc/nginx/streams-enabled/rproxy_*.conf 2>/dev/null"
        success, output = VPSManager.run_remote(vps_cfg, cmd)
        if not success or not output:
            return True, "No files found for cleanup"
        
        files = output.splitlines()
        deleted = []
        for f in files:
            # Извлекаем имя из /path/rproxy_NAME.conf
            fname = os.path.basename(f)
            s_name = fname.replace("rproxy_", "").replace(".conf", "")
            if s_name not in active_services:
                VPSManager.run_remote(vps_cfg, f"rm -f {f}")
                deleted.append(fname)
        
        if deleted:
            VPSManager.run_remote(vps_cfg, "nginx -t && systemctl reload nginx")
            return True, f"Deleted: {', '.join(deleted)}"
        return True, "VPS is clean"

    @staticmethod
    def health_check(vps_cfg):
        """Проверка состояния VPS: Nginx, SSL, Certbot"""
        results = {
            'nginx': 'Unknown',
            'ssl_timer': 'Unknown',
            'certs': [] # List of {domains: str, expiry: str, days: int}
        }
        
        # 1. Проверка Nginx
        success, output = VPSManager.run_remote(vps_cfg, "systemctl is-active nginx")
        results['nginx'] = "Запущен" if success and "active" in output else "Остановлен"
        
        # 2. Проверка Certbot Timer
        success, output = VPSManager.run_remote(vps_cfg, "systemctl list-timers | grep certbot")
        if success and "certbot" in output:
            results['ssl_timer'] = "Активен (Systemd)"
            # Пытаемся вытащить дату следующего запуска
            parts = output.split()
            if len(parts) > 1:
                results['next_run'] = f"{parts[0]} {parts[1]}"
        else:
            results['ssl_timer'] = "Не найден"

        # 3. Список сертификатов
        success, output = VPSManager.run_remote(vps_cfg, "certbot certificates")
        if success and "Found the following certs" in output:
            import re
            
            # Парсим сертификаты
            blocks = output.split("Certificate Name:")
            for block in blocks[1:]:
                cert = {}
                domains_match = re.search(r"Domains:\s+(.*)", block)
                expiry_match = re.search(r"Expiry Date:\s+(.*?)\s+\(VALID:\s+(\d+)\s+days\)", block)
                
                if domains_match:
                    cert['domains'] = domains_match.group(1).strip()
                if expiry_match:
                    cert['expiry'] = expiry_match.group(1).strip()
                    cert['days'] = int(expiry_match.group(2))
                
                if cert:
                    results['certs'].append(cert)
                    
        return results
