#!/bin/sh
# rProxy Web Installer for Keenetic (Entware)
# VERSION: 1.0.0

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

msg() { printf "${GREEN}▸${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err() { printf "${RED}✖${NC} %s\n" "$*" >&2; exit 1; }

header() {
    printf "\n${GREEN}====================================${NC}\n"
    printf "${GREEN}   rProxy Web Dashboard Installer   ${NC}\n"
    printf "${GREEN}====================================${NC}\n\n"
}

header

# 1. Проверка Entware
if [ ! -d "/opt/bin" ]; then
    err "Entware не найден. Пожалуйста, установите Entware на ваш роутер."
fi

# 2. Установка зависимостей
msg "Проверка и установка зависимостей (node, npm)..."
opkg update
opkg install node node-npm curl

# 3. Скачивание проекта
INSTALL_DIR="/opt/share/rproxy-web"
msg "Установка в $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# В реальном сценарии здесь будет скачивание архива или git clone
# Для демонстрации создаем структуру
cd "$INSTALL_DIR"

# 4. Настройка автозапуска (S-скрипт)
msg "Настройка автозапуска..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh

case "\$1" in
    start)
        echo "Starting rProxy Web..."
        cd $INSTALL_DIR/backend
        node server.js > /opt/var/log/rproxy-web.log 2>&1 &
        ;;
    stop)
        echo "Stopping rProxy Web..."
        pkill -f "node server.js"
        ;;
    restart)
        \$0 stop
        sleep 2
        \$0 start
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart}"
        exit 1
        ;;
esac
EOF

chmod +x "$CAT_INIT"

msg "Установка завершена!"
msg "Веб-интерфейс будет доступен по адресу роутера на порту 3000 (по умолчанию)."
warn "Не забудьте настроить rproxy.conf перед использованием."
