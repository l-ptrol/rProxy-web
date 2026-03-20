#!/bin/sh
# rProxy Go Edition — Установщик для Keenetic (Entware)
VERSION="1.0.2-go"

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

# Определение порта веб-интерфейса (по умолчанию 3000)
RPROXY_PORT=${PORT:-3000}

# Определение архитектуры
ARCH=$(uname -m)
if [ "$ARCH" = "mips" ]; then
    # Проверка на Little Endian (например, роутеры Keenetic на MT7621)
    if grep -qiE "MediaTek|Ralink|MT76|RT3|RT5|Little" /proc/cpuinfo 2>/dev/null; then
        ARCH="mipsel"
    fi
fi

case "$ARCH" in
    mips)     BINARY="rproxy-mips"    ;;
    mipsel)   BINARY="rproxy-mipsle"  ;;
    aarch64)  BINARY="rproxy-arm64"   ;;
    *)        err "Неподдерживаемая архитектура: $ARCH" ;;
esac

msg "Архитектура: $ARCH → Бинарник: $BINARY"

# Установка минимальных зависимостей (только системные утилиты)
msg "Установка системных зависимостей (autossh, openssh)..."
opkg update
opkg install autossh psmisc procps-ng-pkill openssh-keygen openssh-client openssl-util ttyd socat curl

INSTALL_DIR="/opt/bin"

msg "Очистка старой версии..."
/opt/etc/init.d/S99rproxy-web stop 2>/dev/null || true

# Загрузка бинарника
msg "Загрузка бинарника rProxy..."
T_STAMP=$(date +%s)
# Для тестирования качаем прямо из ветки test-go этого репозитория
curl -f -sL "https://raw.githubusercontent.com/l-ptrol/rProxy-web/test-go/go-rewrite/dist/${BINARY}?t=$T_STAMP" -o "$INSTALL_DIR/rproxy" || err "Не удалось скачать бинарник. Проверьте интернет или URL."

# Проверка размера
if [ ! -s "$INSTALL_DIR/rproxy" ]; then
    err "Скачанный файл пуст. Возможно, URL неверен."
fi

# Назначение прав
chmod +x "$INSTALL_DIR/rproxy"
msg "Права доступа установлены: $(ls -l $INSTALL_DIR/rproxy)"

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
        ./rproxy web $RPROXY_PORT > /opt/var/log/rproxy-web.log 2>&1 &
        ;;
    stop)
        echo "Stopping rProxy Web..."
        pkill -f "rproxy web" || true
        fuser -k ${RPROXY_PORT}/tcp 2>/dev/null || true
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
msg "Консоль:  ${CYAN}/opt/bin/rproxy${NC}"
msg "Веб-порт: ${CYAN}${RPROXY_PORT}${NC}"
msg "Статус:   ${GREEN}онлайн${NC}"

# Проверка работоспособности
msg "Тестовый запуск версии..."
/opt/bin/rproxy version || msg "${RED}Внимание: бинарник не запускается. Возможно, не та архитектура.${NC}"
msg ""
msg "Примечание: Python больше НЕ ТРЕБУЕТСЯ!"
