#!/bin/sh
# rProxy Web (Python/Zero-Dep Edition) Installer for Keenetic
# VERSION: 2.0.3

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
    printf "${GREEN}   rProxy Web (Zero-Dep) Installer  ${NC}\n"
    printf "${GREEN}====================================${NC}\n\n"
}

header

# 1. Проверка Entware
if [ ! -d "/opt/bin" ]; then
    err "Entware не найден. Установите Entware на ваш роутер."
fi

# 2. Установка Python
msg "Установка Python3..."
opkg update
opkg install python3

# 3. Подготовка директорий
INSTALL_DIR="/opt/share/rproxy-web"
msg "Установка в $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR/templates"

# 4. Загрузка Bottle.py (Zero-Dependency Strategy)
msg "Загрузка библиотеки Bottle (автономный режим)..."
curl -sL https://raw.githubusercontent.com/bottlepy/bottle/master/bottle.py -o "$INSTALL_DIR/bottle.py"

# 5. Установка файлов проекта
if [ -f "./main.py" ]; then
    msg "Копирование локальных файлов..."
    cp main.py "$INSTALL_DIR/"
    cp templates/index.html "$INSTALL_DIR/templates/"
else
    msg "Загрузка из репозитория GitHub..."
    TMP_DIR="/tmp/rproxy-web-py"
    mkdir -p "$TMP_DIR"
    curl -L https://github.com/l-ptrol/rProxy-web/archive/refs/heads/master.tar.gz -o "$TMP_DIR/master.tar.gz"
    tar -xzf "$TMP_DIR/master.tar.gz" -C "$TMP_DIR"
    cp -r "$TMP_DIR"/rProxy-web-master/main.py "$INSTALL_DIR/"
    cp -r "$TMP_DIR"/rProxy-web-master/templates "$INSTALL_DIR/"
    rm -rf "$TMP_DIR"
fi

# 6. Настройка автозапуска
msg "Создание службы автозапуска..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh

case "\$1" in
    start)
        echo "Starting rProxy Web..."
        cd $INSTALL_DIR
        python3 main.py > /opt/var/log/rproxy-web.log 2>&1 &
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
    *)
        echo "Usage: \$0 {start|stop|restart}"
        exit 1
        ;;
esac
EOF

chmod +x "$CAT_INIT"

msg "Установка завершена успешно!"
msg "Порт управления: 3000"
warn "Для запуска выполните: $CAT_INIT start"
