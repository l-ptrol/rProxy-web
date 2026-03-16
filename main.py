import os
import sys
import subprocess
import json
import time
from bottle import route, run, template, request, response, static_file, post, get, HTTPResponse

# Пути rProxy (Entware)
RPROXY_ROOT = "/opt/etc/rproxy"
SERVICES_DIR = os.path.join(RPROXY_ROOT, "services")
VPS_DIR = os.path.join(RPROXY_ROOT, "vps")
GLOBAL_CONF = os.path.join(RPROXY_ROOT, "rproxy.conf")
PID_DIR = "/opt/var/run/rproxy"

# Версия интерфейса
VERSION = "5.0.0"

def parse_bash_config(file_path):
    if not os.path.exists(file_path): return {}
    config = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    parts = line.split("=", 1)
                    key = parts[0].strip()
                    val = parts[1].strip().strip("'").strip('"')
                    config[key] = val
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
    return config

def get_service_status(name):
    pid_file = os.path.join(PID_DIR, f"{name}.pid")
    if os.path.exists(pid_file):
        return "online"
    return "offline"

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
            if get_service_status(f.replace(".conf", "")) == "online":
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
                cfg = parse_bash_config(os.path.join(SERVICES_DIR, f))
                status = get_service_status(name)
                services.append({
                    "id": name,
                    "name": name,
                    "type": cfg.get("SVC_TYPE", "http"),
                    "target": f"{cfg.get('SVC_TARGET_HOST', '127.0.0.1')}:{cfg.get('SVC_TARGET_PORT', '')}",
                    "ext_port": cfg.get("SVC_EXT_PORT", ""),
                    "domain": cfg.get("SVC_DOMAIN", ""),
                    "ssl": cfg.get("SVC_SSL", "no"),
                    "status": status
                })
    return {"services": services}

@post('/api/action/<name>/<action>')
def service_action(name, action):
    # Допустимые действия: start, stop, restart
    if action not in ["start", "stop", "restart"]:
        return HTTPResponse(status=400, body="Invalid action")
    
    try:
        # Запускаем rproxy CLI
        cmd = ["/opt/bin/rproxy", action, name]
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"status": "success", "message": f"Command {action} sent for {name}"}
    except Exception as e:
        return HTTPResponse(status=500, body=str(e))

@get('/api/vps')
def list_vps():
    vps_list = []
    if os.path.exists(VPS_DIR):
        for f in os.listdir(VPS_DIR):
            if f.endswith(".conf"):
                name = f.replace(".conf", "")
                cfg = parse_bash_config(os.path.join(VPS_DIR, f))
                vps_list.append({
                    "id": name,
                    "host": cfg.get("VPS_HOST", ""),
                    "user": cfg.get("VPS_USER", "root")
                })
    return {"vps": vps_list}

if __name__ == "__main__":
    # На роутере мы работаем через Entware
    run(host='0.0.0.0', port=3000, quiet=True)
