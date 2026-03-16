#!/bin/sh
# rProxy Web Uninstaller for Keenetic

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

msg() { printf "${GREEN}▸${NC} %b\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC} %b\n" "$*"; }
err() { printf "${RED}✖${NC} %b\n" "$*" >&2; exit 1; }

printf "\n${RED}==========================================${NC}\n"
printf "${RED}    Деинсталляция rProxy Web              ${NC}\n"
printf "${RED}==========================================${NC}\n\n"

# 1. Остановка службы
msg "Остановка службы..."
if [ -f "/opt/etc/init.d/S99rproxy-web" ]; then
    /opt/etc/init.d/S99rproxy-web stop 2>/dev/null || true
    rm "/opt/etc/init.d/S99rproxy-web"
    msg "Служба S99rproxy-web удалена."
else
    warn "Служба S99rproxy-web не найдена."
fi

# 2. Удаление файлов проекта
msg "Удаление файлов проекта..."
if [ -d "/opt/share/rproxy-web" ]; then
    rm -rf "/opt/share/rproxy-web"
    msg "Директория /opt/share/rproxy-web удалена."
else
    warn "Директория проекта не найдена."
fi

# 3. Удаление логов и PID
msg "Очистка временных файлов..."
rm -f /opt/var/log/rproxy-web.log
rm -f /opt/var/run/rproxy-web.pid
rm -f /opt/var/run/rproxy-web-backend.pid
rm -f /opt/var/run/rproxy-web-frontend.pid

# 4. Сообщение пользователю про пакеты
warn "Node.js, NPM и Python3 не были удалены, так как они могут быть нужны системе."
warn "Если они вам не нужны, удалите их вручную: opkg remove node node-npm python3"

msg "Удаление rProxy Web завершено."
printf "\n"
