import os
import subprocess
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
    <div class="stat-item">
        <div class="stat-label"><i data-lucide="cpu" style="width:14px"></i> Version</div>
        <div class="stat-value" style="color: var(--neon-cyan)">{config.get("VERSION", "2.0.3")}</div>
    </div>
    <div class="stat-item">
        <div class="stat-label"><i data-lucide="hard-drive" style="width:14px"></i> VPS Active</div>
        <div class="stat-value">{vps_count}</div>
    </div>
    <div class="stat-item">
        <div class="stat-label"><i data-lucide="activity" style="width:14px"></i> Online</div>
        <div class="stat-value" style="color: var(--neon-emerald)">{online_count}</div>
    </div>
    """

@route('/api/services')
def get_services():
    if not os.path.exists(SERVICES_DIR):
        return '<div class="custom-loader"><p>Сервисы не настроены</p></div>'
    
    html = ""
    try:
        files = sorted([f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")])
    except: return '<div class="custom-loader"><p>Ошибка доступа</p></div>'

    for f in files:
        name = f[:-5]
        cfg = parse_config(os.path.join(SERVICES_DIR, f))
        status = get_service_status(name)
        is_online = status == "online"
        icon = "terminal" if cfg.get('SVC_TYPE') == 'tcp' else "globe"
        
        html += f"""
        <div class="glass svc-card {'online' if is_online else ''}">
            <div class="svc-header">
                <div class="svc-info">
                    <div class="svc-icon"><i data-lucide="{icon}"></i></div>
                    <div class="svc-name">
                        <h3>{name}</h3>
                        <div class="svc-status">
                            <span class="status-dot {'online' if is_online else 'offline'}"></span>
                            <span class="status-text" style="color: {'var(--neon-emerald)' if is_online else 'var(--neon-red)'}">
                                {'On-Air' if is_online else 'Standby'}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="svc-details">
                <div class="detail-row">
                    <div class="detail-label"><i data-lucide="server" style="width:12px"></i> Target</div>
                    <div class="detail-value">{cfg.get('SVC_TARGET_HOST', '127.0.0.1')}:{cfg.get('SVC_TARGET_PORT', '')}</div>
                </div>
                <div class="detail-row">
                    <div class="detail-label"><i data-lucide="external-link" style="width:12px"></i> Public</div>
                    <div class="detail-value" style="color: var(--neon-cyan); font-weight: bold;">{cfg.get('SVC_EXT_PORT', '')}</div>
                </div>
            </div>

            <div class="svc-actions">
                <button hx-post="/api/services/{name}/{'stop' if is_online else 'start'}" hx-swap="none"
                    class="action-btn power {'off' if is_online else 'on'}">
                    <i data-lucide="power" style="width:14px"></i> {'Stop' if is_online else 'Start'}
                </button>
                <button class="action-btn"><i data-lucide="file-text" style="width:16px"></i></button>
                <button class="action-btn delete" hx-post="/api/services/{name}/remove" hx-confirm="Удалить {name}?" hx-swap="none">
                    <i data-lucide="trash-2" style="width:16px"></i>
                </button>
            </div>
        </div>
        """
    return html

@post('/api/services/<service_id>/<action>')
def service_action(service_id, action):
    try:
        subprocess.run(["/opt/bin/rproxy", action, service_id], capture_output=True)
        return {"status": "ok"}
    except: return HTTPResponse(status=500)

if __name__ == "__main__":
    run(host='0.0.0.0', port=3000, quiet=True)
