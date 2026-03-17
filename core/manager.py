import os
import time
import subprocess
import signal
import time
import sys
import shutil
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
        if shutil.which('fuser'):
            subprocess.run(["fuser", "-k", f"{port}/tcp"], stderr=subprocess.DEVNULL)
        time.sleep(1)

        # Проверка наличия ttyd
        if not shutil.which('ttyd'):
            msg("ttyd не найден. Пытаюсь установить автоматически через opkg...")
            try:
                # Обновляем списки и ставим ttyd
                subprocess.run(["opkg", "update"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["opkg", "install", "ttyd"], check=True)
                if not shutil.which('ttyd'):
                    err("Не удалось установить ttyd автоматически. Установите его вручную: opkg install ttyd")
                    return False
                msg("ttyd успешно установлен.")
            except Exception as e:
                err(f"Ошибка при автоматической установке ttyd: {e}")
                return False

        watchdog_script = f"""
import subprocess, time, os, signal, traceback, sys
def run():
    log_path = '{log_file}'
    with open(log_path, 'a') as f:
        f.write(f'\\n--- Watchdog started at {{time.ctime()}} (PID: {{os.getpid()}}) ---\\n')
        f.flush()
    
    while True:
        try:
            # Запуск ttyd на 0.0.0.0
            with open(log_path, 'a') as f:
                f.write(f'[{{time.ctime()}}] Starting ttyd on port {port}...\\n')
                f.flush()
            # Проверка бинарника прямо перед запуском
            import shutil as sh
            binary = sh.which('ttyd')
            with open(log_path, 'a') as f:
                f.write(f'[{{time.ctime()}}] Binary check: {{binary}}\\n')
                f.flush()
            
            if not binary:
                with open(log_path, 'a') as f:
                    f.write(f'[{{time.ctime()}}] ERROR: ttyd not found in PATH!\\n')
                    f.flush()
                time.sleep(5)
                continue

            proc = subprocess.Popen(['ttyd', '-W', '--max-clients', '10', '-i', '0.0.0.0', '-p', '{port}', '--', '{cmd}'], 
                                     stdout=open(log_path, 'a'), stderr=subprocess.STDOUT)
            proc.wait()
            
            with open(log_path, 'a') as f:
                f.write(f'[{{time.ctime()}}] ttyd stopped with exit code {{proc.returncode}}\\n')
                if proc.returncode != 0:
                    f.write(f'Check if port {port} is already in use or binary is compatible.\\n')
                f.write('Restarting ttyd in 2 seconds...\\n')
                f.flush()
        except Exception as e:
            with open(log_path, 'a') as f:
                f.write(f'[{{time.ctime()}}] Watchdog fatal error: {{e}}\\n')
                f.write(traceback.format_exc())
                f.flush()
        time.sleep(2)
if __name__ == "__main__":
    run()
"""
        # Запускаем watchdog как независимый процесс
        try:
            # Направляем вывод самого процесса watchdog в тот же лог для отладки ошибок Python
            log_handle = open(log_file, 'a')
            proc = subprocess.Popen([sys.executable, '-c', watchdog_script], 
                                     stdout=log_handle, stderr=subprocess.STDOUT,
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
        if shutil.which('fuser'):
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
            if success:
                # Устанавливаем права 644, чтобы Nginx мог прочитать файл
                VPSManager.run_remote(vps_cfg, f"chmod 644 /etc/nginx/rproxy_{name}.htpasswd")
            else:
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
            ttyd_port = svc_cfg.get('SVC_TARGET_PORT', 7681)
            ttyd_cmd = svc_cfg.get('SVC_TTYD_CMD', 'login')
            if ProcessManager.start_ttyd(ttyd_port, ttyd_cmd, name):
                target_host = "127.0.0.1"
                target_port = ttyd_port
            else:
                log_path = os.path.join(ProcessManager.LOG_DIR, f"ttyd_{name}.log")
                err(f"Не удалось запустить ttyd. Подробности см. в логе: {log_path}")
                return False

        # 5. ЗАПУСК ТУННЕЛИ (AUTOSSH)
        remote_tunnel_port = svc_cfg.get('SVC_TUNNEL_PORT')
        vps_host = vps_cfg.get('VPS_HOST')
        vps_user = vps_cfg.get('VPS_USER', 'root')
        vps_port = vps_cfg.get('VPS_PORT', '22')
        ssh_key = "/opt/etc/rproxy/id_ed25519"

        import random
        mon_port = random.randint(20000, 21000)

        # 5.1 СПЕЦИФИКАЦИЯ ТУННЕЛЯ
        tunnel_spec = f"0.0.0.0:{remote_tunnel_port}:{target_host}:{target_port}"
        if svc_cfg.get('SVC_TYPE') == 'udp':
            # Для UDP пробрасываем порт туннеля для моста socat
            tunnel_spec = f"{remote_tunnel_port}:127.0.0.1:{remote_tunnel_port}"

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
            f"-R", tunnel_spec,
            f"{vps_user}@{vps_host}"
        ]

        try:
            msg(f"Запуск туннеля '{name}' (Target: {target_host}:{target_port})...")
            # Остановка старого процесса если есть
            ProcessManager.stop_service(name, svc_cfg=svc_cfg)
            
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
                
                # 6. ДЕПЛОЙ NGINX / UDP BRIDGE
                if svc_cfg.get('SVC_TYPE') == 'udp':
                    # Для UDP запускаем мост
                    msg("Подготовка UDP-TCP моста...")
                    
                    ext_port = svc_cfg.get('SVC_EXT_PORT')
                    
                    # 1. Проверка/Установка socat на VPS
                    msg("Проверка socat на VPS...")
                    s_soc, _ = VPSManager.run_remote(vps_cfg, "which socat")
                    if not s_soc:
                        warn("socat не найден на VPS. Установка...")
                        VPSManager.run_remote(vps_cfg, "apt-get update && apt-get install -y socat || yum install -y socat")

                    # 2. Запуск на VPS (UDP -> TCP)
                    # Используем полный путь если возможно
                    socat_path_vps = "socat"
                    socat_cmd_vps = f"nohup {socat_path_vps} UDP4-LISTEN:{ext_port},fork,reuseaddr TCP4:127.0.0.1:{remote_tunnel_port} > /dev/null 2>&1 &"
                    msg(f"Запуск socat на VPS (Порт {ext_port} UDP -> {remote_tunnel_port} TCP)...")
                    VPSManager.run_remote(vps_cfg, f"pkill -f 'UDP4-LISTEN:{ext_port}' ; {socat_cmd_vps}")
                    
                    # 3. Запуск на Роутере (TCP -> UDP)
                    msg("Запуск socat на роутере...")
                    socat_path_router = "/opt/bin/socat" if os.path.exists("/opt/bin/socat") else "socat"
                    # Важно: pkill завершаем успешно (|| true), чтобы не прерывать цепочку
                    bash_cmd = f"pkill -f 'TCP4-LISTEN:{remote_tunnel_port}' || true; nohup {socat_path_router} TCP4-LISTEN:{remote_tunnel_port},fork,reuseaddr UDP4:{target_host}:{target_port} > /dev/null 2>&1 &"
                    subprocess.Popen(["sh", "-c", bash_cmd], start_new_session=True)
                else:
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
                msg(f"Сервис '{name}' успешно проброшен!")
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
            
            # 3. SOCAT (UDP мост)
            if svc_cfg.get('SVC_TYPE') == 'udp':
                t_port = svc_cfg.get('SVC_TARGET_PORT')
                ext_port = svc_cfg.get('SVC_EXT_PORT')
                tun_port = svc_cfg.get('SVC_TUNNEL_PORT')
                v_id = svc_cfg.get('SVC_VPS')
                v_path = os.path.join("/opt/etc/rproxy/vps", f"{v_id}.conf")
                if os.path.exists(v_path):
                    v_cfg = ConfigManager.load(v_path)
                    VPSManager.run_remote(v_cfg, f"pkill -f 'UDP4-LISTEN:{ext_port}'")
                subprocess.run(["pkill", "-f", f"TCP4-LISTEN:{tun_port}"], stderr=subprocess.DEVNULL)
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
            msg(f"Принудительный перезапуск сервиса...")
            # Сначала полностью останавливаем, затем запускаем
            ProcessManager.stop_service(name)
            time.sleep(1)
            ProcessManager.start_service(svc_cfg, vps_cfg)
        else:
            err(f"Ошибка при обновлении Nginx: {output}")
        return success

    @staticmethod
    def test_service(svc_cfg, vps_cfg):
        """Диагностика работоспособности сервиса"""
        name = svc_cfg.get('SVC_NAME')
        svc_type = svc_cfg.get('SVC_TYPE')
        msg(f"Тестирование сервиса '{name}' ({svc_type})...")
        
        # 1. Проверка SSH туннеля
        is_ssh = ProcessManager.is_running(name)
        status = f"{GREEN}ЗАПУЩЕН{NC}" if is_ssh else f"{RED}НЕ ЗАПУЩЕН{NC}"
        print(f"  - SSH Туннель (autossh): {status}")
        
        # 2. Проверка VPS
        success, output = VPSManager.run_remote(vps_cfg, "echo 1")
        vps_status = f"{GREEN}ДОСТУПЕН{NC}" if success else f"{RED}ОШИБКА: {output}{NC}"
        print(f"  - Доступность VPS: {vps_status}")
        
        # 3. Специфичные проверки для UDP
        if svc_type == 'udp':
            msg("Проверка UDP-over-TCP моста...")
            t_port = svc_cfg.get('SVC_TARGET_PORT')
            ext_port = svc_cfg.get('SVC_EXT_PORT')
            tun_port = svc_cfg.get('SVC_TUNNEL_PORT')
            
            # Проверка socat в системе
            import shutil
            if not shutil.which('socat'):
                err("socat НЕ НАЙДЕН на роутере! Выполните opkg install socat")
            
            # Проверка socat на роутере (слушает порт туннеля)
            pgrep_socat = subprocess.run(["pgrep", "-f", f"TCP4-LISTEN:{tun_port}"], capture_output=True, text=True)
            s_status = f"{GREEN}ЗАПУЩЕН{NC}" if pgrep_socat.returncode == 0 else f"{RED}НЕ ЗАПУЩЕН{NC}"
            print(f"  - Мост на роутере (socat): {s_status}")
            
            # Проверка socat на VPS
            has_soc_vps, _ = VPSManager.run_remote(vps_cfg, "which socat")
            if not has_soc_vps:
                print(f"  - Мост на VPS (socat): {RED}КОМАНДА SOCAT НЕ НАЙДЕНА{NC}")
            else:
                s_vps, o_vps = VPSManager.run_remote(vps_cfg, f"pgrep -f 'UDP4-LISTEN:{ext_port}'")
                sv_status = f"{GREEN}ЗАПУЩЕН{NC}" if s_vps and o_vps else f"{RED}ОСТАНОВЛЕН{NC}"
                print(f"  - Мост на VPS (socat): {sv_status}")
            
            # Проверка WireGuard порта на роутере
            try:
                # Пробуем найти кто слушает UDP порт
                ns = subprocess.run(["netstat", "-unlp"], capture_output=True, text=True)
                if f":{t_port}" in ns.stdout:
                    print(f"  - Порт {t_port} (UDP): {GREEN}СЛУШАЕТСЯ (WireGuard активен){NC}")
                else:
                    warn(f"Порт {t_port} (UDP) не найден в netstat. Убедитесь, что WireGuard включен на роутере!")
            except: pass
        
        # 4. Проверка Nginx на VPS
        if svc_type in ['http', 'tcp', 'ssh']:
            s_ng, _ = VPSManager.run_remote(vps_cfg, f"ls /etc/nginx/*/rproxy_{name}.conf")
            ng_status = f"{GREEN}АКТИВЕН{NC}" if s_ng else f"{RED}НЕ НАЙДЕН{NC}"
            print(f"  - Конфигурация Nginx: {ng_status}")

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
        paths = ["/opt/etc/rproxy", "/opt/var/run/rproxy", "/opt/share/rproxy-web"]
        for p in paths:
            if os.path.exists(p):
                if os.path.isdir(p): shutil.rmtree(p)
                else: os.remove(p)
        
        msg("Система очищена. Перезапустите инсталлятор для новой настройки.")
        sys.exit(0)
