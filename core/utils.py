# rProxy Core Utilities
import sys

# Цвета для терминала
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
CYAN = '\033[0;36m'
BOLD = '\033[1m'
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
    print(f"{NC}──────────────────────────────────────────────────")
