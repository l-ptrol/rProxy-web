import os
import time
import sys
import json
import random
import bottle
from bottle import route, run, template, request, response, static_file, post, get, delete, HTTPResponse, debug

# Импорт нового ядра
from core.config import ConfigManager
from core.manager import ProcessManager
from core.vps import VPSManager

# Пути rProxy
RPROXY_ROOT = "/opt/etc/rproxy"
SERVICES_DIR = os.path.join(RPROXY_ROOT, "services")
VPS_DIR = os.path.join(RPROXY_ROOT, "vps")

VERSION = "7.3.2"

# Многопоточный сервер для Bottle
from wsgiref.simple_server import WSGIServer, WSGIRequestHandler
from socketserver import ThreadingMixIn

class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True

class ThreadingServer(bottle.ServerAdapter):
    def run(self, handler):
        from wsgiref.simple_server import make_server
        srv = make_server(self.host, self.port, handler, server_class=ThreadingWSGIServer)
        srv.serve_forever()

# Настройка Bottle
bottle.TEMPLATE_PATH.insert(0, './templates')
debug(True)

# ==================== API: Система ====================

@post('/api/system/action')
def system_action():
    try:
        data = request.json or {}
        action = data.get('action')
        if action == 'restart':
            os.system("rproxy restart >/dev/null 2>&1 &")
            return {"status": "success"}
        elif action == 'stop':
            os.system("rproxy stop >/dev/null 2>&1 &")
            return {"status": "success"}
        elif action == 'reboot':
            os.system("reboot >/dev/null 2>&1 &")
            return {"status": "success"}
        response.status = 400
        return {"status": "error", "message": "Unknown action"}
    except Exception as e:
        response.status = 500
        return {"status": "error", "message": str(e)}

@post('/api/system/update')
def update_system():
    try:
        ProcessManager.self_update(web=True)
        return {"status": "success"}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        # Записываем ошибку в лог для отладки
        try:
            with open('/tmp/rproxy_updater.log', 'w') as f:
                f.write(f"ERROR in update_system:\n{tb}\n")
        except Exception:
            pass
        response.status = 500
        return {"status": "error", "message": str(e), "traceback": tb}

@get('/api/system/update/log')
def get_update_log():
    log_upd = "/tmp/rproxy_updater.log"
    if os.path.exists(log_upd):
        with open(log_upd, 'r', errors='replace') as f:
            return {"log": f.read()}
    return {"log": "Ожидание запуска установщика..."}

@get('/api/system/check_update')
def check_update():
    import urllib.request
    import re
    try:
        url = "https://raw.githubusercontent.com/l-ptrol/rProxy-web/master/install.sh"
        req = urllib.request.Request(url, headers={'User-Agent': 'rProxy Web API'})
        with urllib.request.urlopen(req, timeout=5) as response:
            content = response.read().decode('utf-8')
            match = re.search(r'VERSION="([^"]+)"', content)
            if match:
                latest_version = match.group(1)
                return {
                    "latest": latest_version, 
                    "current": VERSION, 
                    "update_available": latest_version != VERSION
                }
        return {"error": "Version not found in repo"}
    except Exception as e:
        return {"error": str(e)}

@get('/api/dns/resolve')
def resolve_domain():
    import socket
    domain = request.query.get('domain', '').strip()
    if not domain:
        return {"ip": None}
    try:
        ip = socket.gethostbyname(domain)
        return {"ip": ip}
    except Exception as e:
        return {"ip": None, "error": str(e)}

# ==================== Страницы ====================

@route('/')
def index():
    return template('index', version=VERSION)

# ==================== API: Статистика ====================

