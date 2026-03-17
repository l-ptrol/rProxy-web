#!/opt/bin/python3
import sys
import os
import random
from core.utils import msg, warn, err, header, draw_separator, get_router_ip, BOLD, NC, GREEN, RED, YELLOW, CYAN, DIM
from core.config import ConfigManager
from core.vps import VPSManager
from core.manager import ProcessManager

VERSION = "6.4.3"

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
            
            # Статистика
            total = len([f for f in os.listdir(self.services_dir) if f.endswith(".conf")]) if os.path.exists(self.services_dir) else 0
            vps_count = len([f for f in os.listdir(self.vps_dir) if f.endswith(".conf")]) if os.path.exists(self.vps_dir) else 0
            online = 0
            if os.path.exists(self.services_dir):
                for f in os.listdir(self.services_dir):
                    if f.endswith(".conf") and ProcessManager.is_running(f.replace(".conf", "")):
                        online += 1

            print(f"  {DIM}Серверов VPS:{NC} {BOLD}{vps_count}{NC}  {DIM}Сервисов:{NC} {BOLD}{total}{NC}  {DIM}Онлайн:{NC} {GREEN}{BOLD}{online}{NC}")
            draw_separator()
            
            print(f"  {BOLD}1){NC}  📋  Список сервисов и статус")
            print(f"  {BOLD}2){NC}  ➕  Добавить сервис")
            print(f"  {BOLD}3){NC}  📝  Редактировать сервис")
            print(f"  {BOLD}4){NC}  ❌  Удалить сервис")
            draw_separator()
            print(f"  {BOLD}5){NC}  ▶️   Запустить туннель")
            print(f"  {BOLD}6){NC}  ⏹️   Остановить туннель")
            print(f"  {BOLD}7){NC}  🔄  Перезапустить туннель")
            draw_separator()
            print(f"  {BOLD}8){NC}  🔒  Управление SSL (Certbot)")
            print(f"  {BOLD}9){NC}  ⚙️   Настройки VPS")
            draw_separator()
            print(f"  {BOLD}10){NC} 🚀  Обновить rProxy")
            print(f"  {BOLD}11){NC} 🏥  Проверка VPS (Health)")
            print(f"  {BOLD}99){NC} ☢️   Глубокая очистка (Hard Reset)")
            print(f"  {BOLD}0){NC}      Выход")
            
            choice = input(f"\n{BOLD}Выберите действие:{NC} ")
            
            if choice == '1': self.show_status()
            elif choice == '2': self.add_service()
            elif choice == '3': self.edit_service()
            elif choice == '4': self.remove_service()
            elif choice == '5': self.start_menu()
            elif choice == '6': self.stop_menu()
            elif choice == '7': self.restart_menu()
            elif choice == '8': self.ssl_menu()
            elif choice == '9': self.vps_menu()
            elif choice == '10': ProcessManager.self_update()
            elif choice == '11': self.health_check_menu()
            elif choice == '99': ProcessManager.hard_reset()
            elif choice == '0': break
            
            if choice != '0': input(f"\n{NC}Нажмите Enter для продолжения...")

    def show_status(self):
        self.clear()
        header("Список сервисов")
        files = sorted([f for f in os.listdir(self.services_dir) if f.endswith(".conf")])
        if not files:
            print(f"\n  {YELLOW}Нет добавленных сервисов.{NC}")
            return

        print(f"  {BOLD}{'№':<4} {'ИМЯ':<14} {'ЦЕЛЬ':<22} {'ПОРТ':<7} {'СТАТУС':<9} {'ДОМЕН'}{NC}")
        draw_separator()
        
        for idx, f in enumerate(files, 1):
            name = f.replace(".conf", "")
            cfg = ConfigManager.load(os.path.join(self.services_dir, f))
            is_on = ProcessManager.is_running(name)
            status = f"{GREEN}● онлайн{NC}" if is_on else f"{RED}○ офлайн{NC}"
            
            target = f"{cfg.get('SVC_TARGET_HOST','127.0.0.1')}:{cfg.get('SVC_TARGET_PORT','---')}"
            domain = cfg.get('SVC_DOMAIN', '---')
            port = cfg.get('SVC_EXT_PORT', '---')
            
            print(f"  {idx:<4} {name:<14} {target:<22} {port:<7} {status} {domain}")

    def select_service(self, title, filter_type='all'):
        files = sorted([f for f in os.listdir(self.services_dir) if f.endswith(".conf")])
        if not files:
            warn("Нет сервисов.")
            return []

        header(title)
        shown_files = []
        for idx, f in enumerate(files, 1):
            name = f.replace(".conf", "")
            is_on = ProcessManager.is_running(name)
            
            if filter_type == 'running' and not is_on: continue
            if filter_type == 'stopped' and is_on: continue
            
            status = f"{GREEN}●{NC}" if is_on else f"{RED}○{NC}"
            cfg = ConfigManager.load(os.path.join(self.services_dir, f))
            target = f"{cfg.get('SVC_TARGET_HOST','127.0.0.1')}:{cfg.get('SVC_TARGET_PORT','---')}"
            
            print(f"  {BOLD}{idx}){NC}  {status}  {name:<14}  {target}")
            shown_files.append((idx, name))

        if not shown_files:
            warn("Нет подходящих сервисов.")
            return []

        draw_separator()
        print(f"  {BOLD}903){NC} Все сервисы")
        print(f"  {BOLD}0){NC}   Назад")
        
        ans = input(f"\n{BOLD}Выберите номер(а) (через пробел или 903):{NC} ").strip()
        if ans == '0' or not ans: return []
        if ans == '903': return [name for idx, name in shown_files]
        
        selected = []
        for part in ans.split():
            try:
                val = int(part)
                for idx, name in shown_files:
                    if idx == val:
                        selected.append(name)
            except ValueError: continue
        return selected

    def start_menu(self):
        names = self.select_service("Запустить туннель", 'stopped')
        for name in names:
            msg(f"Запуск {name}...")
            cfg = ConfigManager.load(os.path.join(self.services_dir, f"{name}.conf"))
            vps_id = cfg.get('SVC_VPS')
            vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
            if vps_cfg:
                ProcessManager.start_service(cfg, vps_cfg)
            else:
                err(f"VPS {vps_id} не найден.")

    def stop_menu(self):
        names = self.select_service("Остановить туннель", 'running')
        for name in names:
            msg(f"Остановка {name}...")
            ProcessManager.stop_service(name)

    def restart_menu(self):
        names = self.select_service("Перезапустить туннель")
        for name in names:
            msg(f"Перезапуск {name}...")
            ProcessManager.stop_service(name)
            cfg = ConfigManager.load(os.path.join(self.services_dir, f"{name}.conf"))
            vps_id = cfg.get('SVC_VPS')
            vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
            if vps_cfg:
                ProcessManager.start_service(cfg, vps_cfg)

    def remove_service(self):
        names = self.select_service("Удалить сервис")
        if not names: return
        confirm = input(f"\n{RED}Удалить {len(names)} сервис(ов)? (y/n): {NC}").lower()
        if confirm != 'y': return
        
        for name in names:
            cfg = ConfigManager.load(os.path.join(self.services_dir, f"{name}.conf"))
            ProcessManager.stop_service(name)
            
            # Удаление с VPS
            if cfg:
                vps_id = cfg.get('SVC_VPS')
                vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
                if vps_cfg:
                    msg(f"Удаление конфигурации Nginx на VPS для {name}...")
                    VPSManager.remove_vhost(vps_cfg, name)

            path = os.path.join(self.services_dir, f"{name}.conf")
            if os.path.exists(path):
                os.remove(path)
            msg(f"Сервис {name} полностью удален.")

    def vps_menu(self):
        while True:
            self.clear()
            header("Управление VPS серверами")
            files = sorted([f for f in os.listdir(self.vps_dir) if f.endswith(".conf")])
            for idx, f in enumerate(files, 1):
                name = f.replace(".conf", "")
                cfg = ConfigManager.load(os.path.join(self.vps_dir, f))
                print(f"  {BOLD}{idx}){NC}  {name:<14} ({cfg.get('VPS_HOST')})")
            
            draw_separator()
            print(f"  {BOLD}901){NC} Добавить VPS")
            print(f"  {BOLD}902){NC} Удалить VPS")
            print(f"  {BOLD}0){NC} Назад")
            
            choice = input(f"\n{BOLD}Выбор:{NC} ")
            if choice == '0': break
            elif choice == '901': self.add_vps()
            elif choice == '902': self.remove_vps()

    def add_vps(self):
        header("Добавление нового VPS")
        name = input("Название сервера (лат.): ").strip()
        if not name or os.path.exists(os.path.join(self.vps_dir, f"{name}.conf")):
            warn("Некорректное имя или сервер существует.")
            return

        host = input("IP адрес: ").strip()
        user = input("Пользователь [root]: ").strip() or "root"
        port = input("SSH порт [22]: ").strip() or "22"
        
        VPSManager.ensure_ssh_key()
        msg(f"Настройка SSH доступа для {host}...")
        pub_key_path = "/opt/etc/rproxy/id_ed25519.pub"
        
        try:
            with open(pub_key_path, 'r') as f:
                pub_key = f.read().strip()
            
            cmd = f"mkdir -p ~/.ssh && echo '{pub_key}' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
            os.system(f"ssh -o StrictHostKeyChecking=no -p {port} {user}@{host} \"{cmd}\"")
        except Exception as e:
            err(f"Ошибка настройки ключей: {e}")
            return
        
        cfg = {
            "VPS_HOST": host,
            "VPS_USER": user,
            "VPS_PORT": port,
            "VPS_AUTH": "key"
        }
        ConfigManager.save(os.path.join(self.vps_dir, f"{name}.conf"), cfg)
        msg(f"VPS '{name}' успешно добавлен.")

    def remove_vps(self):
        header("Удаление VPS")
        files = sorted([f for f in os.listdir(self.vps_dir) if f.endswith(".conf")])
        if not files:
            warn("Нет VPS для удаления.")
            return

        for idx, f in enumerate(files, 1):
            print(f"  {idx}) {f.replace('.conf', '')}")
        
        choice = input(f"\n{BOLD}Выберите номер для удаления (0 - отмена):{NC} ")
        if choice == '0' or not choice.isdigit(): return
        
        idx = int(choice) - 1
        if 0 <= idx < len(files):
            name = files[idx].replace('.conf', '')
            confirm = input(f"Удалить конфигурацию '{name}'? (y/n): ")
            if confirm.lower() == 'y':
                os.remove(os.path.join(self.vps_dir, files[idx]))
                msg(f"VPS '{name}' удален.")

    def health_check_menu(self):
        header("Проверка состояния VPS (Health Check)")
        files = sorted([f for f in os.listdir(self.vps_dir) if f.endswith(".conf")])
        if not files:
            warn("Нет добавленных VPS.")
            return

        for f in files:
            name = f.replace(".conf", "")
            cfg = ConfigManager.load(os.path.join(self.vps_dir, f))
            print(f"\n{BOLD}[{name}]{NC} ({cfg.get('VPS_HOST')})")
            success, info = VPSManager.health_check(cfg)
            print(f"  {info}")

    def add_service(self, edit_name=None):
        header("Добавить новый сервис" if not edit_name else f"Редактирование: {edit_name}")
        msg(f"{DIM}Введите 0 на любом шаге для возврата назад{NC}")
        
        old_cfg = {}
        if edit_name:
            old_cfg = ConfigManager.load(os.path.join(self.services_dir, f"{edit_name}.conf"))

        step = 1
        name = edit_name or ""
        svc_type = old_cfg.get('SVC_TYPE', 'http')
        target_host = old_cfg.get('SVC_TARGET_HOST', '127.0.0.1')
        target_port = old_cfg.get('SVC_TARGET_PORT', '80')
        domain = old_cfg.get('SVC_DOMAIN', '')
        ext_port = old_cfg.get('SVC_EXT_PORT', '')
        use_ssl = old_cfg.get('SVC_SSL', 'no')
        vps_id = old_cfg.get('SVC_VPS', '')
        auth_user = old_cfg.get('SVC_AUTH_USER', '')
        auth_pass = old_cfg.get('SVC_AUTH_PASS', '')

        while step > 0:
            draw_separator()
            if step == 1: # Имя
                if edit_name:
                    step = 2
                    continue
                res = input(f"{BOLD}Шаг 1. Название (лат. без пробелов):{NC} ").strip()
                if res == "0": return
                if not res or os.path.exists(os.path.join(self.services_dir, f"{res}.conf")):
                    warn("Некорректное имя или сервис существует.")
                else:
                    name = res
                    step = 2
            
            elif step == 2: # Тип
                types = [("http", "веб"), ("tcp", "порты"), ("ttyd", "терминал"), ("ssh", "удаленный доступ")]
                print(f"\n{BOLD}Шаг 2. Выберите тип сервиса (по умолчанию {svc_type}):{NC}")
                for idx, (code, desc) in enumerate(types, 1):
                    mark = f"{GREEN}●{NC}" if code == svc_type else " "
                    print(f"  {BOLD}{idx}){NC} {code:<6} {DIM}({desc}){NC} {mark}")
                
                res = input(f"\nВариант [1-4]: ").strip()
                if res == "0": 
                    if edit_name: return
                    step = 1; continue
                if res:
                    try:
                        idx = int(res) - 1
                        if 0 <= idx < len(types): svc_type = types[idx][0]
                    except: pass
                step = 3

            elif step == 3: # Цель
                if svc_type == 'ttyd':
                    target_host = "127.0.0.1"
                    target_port = old_cfg.get('SVC_TARGET_PORT', random.randint(7681, 7781))
                    msg(f"Для ttyd будет использован порт {target_port}")
                    step = 4
                    continue
                
                print(f"\n{BOLD}Шаг 3. Цель локально (IP:порт){NC}")
                res = input(f"Адрес [{target_host}:{target_port}]: ").strip()
                if res == "0": step = 2; continue
                if res:
                    if ":" in res:
                        target_host, target_port = res.split(":", 1)
                    else:
                        target_port = res
                step = 4

            elif step == 4: # Режим (Домен или Порт)
                print(f"\n{BOLD}Шаг 4. Режим публикации{NC}")
                print(f"  {BOLD}1){NC} Домен (SSL, порт 443)")
                print(f"  {BOLD}2){NC} Внешний порт (без SSL)")
                mode = input(f"Ваш выбор [1]: ").strip() or "1"
                if mode == "0": step = 3; continue
                if mode == "1":
                    step = 5
                else:
                    domain = ""
                    use_ssl = "no"
                    step = 6

            elif step == 5: # Домен
                res = input(f"Введите домен [{domain}]: ").strip() or domain
                if res == "0": step = 4; continue
                if not res:
                    warn("Домен обязателен для этого режима.")
                    continue
                domain = res
                use_ssl = "yes"
                
                # Синхронизация с shell: ввод порта даже для домена
                ext_def = ext_port or "443"
                res_port = input(f"Внешний порт [{ext_def}]: ").strip() or ext_def
                if res_port == "0": step = 4; continue
                ext_port = res_port
                step = 6

            elif step == 6: # Внешний порт (если не домен)
                if domain: 
                    step = 7
                    continue
                print(f"\n{BOLD}Шаг 6. Внешний порт на VPS{NC}")
                def_port = ext_port or "26000"
                res = input(f"Порт [{def_port}]: ").strip() or def_port
                if res == "0": step = 4; continue
                ext_port = res
                step = 7

            elif step == 7: # VPS
                # Автоопределение если домен
                if domain and not vps_id:
                    msg(f"Проверяю резолв домена {domain}...")
                    found = VPSManager.find_vps_by_domain(domain)
                    if found:
                        msg(f"Домен указывает на VPS: {GREEN}{found}{NC}")
                        vps_id = found
                
                vps_files = [f.replace('.conf', '') for f in os.listdir(self.vps_dir) if f.endswith('.conf')]
                if not vps_files:
                    err("Сначала добавьте VPS в меню 9!"); return
                
                print(f"\n{BOLD}Шаг 7. Выбор VPS сервера{NC}")
                v_def = vps_id or vps_files[0]
                print(f"  Доступные: {', '.join(vps_files)}")
                res = input(f"Выберите VPS [{v_def}]: ").strip() or v_def
                if res == "0": 
                    step = 5 if domain else 6
                    continue
                if res not in vps_files:
                    warn("Такой VPS не найден.")
                    continue
                vps_id = res
                step = 8

            elif step == 8: # Авторизация
                print(f"\n{BOLD}Шаг 8. Защита паролем (Basic Auth){NC}")
                auth_now = "yes" if auth_user else "no"
                res = input(f"Использовать защиту? (yes/no) [{auth_now}]: ").strip() or auth_now
                if res == "0": step = 7; continue
                if res == "yes":
                    u_def = auth_user or "admin"
                    auth_user = input(f"Логин [{u_def}]: ").strip() or u_def
                    auth_pass = input(f"Пароль: ").strip() or auth_pass
                else:
                    auth_user = ""
                    auth_pass = ""
                step = 9

            elif step == 9: # Итог и Сохранение
                tunnel_port = old_cfg.get('SVC_TUNNEL_PORT', random.randint(10000, 15000))
                
                header("Итоговая конфигурация")
                print(f"  Имя:           {CYAN}{name}{NC}")
                print(f"  Тип:           {CYAN}{svc_type}{NC}")
                print(f"  Цель:          {CYAN}{target_host}:{target_port}{NC}")
                print(f"  VPS:           {CYAN}{vps_id}{NC}")
                print(f"  Туннель порт:  {CYAN}{tunnel_port}{NC}")
                print(f"  Внешний:       {CYAN}{domain or 'IP'}:{ext_port}{NC}")
                print(f"  SSL/Auth:      {CYAN}SSL:{use_ssl} / Auth:{'yes' if auth_user else 'no'}{NC}")
                draw_separator()
                
                res = input(f"\n{BOLD}Все верно? Сохранить? (y/n) [y]:{NC} ").strip().lower() or "y"
                if res == "0": step = 8; continue
                if res != "y": msg("Отменено"); return
                
                new_cfg = {
                    "SVC_NAME": name,
                    "SVC_TYPE": svc_type,
                    "SVC_TARGET_HOST": target_host,
                    "SVC_TARGET_PORT": target_port,
                    "SVC_VPS": vps_id,
                    "SVC_EXT_PORT": ext_port,
                    "SVC_DOMAIN": domain,
                    "SVC_SSL": use_ssl,
                    "SVC_TUNNEL_PORT": tunnel_port,
                    "SVC_ENABLED": "yes"
                }
                if auth_user:
                    new_cfg["SVC_AUTH_USER"] = auth_user
                    new_cfg["SVC_AUTH_PASS"] = auth_pass

                ConfigManager.save(os.path.join(self.services_dir, f"{name}.conf"), new_cfg)
                msg(f"Сервис '{name}' успешно сохранен.")
                
                if input("\nЗапустить сейчас? (y/n) [y]: ").lower() != 'n':
                    v_path = os.path.join(self.vps_dir, f"{vps_id}.conf")
                    vps_cfg = ConfigManager.load(v_path)
                    ProcessManager.start_service(new_cfg, vps_cfg)
                return

    def edit_service(self):
        names = self.select_service("Редактирование сервиса")
        if not names: return
        name = names[0]
        
        while True:
            self.clear()
            header(f"Редактирование: {name}")
            print(f"  {BOLD}1){NC} Изменить параметры (IP, Порты, SSL...)")
            print(f"  {BOLD}2){NC} Исправить (перезаписать) конфигурацию nginx")
            print(f"  {BOLD}0){NC} Назад")
            
            choice = input(f"\n{BOLD}Выбор:{NC} ")
            if choice == '1':
                self.add_service(edit_name=name)
                break
            elif choice == '2':
                cfg = ConfigManager.load(os.path.join(self.services_dir, f"{name}.conf"))
                vps_id = cfg.get('SVC_VPS')
                vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
                if vps_cfg:
                    ProcessManager.redeploy_nginx(cfg, vps_cfg)
                else:
                    err(f"VPS {vps_id} не найден.")
                input(f"\n{NC}Нажмите Enter для продолжения...")
            elif choice == '0':
                break

    def ssl_menu(self):
        header("Управление SSL (Certbot)")
        names = self.select_service("Выберите сервис для настройки SSL", 'all')
        if not names: return
        
        for name in names:
            cfg = ConfigManager.load(os.path.join(self.services_dir, f"{name}.conf"))
            domain = cfg.get('SVC_DOMAIN')
            if not domain:
                warn(f"Сервис {name} не имеет привязанного домена.")
                continue
            
            vps_id = cfg.get('SVC_VPS')
            vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
            if not vps_cfg:
                err(f"VPS {vps_id} не найден.")
                continue
            
            msg(f"Запуск Certbot для {domain}...")
            ProcessManager.run_certbot(cfg, vps_cfg)

