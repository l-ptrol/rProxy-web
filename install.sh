#!/bin/sh
# rProxy Web & CLI (Python Core) Installer for Keenetic
# rProxy Installer v7.1.1
VERSION="7.1.1"
# - Fixed Version Sync & SSH Reliability
# Новое ядро на Python. 100% паритет с Bash + Модульность.

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

msg() { printf "${GREEN}▸${NC} %b\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC} %b\n" "$*"; }
err() { printf "${RED}✖${NC} %b\n" "$*" >&2; exit 1; }

printf "\n${CYAN}==========================================${NC}\n"
printf "${CYAN}    rProxy Python Core v${VERSION}             ${NC}\n"
printf "${CYAN}==========================================${NC}\n\n"

if [ ! -d "/opt/bin" ]; then
    err "Entware не найден. Установите Entware."
fi

msg "Установка зависимостей (autossh, pkill, psmisc, ttyd, socat)..."
opkg update >/dev/null 2>&1
opkg install python3 python3-pip autossh psmisc procps-ng-pkill openssh-keygen openssh-client openssh-scp openssl-util ttyd socat curl grep sed >/dev/null 2>&1

INSTALL_DIR="/opt/share/rproxy-web"
mkdir -p "$INSTALL_DIR"

msg "Очистка старой версии..."
/opt/etc/init.d/S99rproxy-web stop 2>/dev/null || true
rm -rf "$INSTALL_DIR/core"
rm -rf "$INSTALL_DIR/templates"
rm -f "$INSTALL_DIR/main.py"
rm -f "$INSTALL_DIR/rproxy.py"

msg "Загрузка Bottle.py..."
curl -sL https://raw.githubusercontent.com/bottlepy/bottle/master/bottle.py -o "$INSTALL_DIR/bottle.py"

if [ -d "./core" ] && [ -f "./main.py" ]; then
    msg "Локальная установка..."
    cp -r core "$INSTALL_DIR/"
    cp -r templates "$INSTALL_DIR/"
    cp main.py rproxy.py "$INSTALL_DIR/"
else
    msg "Загрузка последней версии из GitHub..."
    TMP_DIR="/tmp/rproxy-web-v7"
    rm -rf "$TMP_DIR"
    mkdir -p "$TMP_DIR"
    T_STAMP=$(date +%s)
    curl -sL "https://github.com/l-ptrol/rProxy-web/archive/refs/heads/master.tar.gz?t=$T_STAMP" -o "$TMP_DIR/master.tar.gz"
    tar -xzf "$TMP_DIR/master.tar.gz" -C "$TMP_DIR"
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 1 -name "rProxy-web*" -type d | head -n 1)
    if [ -z "$SRC_DIR" ]; then err "Не удалось найти исходники в архиве."; fi
    cp -r "$SRC_DIR/core" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/templates" "$INSTALL_DIR/"
    cp "$SRC_DIR/main.py" "$SRC_DIR/rproxy.py" "$INSTALL_DIR/"
    rm -rf "$TMP_DIR"
fi

msg "Настройка прав доступа..."
chmod +x "$INSTALL_DIR/rproxy.py"
ln -sf "$INSTALL_DIR/rproxy.py" "/opt/bin/rproxy"

msg "Создание службы автозапуска веб-интерфейса..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh
case "\$1" in
    start)
        echo "Starting rProxy Web v${VERSION}..."
        cd "$INSTALL_DIR"
        /opt/bin/python3 main.py > /opt/var/log/rproxy-web.log 2>&1 &
        ;;
    stop)
        echo "Stopping rProxy Web..."
        pkill -f "python3 main.py" || true
        fuser -k 3000/tcp 2>/dev/null || true
        ;;
    restart)
        \$0 stop
        sleep 2
        \$0 start
        ;;
    status)
        if pgrep -f "python3 main.py" > /dev/null; then echo "online"; else echo "offline"; fi
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
EOF
chmod +x "$CAT_INIT"

msg "Создание скрипта автозапуска туннелей..."
SVC_INIT="/opt/etc/init.d/S98rproxy"
cat > "$SVC_INIT" <<EOF
#!/bin/sh
case "\$1" in
    start)
        echo "Autostarting rProxy tunnels..."
        /opt/bin/rproxy boot
        ;;
    stop)
        echo "Stopping all rProxy tunnels..."
        /opt/bin/rproxy stop
        ;;
    restart)
        \$0 stop
        sleep 1
        \$0 start
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart}"
        exit 1
        ;;
esac
EOF
chmod +x "$SVC_INIT"

msg "Перезапуск веб-интерфейса..."
$CAT_INIT restart

msg "Установка rProxy v${VERSION} успешно завершена!"
printf "\n"
msg "Консоль:  ${CYAN}rproxy${NC}"
msg "Веб-порт: ${CYAN}3000${NC}"
msg "Статус:   ${GREEN}онлайн${NC}"
