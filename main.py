import os
import subprocess
import time
from bottle import route, run, template, request, response, static_file, post, HTTPResponse

# Константы путей rProxy
RPROXY_ROOT = "/opt/etc/rproxy"
SERVICES_DIR = os.path.join(RPROXY_ROOT, "services")
VPS_DIR = os.path.join(RPROXY_ROOT, "vps")
GLOBAL_CONF = os.path.join(RPROXY_ROOT, "rproxy.conf")
PID_DIR = "/opt/var/run/rproxy"
TEMPLATES_DIR = "./templates"

def parse_config(file_path: str) -> dict:
    if not os.path.exists(file_path): return {}
    config = {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    parts = line.split("=", 1)
                    config[parts[0].strip()] = parts[1].strip().strip("'").strip('"')
    except: pass
    return config

def get_service_status(service_name: str) -> str:
    pid_file = os.path.join(PID_DIR, f"{service_name}.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f: pid = f.read().strip()
            if pid and subprocess.run(["kill", "-0", pid], capture_output=True).returncode == 0:
                return "online"
        except: pass
    return "offline"

@route('/')
def index():
    return static_file("index.html", root=TEMPLATES_DIR)

@route('/api/system')
def get_system():
    config = parse_config(GLOBAL_CONF)
    services = [f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")] if os.path.exists(SERVICES_DIR) else []
    online_count = sum(1 for f in services if get_service_status(f[:-5]) == "online")
    vps_count = len(os.listdir(VPS_DIR)) if os.path.exists(VPS_DIR) else 0
    
    return f"""
    <div class="stat-card">
        <div class="stat-label"><i data-lucide="cpu"></i> Version</div>
        <div class="stat-value" style="color: var(--accent-main)">{config.get("VERSION", "3.0.0")}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label"><i data-lucide="hard-drive"></i> Global VPS</div>
        <div class="stat-value">{vps_count}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label"><i data-lucide="activity"></i> Active Tunnels</div>
        <div class="stat-value" style="color: var(--accent-success)">{online_count}</div>
    </div>
    """

@route('/api/services')
def get_services():
    if not os.path.exists(SERVICES_DIR):
        return '<div class="loading-state"><p>Конфигурации rProxy не найдены</p></div>'
    
    html = ""
    try:
        files = sorted([f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")])
    except: return '<div class="loading-state"><p>Ошибка доступа к FS</p></div>'

    if not files:
        return '<div class="loading-state"><p>Список сервисов пуст</p></div>'

    for f in files:
        name = f[:-5]
        cfg = parse_config(os.path.join(SERVICES_DIR, f))
        status = get_service_status(name)
        is_online = status == "online"
        
        # Визуальные настройки в зависимости от типа
        is_tcp = cfg.get('SVC_TYPE') == 'tcp'
        icon = "terminal" if is_tcp else "globe"
        accent = "var(--accent-purple)" if is_tcp else "var(--accent-main)"
        accent_glow = "rgba(192, 132, 252, 0.2)" if is_tcp else "rgba(0, 242, 255, 0.2)"
        
        html += f"""
        <div class="glass service-card {'online' if is_online else ''}" style="--accent-color: {accent}; --accent-glow: {accent_glow}">
            <div class="svc-header">
                <div class="svc-visual">
                    <div class="svc-icon-box"><i data-lucide="{icon}"></i></div>
                    <div class="svc-name-group">
                        <h3>{name}</h3>
                        <div class="status-badge {'online' if is_online else 'offline'}">
                            <span class="dot"></span>
                            <span>{'On-Air' if is_online else 'Standby'}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="svc-meta">
                <div class="meta-row">
                    <div class="meta-label"><i data-lucide="server" style="width:12px"></i> Target</div>
                    <div class="meta-value">{cfg.get('SVC_TARGET_HOST', '127.0.0.1')}:{cfg.get('SVC_TARGET_PORT', '')}</div>
                </div>
                <div class="meta-row">
                    <div class="meta-label"><i data-lucide="external-link" style="width:12px"></i> Public Port</div>
                    <div class="meta-value" style="color: var(--accent-main); font-weight: 900;">{cfg.get('SVC_EXT_PORT', '')}</div>
                </div>
            </div>

            <div class="svc-actions">
                <button hx-post="/api/services/{name}/{'stop' if is_online else 'start'}" hx-swap="none"
                    class="btn-action primary {'off' if is_online else 'on'}">
                    <i data-lucide="power" style="width:16px"></i>
                    <span>{'Stop Session' if is_online else 'Start Tunnel'}</span>
                </button>
                <button onclick="showLogs('{name}')" class="btn-action" title="View Logs">
                    <i data-lucide="file-text" style="width:18px"></i>
                </button>
                <button class="btn-action danger" hx-post="/api/services/{name}/remove" hx-confirm="Вы уверены, что хотите удалить {name}?" hx-swap="none">
                    <i data-lucide="trash-2" style="width:18px"></i>
                </button>
            </div>
        </div>
        """
    return html

@post('/api/services/<service_id>/<action>')
def service_action(service_id, action):
    try:
        # Прямой вызов CLI rproxy
        subprocess.run(["/opt/bin/rproxy", action, service_id], capture_output=True)
        return {"status": "success"}
    except: return HTTPResponse(status=500)

@route('/api/logs/<service_id>')
def get_logs(service_id):
    # Пытаемся прочитать лог ttyd если он есть
    log_file = f"/tmp/rproxy_ttyd_{service_id}.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r") as f:
                content = f.read().splitlines()[-50:] # Последние 50 строк
                return "<br>".join(content) if content else "Лог пуст..."
        except: return "Ошибка чтения лога."
    return "Лог-файл не найден. Запустите сервис с ttyd."

if __name__ == "__main__":
    run(host='0.0.0.0', port=3000, quiet=True)
