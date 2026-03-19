#!/opt/bin/python3
import sys
import os
import random
import subprocess
from core.utils import msg, pause, warn, err, header, draw_separator, get_router_ip, BOLD, NC, GREEN, RED, YELLOW, CYAN, DIM, _resolve_bin, _get_ssh_args
from core.config import ConfigManager
from core.vps import VPSManager
from core.manager import ProcessManager
VERSION = "7.4.3"

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
            print(f"  {BOLD}12){NC} 🔍  Тестирование сервиса (Debug)")
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
            elif choice == '12': self.test_menu()
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
            cfg_path = os.path.join(self.services_dir, f"{name}.conf")
            cfg = ConfigManager.load(cfg_path)
            vps_id = cfg.get('SVC_VPS')
            vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
            if vps_cfg:
                ProcessManager.start_service(cfg, vps_cfg)
                # Сохраняем статус для автозагрузки
                cfg['SVC_ENABLED'] = 'yes'
                ConfigManager.save(cfg_path, cfg)
            else:
                err(f"VPS {vps_id} не найден.")

    def stop_menu(self):
        names = self.select_service("Остановить туннель", 'running')
        for name in names:
            msg(f"Остановка {name}...")
            ProcessManager.stop_service(name)
            
            # Сохраняем статус для автозагрузки
            cfg_path = os.path.join(self.services_dir, f"{name}.conf")
            if os.path.exists(cfg_path):
                cfg = ConfigManager.load(cfg_path)
                cfg['SVC_ENABLED'] = 'no'
                ConfigManager.save(cfg_path, cfg)

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
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(files):
                    self.vps_details_menu(files[idx].replace(".conf", ""))

    def vps_details_menu(self, name):
        while True:
            self.clear()
            cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{name}.conf"))
            header(f"VPS: {name} ({cfg.get('VPS_HOST')})")
            
            print(f"  {BOLD}1){NC} Тест доступа и статуса")
            print( f"  {BOLD}2){NC} {YELLOW}Ремонт (Восстановить SSH и окружение){NC}")
            print(f"  {BOLD}3){NC} {RED}Удалить сервер{NC}")
            print(f"  {BOLD}0){NC} Назад")
            
            draw_separator()
            choice = input(f"\n{BOLD}Выбор:{NC} ")
            
            if choice == '0': break
            elif choice == '1':
                msg("Проверка связи...")
                success, output = VPSManager.run_remote(cfg, "echo Connection OK")
                if success:
                    msg("✅ SSH доступ: РАБОТАЕТ")
                    res = VPSManager.health_check(cfg)
                    msg(f"✅ Nginx: {res['nginx']}")
                    msg(f"✅ SSL Timer: {res['ssl_timer']}")
                else:
                    err(f"❌ Доступ закрыт: {output}")
                pause()
            
            elif choice == '2':
                warn("Начинаю ремонт доступа...")
                self.add_ssh_key_manually(cfg)
                success, output = VPSManager.run_remote(cfg, "echo Connection OK")
                if success:
                    msg("✅ Доступ восстановлен. Запускаю настройку окружения...")
                    VPSManager.setup_vps(cfg)
                    msg("✅ Ремонт завершен!")
                else:
                    err(f"❌ Не удалось восстановить доступ: {output}")
                pause()
                
            elif choice == '3':
                res = input(f"{RED}Вы уверены, что хотите удалить {name}? [y/N]:{NC} ").strip().lower()
                if res == 'y':
                    os.remove(os.path.join(self.vps_dir, f"{name}.conf"))
                    msg(f"VPS {name} удален.")
                    return

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
        pub_key_path = f"{VPSManager.SSH_KEY}.pub"
        
        try:
            with open(pub_key_path, 'r') as f:
                pub_key = f.read().strip()
            
            cmd = f"mkdir -p ~/.ssh && echo '{pub_key}' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
            
            ssh_bin = _resolve_bin("ssh")
            args = _get_ssh_args(ssh_bin, host, user, port)
            ssh_cmd = [ssh_bin] + args + [f"{user}@{host}", cmd]
            
            subprocess.run(ssh_cmd, env=ProcessManager._get_env())
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
        
        # Проверка авторизации
        success, _ = VPSManager.run_remote(cfg, "echo OK")
        if not success:
            warn("SSH-ключ не принят сервером (Permission denied).")
            print(f"  {YELLOW}Подсказка: убедитесь, что на VPS разрешен вход root по паролю (PermitRootLogin yes).{NC}")
            res = input(f"{BOLD}Хотите попробовать добавить ключ повторно? [Y/n]:{NC} ").strip().lower()
            if res != 'n':
                self.add_ssh_key_manually(cfg)
                # Перепроверка
                success, _ = VPSManager.run_remote(cfg, "echo OK")

        if success:
            # Инициализация VPS (установка Nginx, socat и т.д.)
            VPSManager.setup_vps(cfg)
        else:
            err("Не удалось установить SSH-доступ. Дальнейшая настройка невозможна.")

    def add_ssh_key_manually(self, cfg):
        """Повторная попытка проброса SSH ключа"""
        host = cfg.get('VPS_HOST')
        user = cfg.get('VPS_USER')
        port = cfg.get('VPS_PORT')
        pub_key_path = f"{VPSManager.SSH_KEY}.pub"
        
        try:
            VPSManager.ensure_ssh_key()
            if not os.path.exists(pub_key_path):
                err("Публичный ключ не найден.")
                return False

            with open(pub_key_path, 'r') as f:
                pub_key = f.read().strip()
            
            msg(f"Пробрасываю ключ на {host} (потребуется пароль)...")
            cmd = f"mkdir -p ~/.ssh && echo '{pub_key}' >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
            
            ssh_bin = _resolve_bin("ssh")
            args = _get_ssh_args(ssh_bin, host, user, port)
            ssh_cmd = [ssh_bin] + args + [f"{user}@{host}", cmd]
            
            result = subprocess.run(ssh_cmd, env=ProcessManager._get_env(), capture_output=True, text=True)
            if result.returncode != 0:
                err(f"Ошибка проброса ключа: {result.stderr.strip()}")
                return False
            return True
        except Exception as e:
            err(f"Ошибка: {e}")
            return False

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
        header("Добавить сервис" if not edit_name else f"Редактирование: {edit_name}")
        print(f"  {DIM}Введите 0 на любом шаге для возврата назад{NC}")
        
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
                res = input(f"\n{BOLD}Шаг 1/9. Название (лат. без пробелов):{NC} ").strip()
                if res == "0": return
                if not res or os.path.exists(os.path.join(self.services_dir, f"{res}.conf")):
                    warn("Некорректное имя или сервис существует.")
                else:
                    name = res
                    step = 2
            
            elif step == 2: # Тип
                types = [
                    ("http", "Веб (HTTP) — сайты, панели управления"),
                    ("tcp",  "Порт (TCP) — SSH (22), БД, сырой трафик"),
                    ("ttyd", "Терминал (ttyd) — консоль в браузере"),
                    ("ssh",  "SSH Access — прямое управление"),
                    ("udp",  "UDP Port — WireGuard, игры, VPN")
                ]
                print(f"\n{BOLD}Шаг 2/9. Выберите тип сервиса (сейчас: {svc_type}):{NC}")
                for idx, (code, desc) in enumerate(types, 1):
                    mark = f"{GREEN}●{NC}" if code == svc_type else " "
                    print(f"  {BOLD}{idx}){NC} {desc} {mark}")
                
                res = input(f"\n{BOLD}▸ Выберите [1-4]:{NC} ").strip()
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
                    target_port = old_cfg.get('SVC_TARGET_PORT', random.randint(7682, 7782))
                    msg(f"Для ttyd будет использован порт {target_port}")
                    step = 4
                    continue
                
                print(f"\n{BOLD}Шаг 3/9. Цель локально (IP:порт){NC}")
                res = input(f"Адрес [{target_host}:{target_port}]: ").strip()
                if res == "0": step = 2; continue
                if res:
                    if ":" in res:
                        target_host, target_port = res.split(":", 1)
                    else:
                        target_port = res
                step = 4

            elif step == 4: # Режим (Домен или Порт)
                if svc_type == 'udp':
                    msg("UDP поддерживает только публикацию через внешний порт.")
                    domain = ""
                    use_ssl = "no"
                    step = 6
                    continue
                
                print(f"\n{BOLD}Шаг 4/9. Режим публикации{NC}")
                print(f"  {BOLD}1){NC} Домен (SSL, порт 443)")
                print(f"  {BOLD}2){NC} Внешний порт (IP, без SSL)")
                mode = input(f"\n{BOLD}Ваш выбор [1]:{NC} ").strip() or "1"
                if mode == "0": step = 3; continue
                if mode == "1":
                    step = 5
                else:
                    domain = ""
                    use_ssl = "no"
                    step = 6

            elif step == 5: # Домен
                import re
                print(f"\n{BOLD}Шаг 5/9. Внешний адрес (домен или IP){NC}")
                res = input(f"Введите адрес [{domain}]: ").strip() or domain
                if res == "0": step = 4; continue
                if not res:
                    warn("Адрес обязателен для этого режима.")
                    continue
                domain = res
                use_ssl = "yes"
                
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", domain):
                    msg(f"{YELLOW}Замечен IP адрес. Будет предложен 6-дневный SSL сертификат.{NC}")

                # Синхронизация с shell: ввод порта даже для домена
                ext_def = ext_port or "443"
                res_port = input(f"Внешний порт (на VPS) [{ext_def}]: ").strip() or ext_def
                if res_port == "0": step = 4; continue
                ext_port = res_port
                step = 6

            elif step == 6: # Внешний порт (если не домен)
                if domain: 
                    step = 7
                    continue
                print(f"\n{BOLD}Шаг 6/9. Внешний порт на VPS{NC}")
                def_port = ext_port or "26000"
                res = input(f"Порт [{def_port}]: ").strip() or def_port
                if res == "0": step = 4; continue
                ext_port = res
                step = 7

            elif step == 7: # VPS
                vps_files = [f.replace('.conf', '') for f in os.listdir(self.vps_dir) if f.endswith('.conf')]
                if not vps_files:
                    err("Сначала добавьте VPS в меню 9!"); return
                
                # Автоопределение если домен
                if domain and not vps_id:
                    print(f"\n{BOLD}Шаг 7/9. Выбор сервера{NC}")
                    msg(f"Проверяю куда направлен домен {domain}...")
                    found = VPSManager.find_vps_by_domain(domain)
                    if found:
                        msg(f"Домен {domain} указывает на ваш VPS: {GREEN}{found}{NC}")
                        ans = input(f"▸ Использовать этот сервер? (y/n) [y]: ").strip().lower() or "y"
                        if ans == "y":
                            vps_id = found
                            step = 8
                            continue
                
                print(f"\n{BOLD}Шаг 7/9. Выбор VPS сервера{NC}")
                v_def = vps_id or vps_files[0]
                
                # Вывод нумерованного списка
                for idx, v_name in enumerate(vps_files, 1):
                    star = f"{GREEN}*{NC}" if v_name == v_def else " "
                    print(f"  {BOLD}{idx}){NC} {v_name:<15} {star}")
                
                res = input(f"\n{BOLD}Выберите номер или название [{v_def}]:{NC} ").strip() or v_def
                if res == "0": 
                    step = 5 if domain else 6
                    continue
                
                # Обработка выбора по номеру
                if res.isdigit():
                    idx = int(res) - 1
                    if 0 <= idx < len(vps_files):
                        res = vps_files[idx]
                    else:
                        warn("Неверный номер сервера.")
                        continue
                
                if res not in vps_files:
                    warn("Такой VPS не найден.")
                    continue
                vps_id = res
                step = 8

            elif step == 8: # Авторизация
                # Загружаем глобальный конфиг
                g_path = os.path.join(self.root, "rproxy.conf")
                g_cfg = ConfigManager.load(g_path)
                
                has_defaults = 'DEFAULT_AUTH_USER' in g_cfg and 'DEFAULT_AUTH_PASS' in g_cfg
                def_user = g_cfg.get('DEFAULT_AUTH_USER', '')
                def_pass = g_cfg.get('DEFAULT_AUTH_PASS', '')

                print(f"\n{BOLD}Шаг 8/9. Защита доступа (Basic Auth){NC}")
                if has_defaults:
                    print(f"  {GREEN}✔ Найдены сохраненные данные{NC}")
                    print(f"  {BOLD}1){NC} Использовать: {CYAN}{def_user}{NC} / {CYAN}{def_pass}{NC}")
                else:
                    print(f"  {YELLOW}⚠ Сохраненные данные не найдены{NC}")
                    print(f"  {BOLD}1){NC} Заполнить стандартные данные (сохранить в конфиг)")
                
                print(f"  {BOLD}2){NC} Ввести логин и пароль вручную (только для этого сервиса)")
                print(f"  {BOLD}0){NC} Без защиты (отключить)")
                
                res = input(f"\n{BOLD}▸ Ваш выбор [1]:{NC} ").strip() or "1"
                if res == "0":
                    auth_user = ""
                    auth_pass = ""
                    step = 9
                elif res == "1":
                    if not has_defaults:
                        # Предлагаем заполнить
                        print(f"\n{CYAN}▸ Настройка стандартных данных для всех новых сервисов{NC}")
                        u = input(f"    Логин [rproxy]: ").strip() or "rproxy"
                        p = input(f"    Пароль: ").strip()
                        if not p: 
                            warn("Пароль не может быть пустым.")
                            continue
                        g_cfg['DEFAULT_AUTH_USER'] = u
                        g_cfg['DEFAULT_AUTH_PASS'] = p
                        ConfigManager.save(g_path, g_cfg)
                        msg("Данные сохранены в rproxy.conf")
                        auth_user = u
                        auth_pass = p
                    else:
                        auth_user = def_user
                        auth_pass = def_pass
                    step = 9
                elif res == "2":
                    u_def = auth_user or "admin"
                    auth_user = input(f"    Логин [{u_def}]: ").strip() or u_def
                    auth_pass = input(f"    Пароль: ").strip() or auth_pass
                    step = 9
                else:
                    step = 7; continue

            elif step == 9: # Итог и Сохранение
                tunnel_port = old_cfg.get('SVC_TUNNEL_PORT', random.randint(10000, 15000))
                vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf"))
                vps_ip = vps_cfg.get('VPS_HOST', '---')

                header("Итоговая конфигурация")
                print(f"  Сервис:        {CYAN}{name}{NC}")
                print(f"  VPS:           {CYAN}{vps_id} ({vps_ip}){NC}")
                print(f"  Цель:          {CYAN}{target_host}:{target_port}{NC}")
                print(f"  Туннель:       {CYAN}порт {tunnel_port}{NC}")
                print(f"  Внешний:       {CYAN}{domain or 'IP'}:{ext_port}{NC}")
                print(f"  Тип прокси:    {CYAN}{svc_type}{NC}")
                print(f"  Авторизация:   {CYAN}{'yes' if auth_user else 'no'}{NC}")
                draw_separator()
                
                res = input(f"\n{BOLD}▸ Всё верно? Сохранить сервис? (y/n) [y]:{NC} ").strip().lower() or "y"
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
                
                if input(f"\n{BOLD}▸ Запустить туннель сейчас? (y/n) [y]:{NC} ").lower() != 'n':
                    v_path = os.path.join(self.vps_dir, f"{vps_id}.conf")
                    vps_cfg = ConfigManager.load(v_path)
                    if ProcessManager.start_service(new_cfg, vps_cfg):
                        # Финальная инструкция
                        proto = "https" if domain and (ext_port == "443" or use_ssl == "yes") else "http"
                        url = f"{proto}://{domain}" if domain else f"http://{vps_ip}:{ext_port}"
                        if domain and ext_port != "443" and ext_port != "80":
                            url = f"{proto}://{domain}:{ext_port}"
                        
                        print(f"\n{GREEN}──────────────────────────────────────────────────{NC}")
                        print(f"  {BOLD}Инструкция по подключению:{NC}")
                        print(f"  Сервис доступен по адресу: {CYAN}{url}{NC}")
                        print(f"{GREEN}──────────────────────────────────────────────────{NC}")
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

    def health_check_menu(self):
        self.clear()
        header("Проверка VPS (Health)")
        
        vps_files = sorted([f for f in os.listdir(self.vps_dir) if f.endswith(".conf")])
        if not vps_files:
            warn("Нет настроенных VPS для проверки.")
            return

        for f in vps_files:
            vps_id = f.replace(".conf", "")
            vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f))
            v_host = vps_cfg.get('VPS_HOST', '---')
            
            print(f"\n{BOLD}Сервер: {CYAN}{vps_id}{NC} ({v_host})")
            
            print(f"{DIM}▸ Проверяю Nginx...{NC}")
            status = VPSManager.health_check(vps_cfg)
            nx_status = status.get('nginx', 'Unknown')
            nx_color = GREEN if nx_status == "Запущен" else RED
            print(f"  Nginx:        {nx_color}{nx_status}{NC}")
            
            print(f"{DIM}▸ Проверяю автопродление SSL (Certbot)...{NC}")
            timer = status.get('ssl_timer', 'Unknown')
            timer_color = GREEN if "Активен" in timer else YELLOW
            print(f"  SSL Timer:    {timer_color}{timer}{NC}")
            
            next_run = status.get('next_run')
            if next_run:
                print(f"  Следующее:    {CYAN}{next_run}{NC}")

            print(f"{DIM}▸ Действующие сертификаты:{NC}")
            certs = status.get('certs', [])
            if not certs:
                print(f"  {YELLOW}Сертификаты не найдены{NC}")
            else:
                for cert in certs:
                    domains = cert.get('domains', '---')
                    expiry = cert.get('expiry', '---')
                    days = cert.get('days', 0)
                    day_color = GREEN if days > 10 else RED
                    print(f"  {BOLD}Domains:{NC} {CYAN}{domains}{NC}")
                    print(f"  Expiry Date: {expiry} ({day_color}VALID: {days} days{NC})")

        draw_separator()
        print(f"\n{BOLD}▸ Утилиты на роутере:{NC}")
        
        # Проверка SSH утилит
        entware_ssh = "/opt/bin/ssh"
        system_ssh = "ssh"
        
        e_status = f"{GREEN}Entware OK{NC}" if os.path.exists(entware_ssh) else f"{RED}Missing{NC}"
        print(f"  SSH:          {e_status}")
        
        try:
            import subprocess
            subprocess.run(["ssh", "-V"], capture_output=True, check=True)
            s_status = f"{GREEN}System OK{NC}"
        except:
            s_status = f"{RED}Missing{NC}"
        print(f"  SSH:          {s_status}")
        
    def test_menu(self):
        self.clear()
        header("Тестирование и отладка сервиса")
        
        names = self.select_service("Выберите сервис для тестирования")
        if not names: return
        
        for name in names:
            cfg = ConfigManager.load(os.path.join(self.services_dir, f"{name}.conf"))
            vps_id = cfg.get('SVC_VPS')
            vps_cfg = ConfigManager.load(os.path.join(self.vps_dir, f"{vps_id}.conf")) if vps_id else None
            
            if not vps_cfg:
                err(f"Конфигурация VPS '{vps_id}' для сервиса '{name}' не найдена!")
                continue
                
            ProcessManager.test_service(cfg, vps_cfg)

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
        elif cmd == 'test':
            if len(sys.argv) > 2:
                name = sys.argv[2]
                cfg = ConfigManager.load(os.path.join(cli.services_dir, f"{name}.conf"))
                vps_cfg = ConfigManager.load(os.path.join(cli.vps_dir, f"{cfg.get('SVC_VPS')}.conf"))
                if vps_cfg: ProcessManager.test_service(cfg, vps_cfg)
            else:
                err("Укажите имя сервиса: rproxy test <name>")
    else:
        cli.main_menu()
