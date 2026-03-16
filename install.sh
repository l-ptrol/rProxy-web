#!/bin/sh
# rProxy Web (Premium Dashboard) Installer for Keenetic
# VERSION: 4.0.0 - Deep Integration Edition
# Глубокая интеграция со скриптом rproxy (Node.js + React)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

msg() { printf "${GREEN}▸${NC} %b\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC} %b\n" "$*"; }
err() { printf "${RED}✖${NC} %b\n" "$*" >&2; exit 1; }

header() {
    printf "\n${CYAN}==========================================${NC}\n"
    printf "${CYAN}    rProxy Web v4.0.0 (Deep Integration)  ${NC}\n"
    printf "${CYAN}==========================================${NC}\n\n"
}

header

if [ ! -d "/opt/bin" ]; then
    err "Entware не найден. Установите Entware на ваш роутер."
fi

msg "Обновление списка пакетов..."
opkg update

msg "Установка зависимостей (Node.js, NPM)..."
opkg install node node-npm

INSTALL_DIR="/opt/share/rproxy-web"
mkdir -p "$INSTALL_DIR"

msg "Чистка старой версии..."
/opt/etc/init.d/S99rproxy-web stop 2>/dev/null || true
rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR"

if [ -d "./backend" ] && [ -d "./frontend_dist" ]; then
    msg "Локальная установка из текущей директории..."
    cp -r backend "$INSTALL_DIR/"
    cp -r frontend_dist "$INSTALL_DIR/"
else
    msg "Загрузка v4.0.0 из GitHub (master)..."
    TMP_DIR="/tmp/rproxy-web-v4"
    rm -rf "$TMP_DIR"
    mkdir -p "$TMP_DIR"
    curl -sL https://github.com/l-ptrol/rProxy-web/archive/refs/heads/master.tar.gz -o "$TMP_DIR/master.tar.gz"
    tar -xzf "$TMP_DIR/master.tar.gz" -C "$TMP_DIR"
    
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 1 -name "rProxy-web*" -type d)
    cp -r "$SRC_DIR/backend" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/frontend_dist" "$INSTALL_DIR/"
    rm -rf "$TMP_DIR"
fi

msg "Установка Node-зависимостей бэкенда..."
cd "$INSTALL_DIR/backend"
npm install --production

msg "Настройка службы автозапуска..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh

# rProxy Web Init Script
# Path: $CAT_INIT

case "\$1" in
    start)
        echo "Starting rProxy Web v4.0..."
        cd "$INSTALL_DIR/backend"
        /opt/bin/node server.js > /opt/var/log/rproxy-web.log 2>&1 &
        echo \$! > /opt/var/run/rproxy-web.pid
        ;;
    stop)
        echo "Stopping rProxy Web..."
        if [ -f /opt/var/run/rproxy-web.pid ]; then
            kill \$(cat /opt/var/run/rproxy-web.pid) 2>/dev/null || true
            rm /opt/var/run/rproxy-web.pid
        fi
        pkill -f "node server.js" || true
        ;;
    restart)
        \$0 stop
        sleep 2
        \$0 start
        ;;
    status)
        if pgrep -f "node server.js" > /dev/null; then
            echo "rProxy Web is online"
        else
            echo "rProxy Web is offline"
        fi
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
EOF

chmod +x "$CAT_INIT"

msg "Установка rProxy Web v4.0.0 завершена!"
msg "Порт: ${CYAN}3000${NC}"
msg "Интерфейс доступен по адресу роутера (напр. http://192.168.1.1:3000)"
warn "Запустите интерфейс командой: ${CYAN}$CAT_INIT start${NC}"
