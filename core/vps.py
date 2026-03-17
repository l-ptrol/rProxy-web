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
        setup_script = """
        if ! command -v nginx >/dev/null 2>&1; then
            apt-get update -qq && apt-get install -y -qq nginx psmisc || (yum update -y && yum install -y nginx psmisc)
        else
            apt-get update -qq && apt-get install -y -qq psmisc || yum install -y psmisc
        fi
        mkdir -p /etc/nginx/sites-enabled
        grep -q 'sites-enabled' /etc/nginx/nginx.conf || sed -i '/http {/a\    include /etc/nginx/sites-enabled/*.conf;' /etc/nginx/nginx.conf
        command -v certbot >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq certbot python3-certbot-nginx || yum install -y certbot python3-certbot-nginx)
        
        # Настройка Nginx Stream
        mkdir -p /etc/nginx/streams-enabled
        if ! grep -q 'streams-enabled' /etc/nginx/nginx.conf; then
            if grep -q 'stream {' /etc/nginx/nginx.conf; then
                 echo "include /etc/nginx/streams-enabled/*.conf;" >> /etc/nginx/nginx.conf
            else
                 printf "\\nstream {\\n    include /etc/nginx/streams-enabled/*.conf;\\n}\\n" >> /etc/nginx/nginx.conf
            fi
        fi
        systemctl enable nginx && systemctl start nginx
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
            return VPSManager.run_remote(vps_cfg, "nginx -t && systemctl reload nginx", echo=True)
        return False, err_msg

    @staticmethod
    def run_certbot(vps_cfg, domain):
        """Запускает Certbot для получения SSL"""
        cmd = f"certbot certonly --nginx -d {domain} --non-interactive --agree-tos --register-unsafely-without-email"
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
        """Проверка состояния VPS: Nginx, Диск, Доступность"""
        results = []
        # 1. Проверка Nginx
        success, output = VPSManager.run_remote(vps_cfg, "systemctl is-active nginx")
        nginx_status = f"{GREEN}Active{NC}" if success and "active" in output else f"{RED}Inactive{NC}"
        results.append(f"Nginx: {nginx_status}")
        
        # 2. Проверка диска
        success, output = VPSManager.run_remote(vps_cfg, "df -h / | tail -1 | awk '{print $4}'")
        disk_space = output.strip() if success else "Error"
        results.append(f"Free Disk: {CYAN}{disk_space}{NC}")
        
        # 3. ОС версия (кратко)
        success, output = VPSManager.run_remote(vps_cfg, "cat /etc/os-release | grep PRETTY_NAME | cut -d'\"' -f2")
        os_ver = output.strip() if success else "Unknown"
        results.append(f"OS: {DIM}{os_ver}{NC}")
        
        return True, " | ".join(results)
