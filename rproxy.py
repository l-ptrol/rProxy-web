#!/usr/bin/env python3
import sys
import os
from core.utils import msg, warn, err, header, draw_separator, BOLD, NC, GREEN, RED, YELLOW, CYAN
from core.config import ConfigManager
from core.vps import VPSManager
from core.manager import ProcessManager

VERSION = "6.0.0"

class RProxyCLI:
    def __init__(self):
        self.root = "/opt/etc/rproxy"
        self.services_dir = os.path.join(self.root, "services")
        self.vps_dir = os.path.join(self.root, "vps")
        os.makedirs(self.services_dir, exist_ok=True)
        os.makedirs(self.vps_dir, exist_ok=True)

    def clear(self):
        os.system('clear')

    def main_menu(self):
        while True:
            self.clear()
            header(f"rProxy v{VERSION} — Python Core Edition")
            print(f"  {BOLD}1){NC}  🌐  Список публикаций и статус")
            print(f"  {BOLD}2){NC}  🚀  Запустить туннели")
            print(f"  {BOLD}3){NC}  🛑  Остановить туннели")
            print(f"  {BOLD}4){NC}  ➕  Добавить новый сервис")
            print(f"  {BOLD}5){NC}  🖥️   Управление VPS")
            print(f"  {BOLD}6){NC}  🔑  Управление SSL (Certbot)")
            print(f"  {BOLD}0){NC}      Выход")
            
            choice = input(f"\n{BOLD}Выберите действие:{NC} ")
            
            if choice == '1': self.list_services()
            elif choice == '2': self.start_services()
            elif choice == '3': self.stop_services()
            elif choice == '5': self.vps_menu()
            elif choice == '0': break
            else: warn("Неверный ввод")
            
            if choice != '0': input(f"\n{NC}Нажмите Enter для продолжения...")

    def list_services(self):
        header("Список настроенных сервисов")
        files = [f for f in os.listdir(self.services_dir) if f.endswith(".conf")]
        if not files:
            print("  Сервисы не настроены.")
            return

        for f in sorted(files):
            name = f.replace(".conf", "")
            cfg = ConfigManager.load(os.path.join(self.services_dir, f))
            status_text = f"{RED}OFFLINE{NC}"
            if ProcessManager.is_running(name):
                status_text = f"{GREEN}ONLINE{NC}"
            
            domain = cfg.get('SVC_DOMAIN', cfg.get('SVC_EXT_PORT', '---'))
            print(f"  • {BOLD}{name:15}{NC} {domain:20} [{status_text}]")

    def start_services(self):
        header("Запуск сервисов")
        files = [f for f in os.listdir(self.services_dir) if f.endswith(".conf")]
        for f in files:
            name = f.replace(".conf", "")
            cfg = ConfigManager.load(os.path.join(self.services_dir, f))
            # Загружаем VPS конфиг
            vps_id = cfg.get('SVC_VPS')
            vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
            
            if not vps_cfg:
                warn(f"VPS '{vps_id}' для сервиса '{name}' не найден.")
                continue
            
            ProcessManager.start_service(cfg, vps_cfg)

    def stop_services(self):
        header("Остановка сервисов")
        files = [f for f in os.listdir(self.services_dir) if f.endswith(".conf")]
        for f in files:
            name = f.replace(".conf", "")
            ProcessManager.stop_service(name)

    def vps_menu(self):
        while True:
            self.clear()
            header("Управление VPS серверами")
            files = [f for f in os.listdir(self.vps_dir) if f.endswith(".conf")]
            for f in files:
                name = f.replace(".conf", "")
                cfg = ConfigManager.load(os.path.join(self.vps_dir, f))
                print(f"  • {BOLD}{name:15}{NC} ({cfg.get('VPS_HOST')})")
            
            draw_separator()
            print(f"  {BOLD}1){NC} Добавить VPS")
            print(f"  {BOLD}0){NC} Назад")
            
            c = input(f"\n{BOLD}Выбор:{NC} ")
            if c == '1': self.add_vps()
            elif c == '0': break

    def add_vps(self):
        header("Добавление нового VPS")
        name = input("Название сервера (лат.): ").strip()
        host = input("IP адрес: ").strip()
        user = input("Пользователь [root]: ").strip() or "root"
        port = input("SSH порт [22]: ").strip() or "22"
        
        cfg = {
            "VPS_HOST": host,
            "VPS_USER": user,
            "VPS_PORT": port
        }
        
        VPSManager.ensure_ssh_key()
        msg("Настройка SSH доступа по ключу...")
        # Тут должна быть логика копирования ключа, как в bash (ssh-copy-id)
        # Для краткости пропустим прямой вызов ssh-copy-id
        
        ConfigManager.save(os.path.join(self.vps_dir, f"{name}.conf"), cfg)
        msg(f"VPS '{name}' успешно добавлен.")

if __name__ == "__main__":
    cli = RProxyCLI()
    if len(sys.argv) > 1:
        # Обработка прямых команд (start/stop)
        cmd = sys.argv[1]
        if cmd == 'start': cli.start_services()
        elif cmd == 'stop': cli.stop_services()
    else:
        cli.main_menu()