if __name__ == "__main__":
    cli = RProxyCLI()
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == 'boot':
            msg("Автозапуск включенных сервисов (boot)...")
            if os.path.exists(cli.services_dir):
                for f in sorted(os.listdir(cli.services_dir)):
                    if f.endswith(".conf"):
                        cfg = ConfigManager.load(os.path.join(cli.services_dir, f))
                        if cfg.get('SVC_ENABLED') == 'yes':
                            vps_id = cfg.get('SVC_VPS')
                            vps_cfg = ConfigManager.load(os.path.join(cli.vps_dir, f"{vps_id}.conf"))
                            if vps_cfg:
                                msg(f"Автозапуск сервиса: {cfg.get('SVC_NAME')}...")
                                ProcessManager.start_service(cfg, vps_cfg)
        elif cmd == 'start': 
            if len(sys.argv) > 2:
                name = sys.argv[2]
                cfg = ConfigManager.load(os.path.join(cli.services_dir, f"{name}.conf"))
                vps_cfg = ConfigManager.load(os.path.join(cli.vps_dir, f"{cfg.get('SVC_VPS')}.conf"))
                if vps_cfg: ProcessManager.start_service(cfg, vps_cfg)
            else:
                for f in sorted(os.listdir(cli.services_dir)):
                    if f.endswith(".conf"):
                        cfg = ConfigManager.load(os.path.join(cli.services_dir, f))
                        if cfg.get('SVC_ENABLED') == 'yes':
                            vps_cfg = ConfigManager.load(os.path.join(cli.vps_dir, f"{cfg.get('SVC_VPS')}.conf"))
                            if vps_cfg: ProcessManager.start_service(cfg, vps_cfg)
        elif cmd == 'stop':
            if len(sys.argv) > 2: ProcessManager.stop_service(sys.argv[2])
            else:
                for f in os.listdir(cli.services_dir):
                    if f.endswith(".conf"): ProcessManager.stop_service(f.replace(".conf", ""))
    else:
        cli.main_menu()
