#!/bin/sh
# rProxy Web (Premium Dashboard) Installer for Keenetic
# VERSION: 5.0.1 - Pure Python & Premium CSS Edition (Bugfix)
# Чистый Glassmorphism без лишних фреймворков

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

msg() { printf "${GREEN}▸${NC} %b\n" "$*"; }
err() { printf "${RED}✖${NC} %b\n" "$*" >&2; exit 1; }

printf "\n${CYAN}==========================================${NC}\n"
printf "${CYAN}    rProxy Web v5.0.0 (Premium)           ${NC}\n"
printf "${CYAN}==========================================${NC}\n\n"

if [ ! -d "/opt/bin" ]; then
    err "Entware не найден. Установите Entware."
fi

msg "Установка Python3 и зависимостей..."
opkg update
opkg install python3-light python3-pip

INSTALL_DIR="/opt/share/rproxy-web"
mkdir -p "$INSTALL_DIR/templates"

msg "Чистка старой (Node.js) версии..."
/opt/etc/init.d/S99rproxy-web stop 2>/dev/null || true
pkill -f "python3 main.py" || true

msg "Загрузка Bottle.py..."
curl -sL https://raw.githubusercontent.com/bottlepy/bottle/master/bottle.py -o "$INSTALL_DIR/bottle.py"

if [ -f "./main.py" ] && [ -d "./templates" ]; then
    msg "Локальная установка..."
    cp main.py "$INSTALL_DIR/"
    cp templates/index.html "$INSTALL_DIR/templates/"
else
    msg "Загрузка v5.0.0 из GitHub..."
    TMP_DIR="/tmp/rproxy-web-v5"
    rm -rf "$TMP_DIR"
    mkdir -p "$TMP_DIR"
    # Примечание: в реальной ситуации здесь должна быть ссылка на конкретную ветку/релиз
    curl -sL https://github.com/l-ptrol/rProxy-web/archive/refs/heads/master.tar.gz -o "$TMP_DIR/master.tar.gz"
    tar -xzf "$TMP_DIR/master.tar.gz" -C "$TMP_DIR"
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 1 -name "rProxy-web*" -type d)
    cp "$SRC_DIR/main.py" "$INSTALL_DIR/"
    cp "$SRC_DIR/templates/index.html" "$INSTALL_DIR/templates/"
    rm -rf "$TMP_DIR"
fi

msg "Настройка службы автозапуска..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh
case "\$1" in
    start)
        echo "Starting rProxy Web v5.0..."
        cd "$INSTALL_DIR"
        /opt/bin/python3 main.py > /opt/var/log/rproxy-web.log 2>&1 &
        ;;
    stop)
        echo "Stopping rProxy Web..."
        pkill -f "python3 main.py"
        ;;
    restart)
        \$0 stop
        sleep 2
        \$0 start
        ;;
    status)
        if pgrep -f "python3 main.py" > /dev/null; then
            echo "online"
        else
            echo "offline"
        fi
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
EOF
chmod +x "$CAT_INIT"

msg "Установка v5.0.0 завершена!"
msg "Запустите: ${CYAN}$CAT_INIT start${NC}"
