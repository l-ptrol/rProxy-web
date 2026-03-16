#!/bin/sh
# rProxy Web (Premium Dashboard) Installer for Keenetic
# VERSION: 3.0.0 - Premium Edition

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

msg() { printf "${GREEN}▸${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}⚠${NC} %s\n" "$*"; }
err() { printf "${RED}✖${NC} %s\n" "$*" >&2; exit 1; }

header() {
    printf "\n${CYAN}==========================================${NC}\n"
    printf "${CYAN}    rProxy Web v3.0.0 (Premium Dashboard)  ${NC}\n"
    printf "${CYAN}==========================================${NC}\n\n"
}

header

# 1. Проверка Entware
if [ ! -d "/opt/bin" ]; then
    err "Entware не найден. Установите Entware на ваш роутер."
fi

# 2. Установка Python3
msg "Проверка и установка Python3..."
opkg update
opkg install python3

# 3. Подготовка директорий
INSTALL_DIR="/opt/share/rproxy-web"
LOG_DIR="/opt/var/log"
mkdir -p "$INSTALL_DIR/templates"
mkdir -p "$LOG_DIR"

msg "Директория установки: $INSTALL_DIR"

# 4. Загрузка Bottle.py (Zero-Dependency)
msg "Загрузка ядра Dashboard (Bottle.py)..."
curl -sL https://raw.githubusercontent.com/bottlepy/bottle/master/bottle.py -o "$INSTALL_DIR/bottle.py"

# 5. Установка файлов проекта
# Если работаем локально (dev), берем из текущей папки
if [ -f "./main.py" ] && [ -d "./templates" ]; then
    msg "Установка локальных файлов..."
    cp main.py "$INSTALL_DIR/"
    cp templates/index.html "$INSTALL_DIR/templates/"
else
    msg "Загрузка v3.0.0 из репозитория GitHub..."
    TMP_DIR="/tmp/rproxy-web-v3"
    mkdir -p "$TMP_DIR"
    curl -L https://github.com/l-ptrol/rProxy-web/archive/refs/heads/master.tar.gz -o "$TMP_DIR/master.tar.gz"
    tar -xzf "$TMP_DIR/master.tar.gz" -C "$TMP_DIR"
    
    # Копируем содержимое (путь в архиве может отличаться)
    SRC_DIR=$(find "$TMP_DIR" -maxdepth 1 -name "rProxy-web*" -type d)
    cp -r "$SRC_DIR/main.py" "$INSTALL_DIR/"
    cp -r "$SRC_DIR/templates" "$INSTALL_DIR/"
    
    rm -rf "$TMP_DIR"
fi

# 6. Создание скрипта автозапуска (Init-скрипт)
msg "Регистрация службы в системе..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh

case "\$1" in
    start)
        echo "Starting rProxy Web v3.0..."
        cd "$INSTALL_DIR"
        # Запуск с игнорированием SIGHUP и выводом в лог
        /opt/bin/python3 main.py > "$LOG_DIR/rproxy-web.log" 2>&1 &
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
            echo "rProxy Web is running."
        else
            echo "rProxy Web is stopped."
        fi
        ;;
    *)
        echo "Usage: \$0 {start|stop|restart|status}"
        exit 1
        ;;
esac
EOF

chmod +x "$CAT_INIT"

# 7. Финализация
msg "Установка завершена успешно!"
msg "Порт управления: ${CYAN}3000${NC}"
msg "Дизайн: ${CYAN}Premium Glassmorphism v3${NC}"
warn "Чтобы запустить веб-интерфейс, выполните:"
printf "${CYAN}$CAT_INIT start${NC}\n\n"
EOF
