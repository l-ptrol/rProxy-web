#!/bin/sh
# rProxy Go Edition — Установщик для Keenetic (Entware)
VERSION="1.0.11-go"

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
PKGS="autossh psmisc procps-ng-pkill openssh-keygen openssh-client openssl-util ttyd socat curl"
MISSING_PKGS=""
for pkg in $PKGS; do
    if ! opkg list-installed | grep -q "^$pkg "; then
        MISSING_PKGS="$MISSING_PKGS $pkg"
    fi
done

if [ -n "$MISSING_PKGS" ]; then
    msg "Установка недостающих системных зависимостей:$MISSING_PKGS..."
    opkg update
    opkg install $MISSING_PKGS
else
    msg "Все системные зависимости (autossh, ttyd и др.) уже установлены."
fi

INSTALL_DIR="/opt/bin"

msg "Очистка старой версии..."
# Останавливаем и удаляем старые скрипты, если они есть
[ -f "/opt/etc/init.d/S99rproxy-web" ] && /opt/etc/init.d/S99rproxy-web stop 2>/dev/null || true
[ -f "/opt/etc/init.d/S98rproxy" ] && /opt/etc/init.d/S98rproxy stop 2>/dev/null || true
rm -f "/opt/etc/init.d/S99rproxy-web" "/opt/etc/init.d/S98rproxy"

# Загрузка бинарника
msg "Загрузка бинарника rProxy..."
T_STAMP=$(date +%s)
# Качаем из основной ветки master
curl -f -sL "https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/dist/${BINARY}?t=$T_STAMP" -o "$INSTALL_DIR/rproxy" || err "Не удалось скачать бинарник. Проверьте интернет или URL."

# Проверка размера
if [ ! -s "$INSTALL_DIR/rproxy" ]; then
    err "Скачанный файл пуст. Возможно, URL неверен."
fi

# Назначение прав
chmod +x "$INSTALL_DIR/rproxy"
msg "Права доступа установлены: $(ls -l $INSTALL_DIR/rproxy)"

msg "Настройка прав доступа..."
[ -f "/opt/etc/rproxy/id_ed25519" ] && chmod 600 "/opt/etc/rproxy/id_ed25519"

msg "Создание единой службы автозапуска rProxy..."
CAT_INIT="/opt/etc/init.d/S99rproxy"
cat > "$CAT_INIT" <<EOF
#!/bin/sh
export PATH=/opt/sbin:/opt/bin:/opt/usr/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
case "\$1" in
    start)
        echo "Starting rProxy v${VERSION}..."
        # 1. Веб-интерфейс
        echo "  ▸ Web UI (port $RPROXY_PORT)..."
        mkdir -p /opt/var/log
        cd /opt/bin
        ./rproxy web $RPROXY_PORT > /opt/var/log/rproxy-web.log 2>&1 &
        # 2. Туннели (с задержкой 60с)
        echo "  ▸ Tunnels (delayed boot)..."
        (
            sleep 60
            /opt/bin/rproxy boot
        ) > /opt/var/log/rproxy_boot.log 2>&1 &
        ;;
    stop)
        echo "Stopping rProxy..."
        pkill -f "rproxy web" || true
        fuser -k ${RPROXY_PORT}/tcp 2>/dev/null || true
        /opt/bin/rproxy stop || true
        ;;
    restart)
        \$0 stop
        sleep 2
        \$0 start
        ;;
    status)
        WEB_ST=\$(pgrep -f "rproxy web" > /dev/null && echo "online" || echo "offline")
        TUN_ST=\$(pgrep -f "autossh" > /dev/null && echo "active" || echo "inactive")
        echo "Web UI:  \$WEB_ST"
        echo "Tunnels: \$TUN_ST"
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
EOF
chmod +x "$CAT_INIT"

msg "Перезапуск службы rProxy..."
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
