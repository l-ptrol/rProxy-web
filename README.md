# 🚀 rProxy v7.4.2 (Python Core Edition)

[![Version](https://img.shields.io/badge/version-7.4.2-blue.svg)](https://github.com/l-ptrol/rProxy-web)
[![Platform](https://img.shields.io/badge/platform-Keenetic%20%7C%20Entware-orange.svg)](https://keenetic.net/)
[![Interface](https://img.shields.io/badge/interface-CLI%20%26%20Web-green.svg)](#)

**rProxy** — это профессиональная модульная система для управления SSH-туннелями и VPS-хостами, специально оптимизированная для роутеров Keenetic. Полностью переписанная на Python, система обеспечивает максимальную стабильность, скорость и безопасность при публикации внутренних сервисов в глобальную сеть.

---

## ✨ Основные возможности

### 🛠 Мощное ядро на Python
- **Modular Core**: Единая бизнес-логика для консольного (CLI) и графического (Web) интерфейсов.
- **AutoSSH Engine**: Интеллектуальное управление туннелями с автоматическим переподключением.
- **Nginx Automation**: Полная автоматизация конфигураций проксирования на стороне VPS.

### 🌐 Премиальный Web-интерфейс
- **Glassmorphism Design**: Современный, "стеклянный" интерфейс с поддержкой темной темы.
- **Real-time Logs**: Отслеживание процесса деплоя и выполнения задач в реальном времени прямо в браузере.
- **Mobile Ready**: Адаптивная верстка, идеально подходящая для управления с мобильных устройств.

### 🖥 Управление VPS серверами
- **Connection Monitoring**: Автоматическая проверка статуса серверов (Online/Offline).
- **One-Click Repair**: Система автоматического восстановления окружения на удаленном сервере.
- **Cleanup Tool**: Умная очистка фантомных конфигураций Nginx.

---

## 📦 Установка

Для установки на Keenetic (с установленным Entware) выполните одну команду:

```bash
curl -sL https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/install.sh -o /tmp/install.sh && sh /tmp/install.sh
```

---

## 🚀 Использование

### Консольный интерфейс (CLI)
Просто введите команду `rproxy` в терминале для запуска интерактивного меню:
```bash
rproxy
```

### Веб-интерфейс
1. Убедитесь, что служба запущена: `/opt/etc/init.d/S99rproxy-web start`
2. Откройте в браузере: `http://<IP-роутера>:3000`

---

## 🏗 Архитектура проекта

Проект построен по модульному принципу:
- `core/`: Ядро системы (логика туннелей, управление конфигами, VPS менеджер).
- `main.py`: Быстрый веб-сервер на Bottle с поддержкой многопоточности.
- `rproxy.py`: Удобный интерактивный CLI на базе Python.
- `templates/`: Фронтенд-составляющая (HTML/JS/Vanilla CSS).
- `install.sh`: Интеллектуальный установщик, настраивающий окружение и зависимости.

---

## 🛠 Технический стек
- **Backend**: Python 3.x, Bottle Framework.
- **Frontend**: Vanilla JS, Vanilla CSS (Glassmorphism), WebSocket-like polling.
- **Tunneling**: AutoSSH, Nginx (Stream & HTTP modules).
- **Security**: Basic Auth, Certbot (Let's Encrypt), SSH Key Auth.

---

## 🤝 Разработка
Проект активно развивается. При обнаружении ошибок или наличии предложений — создавайте Issue или Pull Request.

*Разработано с заботой о пользователях Keenetic.*
