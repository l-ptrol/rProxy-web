#!/bin/sh
# rProxy Go Edition — Установщик для Keenetic (Entware)
VERSION="8.0.0-go"

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
NC='\033[0m'

msg() { printf "${GREEN}▸${NC} %b\n" "$*"; }
err() { printf "${RED}✖${NC} %b\n" "$*" >&2; exit 1; }

printf "\n${CYAN}==========================================${NC}\n"
printf "${CYAN}    rProxy Go Edition v${VERSION}           ${NC}\n"
printf "${CYAN}==========================================${NC}\n\n"

if [ ! -d "/opt/bin" ]; then
    err "Entware не найден. Установите Entware."
fi

# Определение архитектуры
ARCH=$(uname -m)
case "$ARCH" in
    mips)     BINARY="rproxy-mips"    ;;
    mipsel)   BINARY="rproxy-mipsle"  ;;
    aarch64)  BINARY="rproxy-arm64"   ;;
    *)        err "Неподдерживаемая архитектура: $ARCH" ;;
esac

msg "Архитектура: $ARCH → Бинарник: $BINARY"

# Установка минимальных зависимостей (только системные утилиты)
msg "Установка системных зависимостей (autossh, openssh)..."
set +e
opkg update >/dev/null 2>&1
opkg install autossh psmisc procps-ng-pkill openssh-keygen openssh-client openssl-util ttyd socat curl >/dev/null 2>&1
set -e

INSTALL_DIR="/opt/bin"

msg "Очистка старой версии..."
/opt/etc/init.d/S99rproxy-web stop 2>/dev/null || true

# Загрузка бинарника
msg "Загрузка бинарника rProxy..."
T_STAMP=$(date +%s)
# В случае релиза, качаем из github
# curl -sL "https://github.com/l-ptrol/rProxy-go/releases/latest/download/${BINARY}?t=$T_STAMP" -o "$INSTALL_DIR/rproxy"
# Но пока скачан вручную пользователем

# Назначение прав
chmod +x "$INSTALL_DIR/rproxy"

msg "Настройка прав доступа..."
[ -f "/opt/etc/rproxy/id_ed25519" ] && chmod 600 "/opt/etc/rproxy/id_ed25519"

msg "Создание службы автозапуска веб-интерфейса..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh
export PATH=/opt/sbin:/opt/bin:/opt/usr/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
case "\$1" in
    start)
        echo "Starting rProxy Web (Go) v${VERSION}..."
        mkdir -p /opt/var/log
        cd /opt/bin
        ./rproxy web > /opt/var/log/rproxy-web.log 2>&1 &
        ;;
    stop)
        echo "Stopping rProxy Web..."
        pkill -f "rproxy web" || true
        fuser -k 3000/tcp 2>/dev/null || true
        ;;
    restart)
        \$0 stop
        sleep 2
        \$0 start
        ;;
    status)
        if pgrep -f "rproxy web" > /dev/null; then echo "online"; else echo "offline"; fi
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
export PATH=/opt/sbin:/opt/bin:/opt/usr/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
case "\$1" in
    start)
        echo "Autostarting rProxy tunnels in background (delayed)..."
        (
            sleep 60
            /opt/bin/rproxy boot
        ) > /opt/var/log/rproxy_boot.log 2>&1 &
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

msg "Установка rProxy v${VERSION} (Go) успешно завершена!"
printf "\n"
msg "Консоль:  ${CYAN}rproxy${NC}"
msg "Веб-порт: ${CYAN}3000${NC}"
msg "Статус:   ${GREEN}онлайн${NC}"
msg ""
msg "Примечание: Python больше НЕ ТРЕБУЕТСЯ!"
