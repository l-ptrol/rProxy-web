import os
import subprocess
import signal
import time
from .utils import msg, warn, err
from .config import ConfigManager

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
                pid = int(f.read().strip())
            # Проверяем наличие процесса (сигнал 0 не убивает процесс)
            os.kill(pid, 0)
            return True
        except (ValueError, OSError, ProcessLookupError):
            # Если процесса нет, удаляем "протухший" PID-файл
            if os.path.exists(pid_file):
                os.remove(pid_file)
            return False

    @staticmethod
    def start_service(svc_cfg, vps_cfg):
        """Запуск SSH-туннеля через autossh"""
        name = svc_cfg.get('SVC_NAME')
        if ProcessManager.is_running(name):
            msg(f"Сервис '{name}' уже запущен.")
            return True

        os.makedirs(ProcessManager.PID_DIR, exist_ok=True)
        os.makedirs(ProcessManager.LOG_DIR, exist_ok=True)
        
        # Параметры туннеля
        local_port = svc_cfg.get('SVC_TARGET_PORT')
        local_host = svc_cfg.get('SVC_TARGET_HOST', '127.0.0.1')
        remote_tunnel_port = svc_cfg.get('SVC_TUNNEL_PORT')
        
        vps_host = vps_cfg.get('VPS_HOST')
        vps_user = vps_cfg.get('VPS_USER', 'root')
        vps_port = vps_cfg.get('VPS_PORT', '22')
        ssh_key = "/opt/etc/rproxy/id_ed25519"

        # Формируем команду autossh
        # -M 0: отключаем мониторинг порта autossh (используем встроенный в ssh)
        # -N: не выполнять удаленную команду
        # -R: обратный туннель
        cmd = [
            "autossh", "-M", "0", "-f",
            "-o", "ConnectTimeout=10",
            "-o", "ServerAliveInterval=30",
            "-o", "ServerAliveCountMax=3",
            "-o", "ExitOnForwardFailure=yes",
            "-o", "StrictHostKeyChecking=no",
            "-i", ssh_key,
            "-p", str(vps_port),
            f"-R", f"127.0.0.1:{remote_tunnel_port}:{local_host}:{local_port}",
            f"{vps_user}@{vps_host}"
        ]

        try:
            msg(f"Запуск туннеля для '{name}'...")
            subprocess.run(cmd, check=True)
            
            # Нам нужно найти PID запущенного процесса. 
            # Поскольку autossh с флагом -f уходит в бэкграунд, 
            # мы попробуем найти его через pgrep или похожие утилиты.
            # В оригинальном скрипте PID сохраняется самой системой или через pgrep.
            time.sleep(1)
            # Упрощенно для примера (в реальности лучше использовать обертку)
            pgrep = subprocess.run(["pgrep", "-f", f"rproxy.*{name}"], capture_output=True, text=True)
            if pgrep.returncode == 0:
                pid = pgrep.stdout.strip().split('\n')[0]
                with open(os.path.join(ProcessManager.PID_DIR, f"{name}.pid"), 'w') as f:
                    f.write(pid)
            return True
        except Exception as e:
            err(f"Ошибка при запуске сервиса '{name}': {e}")
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
        
        # Дополнительная очистка через pkill (на всякий случай)
        subprocess.run(["pkill", "-9", "-f", f"rproxy.*{name}"], stderr=subprocess.DEVNULL)
        msg(f"Сервис '{name}' остановлен.")
        return True