@get('/api/stats')
def get_stats():
    svc_count = 0
    online_count = 0
    if os.path.exists(SERVICES_DIR):
        files = [f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")]
        svc_count = len(files)
        for f in files:
            if ProcessManager.is_running(f.replace(".conf", "")):
                online_count = online_count + 1

    vps_count = 0
    if os.path.exists(VPS_DIR):
        vps_count = len([f for f in os.listdir(VPS_DIR) if f.endswith(".conf")])

    return {
        "services": svc_count,
        "online": online_count,
        "vps": vps_count,
        "version": VERSION
    }

# ==================== API: Сервисы ====================

@get('/api/services')
def list_services():
    services = []
    if os.path.exists(SERVICES_DIR):
        for f in sorted(os.listdir(SERVICES_DIR)):
            if f.endswith(".conf"):
                name = f.replace(".conf", "")
                cfg = ConfigManager.load(os.path.join(SERVICES_DIR, f))
                services.append({
                    "id": name,
                    "name": name,
                    "type": cfg.get("SVC_TYPE", "http"),
                    "target": f"{cfg.get('SVC_TARGET_HOST', '127.0.0.1')}:{cfg.get('SVC_TARGET_PORT', '')}",
                    "ext_port": cfg.get("SVC_EXT_PORT", ""),
                    "domain": cfg.get("SVC_DOMAIN", ""),
                    "ssl": cfg.get("SVC_SSL", "no") == "yes",
                    "auth": bool(cfg.get("SVC_AUTH_USER")),
                    "status": "online" if ProcessManager.is_running(name) else "offline"
                })
    return {"services": services}


@post('/api/services')
def create_service():
    """Создание нового сервиса через веб-интерфейс"""
    try:
        data = request.json
        if not data:
            return HTTPResponse(status=400, body="Пустой запрос")

        name = data.get('name', '').strip()
        if not name:
            return HTTPResponse(status=400, body="Название обязательно")

        svc_path = os.path.join(SERVICES_DIR, f"{name}.conf")
        if os.path.exists(svc_path):
            return HTTPResponse(status=409, body="Сервис с таким именем уже существует")

        os.makedirs(SERVICES_DIR, exist_ok=True)

        # Генерация порта туннеля
        tunnel_port = random.randint(10000, 15000)

        svc_type = data.get('type', 'http')
        target_port = data.get('target_port', '80')

        # Для ttyd — автоматический порт если не указан
        if svc_type == 'ttyd' and not target_port:
            target_port = str(random.randint(7682, 7782))

        cfg = {
            "SVC_NAME": name,
            "SVC_TYPE": svc_type,
            "SVC_TARGET_HOST": data.get('target_host', '127.0.0.1'),
            "SVC_TARGET_PORT": target_port,
            "SVC_VPS": data.get('vps', ''),
            "SVC_EXT_PORT": data.get('ext_port', '443'),
            "SVC_DOMAIN": data.get('domain', ''),
            "SVC_SSL": data.get('ssl', 'no'),
            "SVC_TUNNEL_PORT": str(tunnel_port),
            "SVC_ENABLED": "yes"
        }

        # Авторизация (Basic Auth)
        auth_user = data.get('auth_user', '').strip()
        auth_pass = data.get('auth_pass', '').strip()
        if auth_user and auth_pass:
            cfg["SVC_AUTH_USER"] = auth_user
            cfg["SVC_AUTH_PASS"] = auth_pass

        ConfigManager.save(svc_path, cfg)
        return {"status": "success", "name": name}
    except Exception as e:
        return HTTPResponse(status=500, body=str(e))


# ==================== API: Деплой сервиса (фоновый) ====================

import threading
import io
import contextlib

@post('/api/services/<name>/deploy')
def deploy_service(name):
    """Запуск полного деплоя сервиса в фоновом потоке с записью лога"""
    svc_path = os.path.join(SERVICES_DIR, f"{name}.conf")
    if not os.path.exists(svc_path):
        return HTTPResponse(status=404, body="Сервис не найден")

    log_file = f"/tmp/rproxy_deploy_{name}.log"

    # Очищаем старый лог
    with open(log_file, 'w') as f:
        f.write(f"▸ Начало деплоя сервиса '{name}'...\n")

    def _deploy_worker():
        """Фоновый воркер — перехватывает stdout/stderr и пишет в лог"""
        import sys as _sys

        class LogWriter:
            """Перехватчик stdout/stderr в файл"""
            def __init__(self, log_path, original):
                self.log_path = log_path
                self.original = original
            def write(self, text):
                if text.strip():
                    # Очистка ANSI-кодов
                    import re
                    clean = re.sub(r'\x1B\[[0-9;]*[a-zA-Z]', '', text)
                    clean = re.sub(r'\[\d+;\d+m', '', clean).replace('\[0m', '')
                    with open(self.log_path, 'a') as f:
                        f.write(clean)
                        if not clean.endswith('\n'):
                            f.write('\n')
                        f.flush()
                self.original.write(text)
            def flush(self):
                self.original.flush()

        old_stdout = _sys.stdout
        old_stderr = _sys.stderr
        _sys.stdout = LogWriter(log_file, old_stdout)
        _sys.stderr = LogWriter(log_file, old_stderr)

        try:
            cfg = ConfigManager.load(svc_path)
            vps_id = cfg.get('SVC_VPS')
            if not vps_id:
                with open(log_file, 'a') as f:
                    f.write("❌ Ошибка: VPS не указан в конфигурации сервиса.\n")
                    f.write("__DEPLOY_STATUS__:error\n")
                return

            vps_path = os.path.join(VPS_DIR, f"{vps_id}.conf")
            if not os.path.exists(vps_path):
                with open(log_file, 'a') as f:
                    f.write(f"❌ Ошибка: VPS '{vps_id}' не найден.\n")
                    f.write("__DEPLOY_STATUS__:error\n")
                return

            vps_cfg = ConfigManager.load(vps_path)
            result = ProcessManager.start_service(cfg, vps_cfg)

            with open(log_file, 'a') as f:
                if result is False:
                    f.write("\n❌ Деплой завершён с ошибками.\n")
                    f.write("__DEPLOY_STATUS__:error\n")
                else:
                    f.write("\n✅ Сервис успешно развернут и запущен!\n")
                    f.write("__DEPLOY_STATUS__:success\n")
        except Exception as e:
            import traceback
            with open(log_file, 'a') as f:
                f.write(f"\n❌ Критическая ошибка: {e}\n")
                f.write(traceback.format_exc() + "\n")
                f.write("__DEPLOY_STATUS__:error\n")
        finally:
            _sys.stdout = old_stdout
            _sys.stderr = old_stderr

    t = threading.Thread(target=_deploy_worker, daemon=True)
    t.start()
    return {"status": "started", "log": log_file}


@get('/api/services/<name>/deploy/log')
def deploy_log(name):
    """Чтение лога деплоя сервиса"""
    log_file = f"/tmp/rproxy_deploy_{name}.log"
    if os.path.exists(log_file):
        with open(log_file, 'r', errors='replace') as f:
            content = f.read()
        # Определяем статус деплоя
        if "__DEPLOY_STATUS__:success" in content:
            status = "success"
            content = content.replace("__DEPLOY_STATUS__:success\n", "")
        elif "__DEPLOY_STATUS__:error" in content:
            status = "error"
            content = content.replace("__DEPLOY_STATUS__:error\n", "")
        else:
            status = "running"
        return {"log": content, "status": status}
    return {"log": "Ожидание запуска деплоя...", "status": "pending"}


# ==================== API: Настройки (Auth, etc) ====================

@get('/api/settings/auth')
def get_default_auth():
    g_path = os.path.join(RPROXY_ROOT, "rproxy.conf")
    g_cfg = ConfigManager.load(g_path)
    return {
        "user": g_cfg.get('DEFAULT_AUTH_USER', ''),
        "pass": g_cfg.get('DEFAULT_AUTH_PASS', '')
    }

# ==================== API: Действия с сервисами ====================

@post('/api/action/<name>/<action>')
def service_action(name, action):
    svc_path = os.path.join(SERVICES_DIR, f"{name}.conf")
    if not os.path.exists(svc_path):
        return HTTPResponse(status=404, body="Сервис не найден")

    try:
        cfg = ConfigManager.load(svc_path)
        vps_id = cfg.get('SVC_VPS')

        vps_cfg = None
        if vps_id:
            vps_path = os.path.join(VPS_DIR, f"{vps_id}.conf")
            if os.path.exists(vps_path):
                vps_cfg = ConfigManager.load(vps_path)

        if action == 'start':
            if not vps_cfg:
                return HTTPResponse(status=400, body="VPS не найден")
            ProcessManager.start_service(cfg, vps_cfg)
        elif action == 'stop':
            ProcessManager.stop_service(name, svc_cfg=cfg)
        elif action == 'restart':
            ProcessManager.stop_service(name, svc_cfg=cfg)
            time.sleep(1)
            if vps_cfg:
                ProcessManager.start_service(cfg, vps_cfg)
        elif action == 'redeploy_nginx':
            if vps_cfg:
                ProcessManager.redeploy_nginx(cfg, vps_cfg)
        elif action == 'delete':
            ProcessManager.stop_service(name, svc_cfg=cfg)
            # Удаление Nginx конфига с VPS
            if vps_cfg:
                VPSManager.remove_vhost(vps_cfg, name)
            os.remove(svc_path)
        elif action == 'ssl':
            if vps_cfg:
                ProcessManager.run_certbot(cfg, vps_cfg)

        return {"status": "success"}
    except Exception as e:
        return HTTPResponse(status=500, body=str(e))


# ==================== API: Логи ====================

@get('/api/services/<name>/logs')
def service_logs(name):
    """Получение последних строк логов сервиса"""
    log_dir = "/opt/var/log"
    result = {}
    # Лог туннеля
    tunnel_log = os.path.join(log_dir, f"tunnel_{name}.log")
    if os.path.exists(tunnel_log):
        with open(tunnel_log, 'r', errors='replace') as f:
            lines = f.readlines()
            result['tunnel'] = ''.join(lines[-100:])

    # Лог ttyd
    ttyd_log = os.path.join(log_dir, f"ttyd_{name}.log")
    if os.path.exists(ttyd_log):
        with open(ttyd_log, 'r', errors='replace') as f:
            lines = f.readlines()
            result['ttyd'] = ''.join(lines[-100:])

    # Лог autossh
    autossh_log = os.path.join(log_dir, f"autossh_{name}.log")
    if os.path.exists(autossh_log):
        with open(autossh_log, 'r', errors='replace') as f:
            lines = f.readlines()
            result['autossh'] = ''.join(lines[-100:])

    return result


# ==================== API: VPS ====================

@get('/api/vps')
def list_vps():
    vps_list = []
    if os.path.exists(VPS_DIR):
        for f in sorted(os.listdir(VPS_DIR)):
            if f.endswith(".conf"):
                name = f.replace(".conf", "")
                cfg = ConfigManager.load(os.path.join(VPS_DIR, f))
                vps_list.append({
                    "id": name,
                    "name": name,
                    "host": cfg.get("VPS_HOST"),
                    "user": cfg.get("VPS_USER", "root"),
                    "port": cfg.get("VPS_PORT", "22")
                })
    return {"vps": vps_list}


@post('/api/vps')
def create_vps():
    """Добавление нового VPS сервераe"""
    try:
        data = request.json
        if not data:
            return HTTPResponse(status=400, body="Пустой запрос")

        name = data.get('name', '').strip()
        host = data.get('host', '').strip()
        if not name or not host:
            return HTTPResponse(status=400, body="Название и IP обязательны")

        os.makedirs(VPS_DIR, exist_ok=True)
        vps_path = os.path.join(VPS_DIR, f"{name}.conf")

        cfg = {
            "VPS_HOST": host,
            "VPS_USER": data.get('user', 'root').strip(),
            "VPS_PORT": data.get('port', '22').strip(),
            "VPS_AUTH": "key"
        }
        ConfigManager.save(vps_path, cfg)
        return {"status": "success", "name": name}
    except Exception as e:
        return HTTPResponse(status=500, body=str(e))


@delete('/api/vps/<name>')
def delete_vps(name):
    vps_path = os.path.join(VPS_DIR, f"{name}.conf")
    if not os.path.exists(vps_path):
        return HTTPResponse(status=404, body="VPS не найден")
    os.remove(vps_path)
    return {"status": "success"}


@get('/api/vps/<name>/health')
def vps_health(name):
    vps_path = os.path.join(VPS_DIR, f"{name}.conf")
    if not os.path.exists(vps_path):
        return HTTPResponse(status=404, body="VPS не найден")

    vps_cfg = ConfigManager.load(vps_path)
    result = VPSManager.health_check(vps_cfg)
    return result


@post('/api/vps/<name>/cleanup')
def vps_cleanup(name):
    vps_path = os.path.join(VPS_DIR, f"{name}.conf")
    if not os.path.exists(vps_path):
        return HTTPResponse(status=404, body="VPS не найден")

    vps_cfg = ConfigManager.load(vps_path)
    # Список активных сервисов для этого VPS
    active = []
    if os.path.exists(SERVICES_DIR):
        for f in os.listdir(SERVICES_DIR):
            if f.endswith(".conf"):
                cfg = ConfigManager.load(os.path.join(SERVICES_DIR, f))
                if cfg.get('SVC_VPS') == name:
                    active.append(f.replace(".conf", ""))

    success, msg = VPSManager.cleanup_vps(vps_cfg, active)
    return {"status": "success" if success else "error", "message": msg}


# ==================== API: Система ====================

@post('/api/system/update')
def system_update():
    """Запускает самообновление"""
    try:
        ProcessManager.self_update()
        return {"status": "success"}
    except Exception as e:
        return HTTPResponse(status=500, body=str(e))


@post('/api/system/reset')
def system_reset():
    """Полная очистка (Hard Reset)"""
    try:
        # Упрощённая версия (без подтверждения через stdin)
        import shutil
        env = ProcessManager._get_env()
        from core.utils import _resolve_bin
        pkill_bin = _resolve_bin("pkill")
        import subprocess
        subprocess.run([pkill_bin, "-f", "autossh"], env=env, stderr=subprocess.DEVNULL)
        subprocess.run([pkill_bin, "-f", "ttyd"], env=env, stderr=subprocess.DEVNULL)

        paths = ["/opt/etc/rproxy", "/opt/var/run/rproxy"]
        for p in paths:
            if os.path.exists(p):
                if os.path.isdir(p):
                    shutil.rmtree(p)
                else:
                    os.remove(p)

        return {"status": "success", "message": "Все данные очищены"}
    except Exception as e:
        return HTTPResponse(status=500, body=str(e))


if __name__ == "__main__":
    # Многопоточный сервер для параллельных запросов
    run(host='0.0.0.0', port=3000, server=ThreadingServer, quiet=True, debug=False)
