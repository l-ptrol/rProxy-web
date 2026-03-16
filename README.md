# rProxy Web Dashboard

Суперсовременный, адаптивный веб-интерфейс для управления скриптом `rProxy` на роутерах Keenetic.

## Особенности

- 💎 **Glassmorphism Design**: Премиальная темная тема с эффектами размытия.
- 📱 **Mobile Ready**: Полная адаптивность для вертикальных экранов смартфонов.
- 🚀 **Keenetic Optimized**: Легковесный бэкенд на Node.js, работающий в Entware.
- 📊 **Real-time Status**: Мониторинг сервисов и туннелей в реальном времени.

## Быстрая установка

Для установки веб-интерфейса выполните следующую команду в терминале вашего роутера (требуется установленный Entware):

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/l-ptrol/rProxy-web/main/install.sh)"
```

## Требования

- Роутер Keenetic с установленным Entware.
- Установленный пакет `node` и `node-npm` (`opkg install node node-npm`).
- Установленный основной скрипт `rProxy`.

## Разработка

Проект разделен на две части:
1. `frontend/` — React + Vite + Tailwind CSS.
2. `backend/` — Node.js Express API мост.

---
Разработано с ❤️ для пользователей Keenetic.
