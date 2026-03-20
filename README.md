# 🚀 rProxy v1.0.9-go (Native Go Edition)

[![Version](https://img.shields.io/badge/version-1.0.9--go-blue.svg)](https://github.com/l-ptrol/rProxy-web)
[![Platform](https://img.shields.io/badge/platform-Keenetic%20%7C%20Entware-orange.svg)](https://keenetic.net/)
[![Interface](https://img.shields.io/badge/interface-CLI%20%26%20Web-green.svg)](#)

**rProxy** — это профессиональная модульная система для управления SSH-туннелями и VPS-хостами, оптимизированная для роутеров Keenetic. Полностью переписанная на нативном **Go**, система работает без зависимостей (Python больше не требуется), обеспечивая максимальную стабильность и минимальное потребление ресурсов.

---

## ✨ Основные возможности

### ⚡ Нативное ядро на Go
- **Zero Dependencies**: Больше не нужно устанавливать Python или пакеты `pip`. Всё включено в один бинарный файл.
- **Native SSH Client**: Использование встроенного Go SSH-клиента вместо внешних утилит типа `sshpass`.
- **High Performance**: Минимальное потребление ОЗУ и мгновенный запуск сервисов.

### 🌐 Премиальный Web-интерфейс
- **Glassmorphism Design**: Современный "стеклянный" интерфейс с эффектом размытия и поддержкой темной темы.
- **Real-time Logs**: Интерактивные консоли деплоя и выполнения задач прямо в браузере.
- **Mobile Ready**: Идеально адаптирован под вертикальные экраны мобильных устройств.

### 🖥 Управление VPS серверами
- **Health Check**: Детальный мониторинг статуса Nginx и SSL-сертификатов на удаленных VPS.
- **One-Click Setup**: Автоматическая настройка SSH-ключей и окружения на новом сервере.
- **Auto-Update**: Встроенная система обновления rProxy одной кнопкой.

---

## 📦 Установка

Для установки на Keenetic (с установленным Entware) выполните одну команду:

```bash
wget -O - https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/install.sh | sh
```

---

## 🚀 Использование

### Консольный интерфейс (CLI)
Команда `rproxy` теперь предоставляет прямой доступ к управлению без посредников:
```bash
rproxy --help
```

### Веб-интерфейс
1. Убедитесь, что служба запущена: `/opt/etc/init.d/S99rproxy-web start`
2. Откройте в браузере: `http://<IP-роутера>:3000`

---

## 🏗 Архитектура проекта
- `main.go`: Точка входа, встроенный веб-сервер и CLI-команды.
- `core/`: Ядро системы (SSH-туннели, управление VPS, шаблоны Nginx).
- `cmd/`: Обработчики Web API.
- `templates/`: Фронтенд (HTML/JS/Vanilla CSS), встроенный прямо в исполняемый файл.
- `install.sh`: Компактный установщик, автоматически определяющий архитектуру (mipsle/mips/arm64).

---

## 🛠 Технический стек
- **Backend**: Go 1.23+
- **Frontend**: Vanilla JS, Glassmorphism CSS UI.
- **Tunneling**: Native Go SSH, Nginx.
- **Security**: Basic Auth, Let's Encrypt, SSH Key Auth.

---

## 🤝 Разработка
Проект активно развивается. Если у вас есть предложения или вы нашли ошибку — создавайте Issue или Pull Request.

*Разработано с заботой о пользователях Keenetic.*
