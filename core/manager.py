import os
import subprocess
import signal
import time
import sys
from .utils import msg, warn, err, gen_htpasswd, RED, NC
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
    def start_ttyd(port, cmd, name):
        """Запуск ttyd с Watchdog-механизмом (авторестарт)"""
        pid_file = os.path.join(ProcessManager.PID_DIR, f"ttyd_{name}.pid")
        log_file = os.path.join(ProcessManager.LOG_DIR, f"ttyd_{name}.log")
        
        # Очистка старых процессов
        ProcessManager.stop_ttyd(name)
        
        watchdog_script = f"""
import subprocess, time, os, signal
def run():
    while True:
        try:
            # Запуск ttyd
            proc = subprocess.Popen(['ttyd', '-W', '--max-clients', '10', '-i', '127.0.0.1', '-p', '{port}', '--', '{cmd}'], 
                                     stdout=open('{log_file}', 'a'), stderr=subprocess.STDOUT)
            proc.wait()
        except Exception as e:
            with open('{log_file}', 'a') as f: f.write(f'Watchdog error: {{e}}\\n')
        time.sleep(2)
run()
"""
        # Запускаем watchdog как независимый процесс
        try:
            proc = subprocess.Popen([sys.executable, '-c', watchdog_script], 
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     start_new_session=True)
            with open(pid_file, 'w') as f:
                f.write(str(proc.pid))
            
            # Верификация порта
            for _ in range(5):
                from .utils import is_port_busy
                if is_port_busy(port): return True
                time.sleep(1)
            return False
        except Exception as e:
            err(f"Ошибка запуска TTYD Watchdog: {e}")
            return False

    @staticmethod
    def stop_ttyd(name):
        """Остановка Watchdog и процесса ttyd"""
        pid_file = os.path.join(ProcessManager.PID_DIR, f"ttyd_{name}.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
            except: pass
            os.remove(pid_file)
        
        # Агрессивно прибиваем ttyd на конкретном порту через pkill/fuser если нужно
        # Но в идеале watchdog сам должен был это делать. Здесь просто pkill для надежности.
        subprocess.run(["pkill", "-9", "-f", f"ttyd.*{name}"], stderr=subprocess.DEVNULL)

    @staticmethod
    def start_service(svc_cfg, vps_cfg):
        """Комплексный запуск сервиса: SSL, Auth, Nginx и Туннель"""
        name = svc_cfg.get('SVC_NAME')
        if ProcessManager.is_running(name):
            msg(f"Сервис '{name}' уже запущен.")
            return True

        os.makedirs(ProcessManager.PID_DIR, exist_ok=True)
        os.makedirs(ProcessManager.LOG_DIR, exist_ok=True)
        
        # 1. ОБРАБОТКА BASIC AUTH
        auth_user = svc_cfg.get('SVC_AUTH_USER')
        auth_pass = svc_cfg.get('SVC_AUTH_PASS')
        if auth_user and auth_pass:
            msg(f"Генерация доступа для {auth_user}...")
            ht_content = gen_htpasswd(auth_user, auth_pass)
            VPSManager.run_remote(vps_cfg, f"echo '{ht_content}' > /etc/nginx/rproxy_{name}.htpasswd", echo=True)

        # 2. ОБРАБОТКА SSL (CERTBOT)
        domain = svc_cfg.get('SVC_DOMAIN')
        use_ssl = svc_cfg.get('SVC_SSL') == 'yes'
        has_certificate = False
        
        if use_ssl and domain:
            if VPSManager.check_ssl_exists(vps_cfg, domain):
                has_certificate = True
            else:
                msg("Выпуск нового сертификата через Certbot...")
                from .services import ServiceTemplate
                v_content = ServiceTemplate.certbot_validation_vhost(domain)
                VPSManager.deploy_vhost(vps_cfg, name, v_content)
                success, output = VPSManager.run_certbot(vps_cfg, domain)
                if success:
                    has_certificate = True
                else:
                    warn(f"Certbot не смог выпустить сертификат: {output}")

        # 3. ДЕПЛОЙ NGINX
        nginx_conf = ServiceManager.generate_conf(svc_cfg, use_ssl_paths=has_certificate)
        nginx_path = ServiceManager.get_nginx_path(svc_cfg.get('SVC_TYPE'))
        VPSManager.deploy_vhost(vps_cfg, name, nginx_conf, path=nginx_path)

        # 4. ЗАПУСК TTYD (если нужно)
        target_host = svc_cfg.get('SVC_TARGET_HOST', '127.0.0.1')
        target_port = svc_cfg.get('SVC_TARGET_PORT')
        
        if svc_cfg.get('SVC_TYPE') == 'ttyd':
            ttyd_port = svc_cfg.get('SVC_TTYD_PORT', 7681)
            ttyd_cmd = svc_cfg.get('SVC_TTYD_CMD', 'login')
            if ProcessManager.start_ttyd(ttyd_port, ttyd_cmd, name):
                target_host = "127.0.0.1"
                target_port = ttyd_port
            else:
                err("Не удалось запустить ttyd.")
                return False

        # 5. ЗАПУСК ТУННЕЛИ (AUTOSSH)
        remote_tunnel_port = svc_cfg.get('SVC_TUNNEL_PORT')
        vps_host = vps_cfg.get('VPS_HOST')
        vps_user = vps_cfg.get('VPS_USER', 'root')
        vps_port = vps_cfg.get('VPS_PORT', '22')
        ssh_key = "/opt/etc/rproxy/id_ed25519"

        import random
        mon_port = random.randint(20000, 21000)

        cmd = [
            "autossh", "-M", str(mon_port), "-f", "-N",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "StrictHostKeyChecking=no",
            "-i", ssh_key,
            "-p", str(vps_port),
            f"-R", f"0.0.0.0:{remote_tunnel_port}:{target_host}:{target_port}",
            f"{vps_user}@{vps_host}"
        ]

        try:
            msg(f"Запуск туннеля '{name}' (Mon:{mon_port})...")
            subprocess.run(cmd, check=True)
            time.sleep(2)
            # Ищем PID
            pgrep = subprocess.run(["pgrep", "-f", f"autossh.*-M {mon_port}"], capture_output=True, text=True)
            pid = ""
            if pgrep.returncode == 0:
                pid = pgrep.stdout.strip().split('\n')[0]
                with open(os.path.join(ProcessManager.PID_DIR, f"{name}.pid"), 'w') as f:
                    f.write(pid)
            msg(f"Сервис '{name}' запущен (PID: {pid}).")
            return True
        except Exception as e:
            err(f"Ошибка при запуске туннеля '{name}': {e}")
            return False

    @staticmethod
    def stop_service(name):
        """Остановка сервиса и очистка ресурсов"""
        # 1. Туннель
        pid_file = os.path.join(ProcessManager.PID_DIR, f"{name}.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
                time.sleep(1)
                if ProcessManager.is_running(name):
                    os.kill(pid, signal.SIGKILL)
            except: pass
            if os.path.exists(pid_file): os.remove(pid_file)
        
        # 2. TTYD
        ProcessManager.stop_ttyd(name)
        
        msg(f"Сервис '{name}' остановлен.")
        return True

    @staticmethod
    def self_update():
        """Самообновление через загрузку и запуск инсталлера"""
        url = "https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/install.sh"
        msg("Загрузка обновления...")
        cmd = f"curl -sL {url} -o /tmp/rproxy_update.sh && sh /tmp/rproxy_update.sh"
        try:
            # Запускаем в новом процессе, так как текущий будет убит инсталлером
            subprocess.Popen(["sh", "-c", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            msg("Инсталлятор запущен. Сессия будет перезапущена.")
            return True
        except Exception as e:
            err(f"Ошибка обновления: {e}")
            return False

    @staticmethod
    def hard_reset():
        """Полная очистка всех конфигураций и данных rProxy"""
        confirm = input(f"\n{RED}ВНИМАНИЕ! Это удалит ВСЕ настройки и ключи. Продолжить? (y/n): {NC}")
        if confirm.lower() != 'y': return False
        
        msg("Выполнение глубокой очистки...")
        # Останавливаем всё
        subprocess.run(["pkill", "-f", "autossh"], stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "ttyd"], stderr=subprocess.DEVNULL)
        
        # Удаляем директории
        import shutil
        paths = ["/opt/etc/rproxy", "/opt/var/run/rproxy", "/opt/share/rproxy-web"]
        for p in paths:
            if os.path.exists(p):
                if os.path.isdir(p): shutil.rmtree(p)
                else: os.remove(p)
        
        msg("Система очищена. Перезапустите инсталлятор для новой настройки.")
        sys.exit(0)
