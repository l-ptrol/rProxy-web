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

# 3. Установка файлов проекта
INSTALL_DIR="/opt/share/rproxy-web"
msg "Установка в $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"

# Копируем фронтенд (сборку) и бэкенд
if [ -d "./frontend/dist" ] && [ -d "./backend" ]; then
    msg "Копирование файлов из текущей директории..."
    cp -r ./backend "$INSTALL_DIR/"
    cp -r ./frontend/dist "$INSTALL_DIR/frontend_dist"
else
    warn "Локальные файлы не найдены. Загрузка из GitHub (ветка master)..."
    mkdir -p /tmp/rproxy-web-download
    cd /tmp/rproxy-web-download
    
    msg "Загрузка архива проекта..."
    curl -L https://github.com/l-ptrol/rProxy-web/archive/refs/heads/master.tar.gz -o project.tar.gz
    tar -xzf project.tar.gz
    cd rProxy-web-master
    
    msg "Установка файлов в систему..."
    cp -rv ./backend "$INSTALL_DIR/"
    cp -rv ./frontend/dist "$INSTALL_DIR/frontend_dist"
    
    # Очистка
    rm -rf /tmp/rproxy-web-download
fi

# Исправляем путь в server.js
sed -i "s|../frontend/dist|../frontend_dist|g" "$INSTALL_DIR/backend/server.js"

# 4. Установка npm-зависимостей
msg "Установка npm-зависимостей сервера (может занять время)..."
cd "$INSTALL_DIR/backend"
npm install --production

# 5. Настройка автозапуска (S-скрипт)
msg "Настройка автозапуска..."
CAT_INIT="/opt/etc/init.d/S99rproxy-web"
cat > "$CAT_INIT" <<EOF
#!/bin/sh

case "\$1" in
    start)
        echo "Starting rProxy Web..."
        cd $INSTALL_DIR/backend
        # Запуск с указанием порта и путей через переменные окружения если нужно
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

msg "Установка успешно завершена!"
msg "1. Бэкенд и зависимости установлены."
msg "2. Автозапуск настроен: /opt/etc/init.d/S99rproxy-web"
msg "3. Веб-интерфейс готов к работе на порту 3000."
warn "Для запуска выполните: /opt/etc/init.d/S99rproxy-web start"
