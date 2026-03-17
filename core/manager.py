import os
import time
import subprocess
import signal
import time
import sys
from .utils import msg, warn, err, gen_htpasswd, RED, GREEN, YELLOW, CYAN, NC, DIM
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
        pid_file = os.path.join(ProcessManager.PID_DIR, f"ttyd_{port}.pid")
        log_file = os.path.join(ProcessManager.LOG_DIR, f"ttyd_{name}.log")
        
        # Очистка старых процессов на этом порту
        ProcessManager.stop_ttyd(port)
        
        # Агрессивная очистка порта перед запуском (как в Bash)
        subprocess.run(["fuser", "-k", f"{port}/tcp"], stderr=subprocess.DEVNULL)
        time.sleep(1)

        watchdog_script = f"""
import subprocess, time, os, signal
def run():
    while True:
        try:
            # Запуск ttyd на 0.0.0.0 (как в оригинале)
            proc = subprocess.Popen(['ttyd', '-W', '--max-clients', '10', '-i', '0.0.0.0', '-p', '{port}', '--', '{cmd}'], 
                                     stdout=open('{log_file}', 'a'), stderr=subprocess.STDOUT)
            proc.wait()
        except Exception as f:
            pass
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
            from .utils import is_port_busy
            for _ in range(5):
                if is_port_busy(port): return True
                time.sleep(1)
            return False
        except Exception as e:
            err(f"Ошибка запуска TTYD Watchdog: {e}")
            return False

    @staticmethod
    def stop_ttyd(port):
        """Остановка Watchdog и процесса ttyd по порту"""
        pid_file = os.path.join(ProcessManager.PID_DIR, f"ttyd_{port}.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                os.kill(pid, signal.SIGTERM)
            except: pass
            os.remove(pid_file)
        
        # Агрессивно прибиваем ttyd на конкретном порту (как в Bash)
        subprocess.run(["pkill", "-9", "-f", f"ttyd.*-p {port}"], stderr=subprocess.DEVNULL)
        subprocess.run(["fuser", "-k", f"{port}/tcp"], stderr=subprocess.DEVNULL)

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
            success, ht_err = VPSManager.upload_content(vps_cfg, ht_content + "\n", f"/etc/nginx/rproxy_{name}.htpasswd")
            if not success:
                warn(f"Не удалось загрузить файл авторизации: {ht_err}")

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
                # Сначала деплоим базовый конфиг на 80 порт для Certbot
                v_content = ServiceTemplate.certbot_validation_vhost(domain)
                VPSManager.deploy_vhost(vps_cfg, name, v_content)
                success, output = VPSManager.run_certbot(vps_cfg, domain)
                if success:
                    has_certificate = True
                else:
                    warn(f"Certbot не смог выпустить сертификат: {output}")

        # 3. ПОДГОТОВКА ПАРАМЕТРОВ (Деплой будет после запуска туннеля)
        nginx_path = ServiceManager.get_nginx_path(svc_cfg.get('SVC_TYPE'))

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

        # Настройка окружения для autossh
        env = os.environ.copy()
        env["AUTOSSH_GATETIME"] = "0"
        env["AUTOSSH_PATH"] = "/opt/bin/ssh" if os.path.exists("/opt/bin/ssh") else "ssh"

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
            msg(f"Запуск туннеля '{name}' (Target: {target_host}:{target_port})...")
            # Остановка старого процесса если есть
            ProcessManager.stop_service(name)
            
            subprocess.run(cmd, check=True, env=env)
            
            max_wait = 20
            started = False
            for i in range(max_wait):
                time.sleep(1)
                # Проверяем PID через pgrep
                pgrep = subprocess.run(["pgrep", "-f", f"autossh.*-M {mon_port}"], capture_output=True, text=True)
                if pgrep.returncode == 0:
                    pid = pgrep.stdout.strip().split('\n')[0]
                    with open(os.path.join(ProcessManager.PID_DIR, f"{name}.pid"), 'w') as f:
                        f.write(pid)
                    
                    # Проверяем, что процесс живой
                    try:
                        os.kill(int(pid), 0)
                        started = True
                        break
                    except OSError: pass
                
            if started:
                # Даем время на установку SSH соединения
                msg(f"Туннель '{name}' запущен (PID: {pid}). Ожидание сетевой готовности...")
                time.sleep(4) 
                
                # 6. ДЕПЛОЙ NGINX (Теперь, когда порт точно слушается autossh)
                # Всегда сначала деплоим актуальный конфиг (с SSL или без)
                use_ssl_final = has_certificate and use_ssl
                msg(f"Применение конфигурации Nginx (SSL: {use_ssl_final})...")
                nginx_conf = ServiceManager.generate_conf(svc_cfg, use_ssl_paths=use_ssl_final)
                
                # Перед деплоем удалим старые конфиги с таким же именем (чтобы не было конфликтов)
                msg(f"Проверка конфликтов конфигурации...")
                VPSManager.run_remote(vps_cfg, f"rm -f /etc/nginx/sites-enabled/rproxy_{name}.conf /etc/nginx/streams-enabled/rproxy_{name}.conf")
                
                success, output = VPSManager.deploy_vhost(vps_cfg, name, nginx_conf, path=nginx_path)
                if not success:
                    warn(f"Nginx reload warning: {output}")
                
                msg(f"Туннель '{name}' запущен {DIM}(PID: {pid}, MonPort: {mon_port}){NC}")
                msg(f"Сервис '{name}' успешно проброшен! 502 ошибка устранена.")
                return True
            else:
                err(f"Туннель '{name}' не запустился за {max_wait} сек.")
                return False
        except Exception as e:
            err(f"Ошибка при запуске туннеля '{name}': {e}")
            return False

    @staticmethod
    def stop_service(name, svc_cfg=None):
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
        if svc_cfg:
            ttyd_port = svc_cfg.get('SVC_TTYD_PORT', 7681)
            ProcessManager.stop_ttyd(ttyd_port)
        else:
            # Если конфига нет, пробуем убить по стандартному порту (для очистки)
            ProcessManager.stop_ttyd(7681)
        
        msg(f"Сервис '{name}' остановлен.")
        return True

    @staticmethod
    def run_certbot(svc_cfg, vps_cfg):
        """Ручной запуск выпуска сертификата через Certbot"""
        name = svc_cfg.get('SVC_NAME')
        domain = svc_cfg.get('SVC_DOMAIN')
        if not domain:
            warn(f"Сервис '{name}' не имеет домена.")
            return False
            
        msg(f"Запуск Certbot для домена '{domain}'...")
        success, output = VPSManager.run_certbot(vps_cfg, domain)
        if success:
            msg(f"Сертификат для '{domain}' успешно получен.")
            # Передеплоим конфиг Nginx, так как теперь SSL файлы точно на месте
            ProcessManager.redeploy_nginx(svc_cfg, vps_cfg)
        else:
            err(f"Ошибка Certbot: {output}")
        return success

    @staticmethod
    def redeploy_nginx(svc_cfg, vps_cfg):
        """Перезапись конфигурации Nginx без остановки туннеля"""
        name = svc_cfg.get('SVC_NAME')
        domain = svc_cfg.get('SVC_DOMAIN')
        use_ssl = svc_cfg.get('SVC_SSL') == 'yes'
        
        msg(f"Перезапись конфигурации Nginx для '{name}'...")
        
        # 1. Проверяем наличие сертификата для SSL
        has_certificate = False
        if use_ssl and domain:
             has_certificate = VPSManager.check_ssl_exists(vps_cfg, domain)
        
        # 2. Деплоим конфиг
        nginx_conf = ServiceManager.generate_conf(svc_cfg, use_ssl_paths=has_certificate)
        nginx_path = ServiceManager.get_nginx_path(svc_cfg.get('SVC_TYPE'))
        
        success, output = VPSManager.deploy_vhost(vps_cfg, name, nginx_conf, path=nginx_path)
        if success:
            msg(f"Конфигурация Nginx для '{name}' успешно обновлена.")
        else:
            err(f"Ошибка при обновлении Nginx: {output}")
        return success

    @staticmethod
    def self_update():
        """Самообновление через загрузку и запуск инсталлера"""
        url = "https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/install.sh"
        msg("Запуск процесса обновления...")
        
        # Мы используем nohup и фоновый запуск, чтобы инсталлер выжил после выхода из текущего процесса
        # Также добавляем вывод в лог для отладки
        updater_cmd = f"curl -sL {url} -o /tmp/rproxy_update.sh && sh /tmp/rproxy_update.sh"
        
        try:
            print(f"\n{CYAN}▸{NC} Загрузка и запуск инсталлера...")
            # Запускаем через os.system для немедленного выполнения команды в текущем окружении перед выходом
            # Но так как инсталлер убьет этот процесс, используем конструкцию, которая позволит ему продолжить работу
            os.system(f"nohup sh -c '{updater_cmd}' > /opt/var/log/rproxy_updater.log 2>&1 &")
            msg("Инсталлер запущен в фоне. Сессия будет прервана.")
            msg("Лог обновления: /opt/var/log/rproxy_updater.log")
            time.sleep(1)
            sys.exit(0)
        except Exception as e:
            err(f"Ошибка при запуске обновления: {e}")
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
