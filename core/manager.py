import os
import subprocess
import signal
import time
from .utils import msg, warn, err, gen_htpasswd
from .config import ConfigManager
from .vps import VPSManager
from .services import ServiceManager

class ProcessManager:
    """Управление процессами autossh и ttyd"""
    
    PID_DIR = "/opt/var/run/rproxy"
    LOG_DIR = "/opt/var/log"

    @staticmethod
    def is_running(name):
        """Проверяет, запущен ли сервис по PID-файлу"""
        pid_file = os.path.join(ProcessManager.PID_DIR, f"{name}.pid")
        if not os.path.exists(pid_file):
            return False
        
        try:
            with open(pid_file, 'r') as f:
                content = f.read().strip()
                if not content: return False
                pid = int(content)
            os.kill(pid, 0)
            return True
        except (ValueError, OSError, ProcessLookupError):
            if os.path.exists(pid_file):
                os.remove(pid_file)
            return False

    @staticmethod
    def start_service(svc_cfg, vps_cfg):
        """Комплексный запуск сервиса: SSL, Auth, Nginx и Туннель"""
        name = svc_cfg.get('SVC_NAME')
        if ProcessManager.is_running(name):
            msg(f"Сервис '{name}' уже запущен.")
            return True

        os.makedirs(ProcessManager.PID_DIR, exist_ok=True)
        
        # 1. ОБРАБОТКА BASIC AUTH
        auth_user = svc_cfg.get('SVC_AUTH_USER')
        auth_pass = svc_cfg.get('SVC_AUTH_PASS')
        if auth_user and auth_pass:
            msg(f"Генерация доступа для {auth_user}...")
            ht_content = gen_htpasswd(auth_user, auth_pass)
            # Деплоим файл паролей на VPS
            VPSManager.run_remote(vps_cfg, f"echo '{ht_content}' > /etc/nginx/rproxy_{name}.htpasswd")

        # 2. ОБРАБОТКА SSL (CERTBOT)
        domain = svc_cfg.get('SVC_DOMAIN')
        use_ssl = svc_cfg.get('SVC_SSL') == 'yes'
        has_certificate = False
        
        if use_ssl and domain:
            msg(f"Проверка SSL для {domain}...")
            if VPSManager.check_ssl_exists(vps_cfg, domain):
                has_certificate = True
                msg("Сертификат уже существует.")
            else:
                msg("Выпуск нового сертификата через Certbot...")
                # Деплоим временный vhost для валидации
                from .services import ServiceTemplate
                v_content = ServiceTemplate.certbot_validation_vhost(domain)
                VPSManager.deploy_vhost(vps_cfg, name, v_content)
                
                success, output = VPSManager.run_certbot(vps_cfg, domain)
                if success:
                    has_certificate = True
                    msg("SSL сертификат успешно получен.")
                else:
                    err(f"Ошибка Certbot: {output}")
                    # Продолжаем без SSL или отменяем? Оригинал продолжает попытку.

        # 3. ДЕПЛОЙ NGINX
        msg("Деплой конфигурации Nginx...")
        nginx_conf = ServiceManager.generate_conf(svc_cfg, use_ssl_paths=has_certificate)
        nginx_path = ServiceManager.get_nginx_path(svc_cfg.get('SVC_TYPE'))
        VPSManager.deploy_vhost(vps_cfg, name, nginx_conf, path=nginx_path)

        # 4. ЗАПУСК TTYD (если нужно)
        target_host = svc_cfg.get('SVC_TARGET_HOST', '127.0.0.1')
        target_port = svc_cfg.get('SVC_TARGET_PORT')
        
        if svc_cfg.get('SVC_TYPE') == 'ttyd':
            ttyd_port = svc_cfg.get('SVC_TTYD_PORT', 7681)
            msg(f"Запуск веб-терминала ttyd на порту {ttyd_port}...")
            ttyd_cmd = ["ttyd", "-p", str(ttyd_port), "-i", "127.0.0.1", "sh"]
            # Запускаем как демон на роутере
            subprocess.Popen(ttyd_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            target_host = "127.0.0.1"
            target_port = ttyd_port

        # 5. ЗАПУСК ТУННЕЛИ (AUTOSSH)
        remote_tunnel_port = svc_cfg.get('SVC_TUNNEL_PORT')
        vps_host = vps_cfg.get('VPS_HOST')
        vps_user = vps_cfg.get('VPS_USER', 'root')
        vps_port = vps_cfg.get('VPS_PORT', '22')
        ssh_key = "/opt/etc/rproxy/id_ed25519"

        # Генерируем случайный порт мониторинга для autossh (как в оригинале)
        import random
        mon_port = random.randint(20000, 21000)

        cmd = [
            "autossh", "-M", str(mon_port), "-f",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "StrictHostKeyChecking=no",
            "-i", ssh_key,
            "-p", str(vps_port),
            f"-R", f"127.0.0.1:{remote_tunnel_port}:{target_host}:{target_port}",
            f"{vps_user}@{vps_host}"
        ]

        try:
            subprocess.run(cmd, check=True)
            time.sleep(2)
            # Ищем PID
            pgrep = subprocess.run(["pgrep", "-f", f"autossh.*-M {mon_port}"], capture_output=True, text=True)
            if pgrep.returncode == 0:
                pid = pgrep.stdout.strip().split('\n')[0]
                with open(os.path.join(ProcessManager.PID_DIR, f"{name}.pid"), 'w') as f:
                    f.write(pid)
            msg(f"Сервис '{name}' успешно запущен.")
            return True
        except Exception as e:
            err(f"Ошибка при запуске туннеля '{name}': {e}")
            return False

    @staticmethod
    def stop_service(name):
        """Остановка сервиса и очистка ресурсов"""
        pid_file = os.path.join(ProcessManager.PID_DIR, f"{name}.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if ProcessManager.is_running(name):
                    os.kill(pid, signal.SIGKILL)
            except:
                pass
            if os.path.exists(pid_file):
                os.remove(pid_file)
        
        # Остановка ttyd если был
        subprocess.run(["pkill", "-f", "ttyd"], stderr=subprocess.DEVNULL)
        msg(f"Сервис '{name}' остановлен.")
        return True
