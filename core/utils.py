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

def msg(text):
    print(f"{GREEN}▸{NC} {text}")

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
