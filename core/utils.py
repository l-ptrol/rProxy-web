# rProxy Core Utilities
import sys

# Цвета для терминала
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
BOLD = '\033[1m'
DIM = '\033[2m'
NC = '\033[0m'

def _resolve_bin(name):
    """Находит абсолютный путь к бинарнику (Entware priority)"""
    import os
    paths = ["/opt/bin", "/opt/sbin", "/usr/bin", "/usr/sbin", "/bin", "/sbin"]
    for p in paths:
        full = os.path.join(p, name)
        if os.path.exists(full):
            return full
    return name

def _get_ssh_type(bin_path):
    """Определяет, является ли бинарник OpenSSH или Dropbear (dbclient)"""
    import subprocess
    try:
        proc = subprocess.run([bin_path, "-V"], capture_output=True, text=True)
        if "Dropbear" in (proc.stdout + proc.stderr):
            return "dropbear"
    except: pass
    
    try:
        proc = subprocess.run([bin_path, "-h"], capture_output=True, text=True)
        if "dbclient" in (proc.stdout + proc.stderr) or "Dropbear" in (proc.stdout + proc.stderr):
            return "dropbear"
    except: pass
    
    return "openssh"

def _get_ssh_args(bin_path, host, user, port, key_path=None, scp=False):
    """Формирует список аргументов в зависимости от типа SSH-клиента"""
    ssh_type = _get_ssh_type(bin_path)
    args = []
    
    if ssh_type == "dropbear":
        args.append("-y") # Accept host key
        if key_path:
            args.extend(["-i", key_path])
        if scp:
            args.extend(["-P", str(port)])
        else:
            args.extend(["-p", str(port)])
    else:
        args.extend([
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "BatchMode=yes" if key_path else "BatchMode=no",
            "-o", "ConnectTimeout=15",
        ])
        if not key_path:
            args.extend(["-o", "PasswordAuthentication=yes"])
        
        if key_path:
            args.extend(["-i", key_path])
        if scp:
            args.extend(["-P", str(port)])
        else:
            args.extend(["-p", str(port)])
    
    return args

def msg(text):
    print(f"{GREEN}▸{NC} {text}")

def pause():
    input(f"\n{BOLD}Нажмите Enter, чтобы продолжить...{NC}")

def warn(text):
    print(f"{YELLOW}⚠{NC} {text}")

def err(text, exit_code=None):
    print(f"{RED}✖{NC} {text}", file=sys.stderr)
    if exit_code is not None:
        sys.exit(exit_code)

def header(text):
    print(f"\n{CYAN}{BOLD}{text}{NC}")

def draw_separator():
    print(f"{DIM}──────────────────────────────────────────────────{NC}")

def get_router_ip():
    """Автоопределение IP роутера (ndmq / ip route / default)"""
    import subprocess
    import os
    
    # 1. ndmq (Keenetic)
    try:
        result = subprocess.run(['ndmq', '-p', 'show interface Bridge0', '-path', 'address'], capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            ip = result.stdout.strip()
            if ip != "0.0.0.0": return ip
    except: pass

    # 2. ip route (General Linux)
    try:
        result = subprocess.run(['ip', 'route', 'show'], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if 'default via' in line:
                return line.split()[2]
    except: pass

    return "192.168.1.1"

def is_port_busy(port):
    """Надежная проверка занятости порта через системные сокеты"""
    import socket
    try:
        # Проверяем TCP порт на 0.0.0.0
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            # Если connect_ex возвращает 0, порт открыт (занят процессом)
            return s.connect_ex(('127.0.0.1', int(port))) == 0
    except:
        return False

def gen_htpasswd(user, password):
    import subprocess
    try:
        # Пытаемся использовать openssl для генерации MD5-хэша (apr1)
        result = subprocess.run(
            ['openssl', 'passwd', '-apr1', password],
            capture_output=True, text=True, check=True
        )
        hash_val = result.stdout.strip()
        return f"{user}:{hash_val}"
    except Exception:
        # Если openssl нет, возвращаем plain text (Nginx может не принять)
        return f"{user}:{password}"

def get_domain_ip(domain):
    """Определяет IP-адрес домена через системный сокет"""
    import socket
    try:
        return socket.gethostbyname(domain)
    except:
        return None
