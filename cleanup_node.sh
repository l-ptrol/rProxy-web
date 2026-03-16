#!/bin/sh
# Скрипт очистки проекта от Node.js/React версии (v4.0 "Trash" edition)

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

echo "${RED}Удаление Node.js версии rProxy Web...${NC}"

# 1. Останавливаем службу
if [ -f /opt/etc/init.d/S99rproxy-web ]; then
    /opt/etc/init.d/S99rproxy-web stop || true
    rm /opt/etc/init.d/S99rproxy-web
fi

# 2. Удаляем временные файлы и PID
rm -f /opt/var/run/rproxy-web.pid
rm -f /opt/var/log/rproxy-web.log

# 3. Удаляем папки проекта, связанные с Node/React
# В локальной директории разработки (на Windows это не сработает, но в репозитории/на роутере да)
rm -rf backend
rm -rf frontend
rm -rf frontend_dist
rm -f package.json
rm -f tsconfig.json
rm -f vite.config.ts
rm -f .gitignore

echo "${GREEN}Очистка завершена. Возвращаемся к Python-архитектуре.${NC}"
