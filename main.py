import os
import time
import bottle
from bottle import route, run, template, request, response, static_file, post, get, HTTPResponse, debug

# Импорт нового ядра
from core.config import ConfigManager
from core.manager import ProcessManager
from core.vps import VPSManager

# Пути rProxy
RPROXY_ROOT = "/opt/etc/rproxy"
SERVICES_DIR = os.path.join(RPROXY_ROOT, "services")
VPS_DIR = os.path.join(RPROXY_ROOT, "vps")

VERSION = "6.2.1"

# Настройка Bottle
bottle.TEMPLATE_PATH.insert(0, './templates')
debug(True)

@route('/')
def index():
    return template('index', version=VERSION)

@get('/api/stats')
def get_stats():
    svc_count = 0
    online_count = 0
    if os.path.exists(SERVICES_DIR):
        files = [f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")]
        svc_count = len(files)
        for f in files:
            if ProcessManager.is_running(f.replace(".conf", "")):
                online_count += 1
    
    vps_count = 0
    if os.path.exists(VPS_DIR):
        vps_count = len([f for f in os.listdir(VPS_DIR) if f.endswith(".conf")])

    return {
        "services": svc_count,
        "online": online_count,
        "vps": vps_count,
        "version": VERSION
    }

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
                    "status": "online" if ProcessManager.is_running(name) else "offline"
                })
    return {"services": services}

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
                    "user": cfg.get("VPS_USER", "root")
                })
    return {"vps": vps_list}

@post('/api/vps/<name>/cleanup')
def vps_cleanup(name):
    vps_path = os.path.join(VPS_DIR, f"{name}.conf")
    if not os.path.exists(vps_path):
        return HTTPResponse(status=404, body="VPS not found")
    
    vps_cfg = ConfigManager.load(vps_path)
    # Список активных сервисов для этого VPS
    active = []
    for f in os.listdir(SERVICES_DIR):
        if f.endswith(".conf"):
            cfg = ConfigManager.load(os.path.join(SERVICES_DIR, f))
            if cfg.get('SVC_VPS') == name:
                active.append(f.replace(".conf", ""))
    
    success, msg = VPSManager.cleanup_vps(vps_cfg, active)
    return {"status": "success" if success else "error", "message": msg}

@post('/api/action/<name>/<action>')
def service_action(name, action):
    svc_path = os.path.join(SERVICES_DIR, f"{name}.conf")
    if not os.path.exists(svc_path):
        return HTTPResponse(status=404, body="Service not found")
    
    cfg = ConfigManager.load(svc_path)
    vps_id = cfg.get('SVC_VPS')
    vps_cfg = ConfigManager.load(os.path.join(VPS_DIR, f"{vps_id}.conf"))

    if action == 'start':
        if not vps_cfg: return HTTPResponse(status=400, body="VPS config missing")
        ProcessManager.start_service(cfg, vps_cfg)
    elif action == 'stop':
        ProcessManager.stop_service(name)
    elif action == 'restart':
        ProcessManager.stop_service(name)
        time.sleep(1)
        ProcessManager.start_service(cfg, vps_cfg)
    elif action == 'delete':
        ProcessManager.stop_service(name)
        os.remove(svc_path)
    
    return {"status": "success"}

if __name__ == "__main__":
    run(host='0.0.0.0', port=3000, quiet=True)

if __name__ == "__main__":
    run(host='0.0.0.0', port=3000, quiet=True)
