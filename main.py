import os
import sys
import subprocess
import time
from bottle import route, run, template, request, response, static_file, post, HTTPResponse

# Принудительно добавляем путь к текущей директории для импорта бутылки
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from bottle import route, run, template, request, response, static_file, post, HTTPResponse
except ImportError:
    import bottle
    from bottle import route, run, template, request, response, static_file, post, HTTPResponse

# Константы путей rProxy
RPROXY_ROOT = "/opt/etc/rproxy"
SERVICES_DIR = os.path.join(RPROXY_ROOT, "services")
VPS_DIR = os.path.join(RPROXY_ROOT, "vps")
GLOBAL_CONF = os.path.join(RPROXY_ROOT, "rproxy.conf")
PID_DIR = "/opt/var/run/rproxy"
TEMPLATES_DIR = os.path.join(current_dir, "templates")

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

def write_config(name: str, data: dict):
    os.makedirs(SERVICES_DIR, exist_ok=True)
    file_path = os.path.join(SERVICES_DIR, f"{name}.conf")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# rProxy Service Config: {name}\n")
        for k, v in data.items():
            f.write(f"{k}='{v}'\n")

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
    online_count = sum(1 for f in services if get_service_status(f.replace(".conf", "")) == "online")
    vps_count = len(os.listdir(VPS_DIR)) if os.path.exists(VPS_DIR) else 0
    
    return f"""
    <div class="stat-card">
        <div class="stat-label"><i data-lucide="cpu"></i> Версия</div>
        <div class="stat-value" style="color: var(--accent-main)">{config.get("VERSION", "3.1.0")}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label"><i data-lucide="hard-drive"></i> Активных VPS</div>
        <div class="stat-value">{vps_count}</div>
    </div>
    <div class="stat-card">
        <div class="stat-label"><i data-lucide="activity"></i> Туннелей онлайн</div>
        <div class="stat-value" style="color: var(--accent-success)">{online_count}</div>
    </div>
    """

@route('/api/services')
def get_services():
    if not os.path.exists(SERVICES_DIR):
        return '<div class="loading-state"><p>Конфигурации не найдены</p></div>'
    
    html = ""
    try:
        files = sorted([f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")])
    except: return '<div class="loading-state"><p>Ошибка доступа к FS</p></div>'

    if not files:
        return '<div class="loading-state"><p>Список сервисов пуст</p></div>'

    for f in files:
        name = f.replace(".conf", "")
        cfg = parse_config(os.path.join(SERVICES_DIR, f))
        status = get_service_status(name)
        is_online = status == "online"
        
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
                            <span>{'В СЕТИ' if is_online else 'ОЖИДАНИЕ'}</span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="svc-meta">
                <div class="meta-row">
                    <div class="meta-label"><i data-lucide="server" style="width:12px"></i> Локальный адрес</div>
                    <div class="meta-value">{cfg.get('SVC_TARGET_HOST', '127.0.0.1')}:{cfg.get('SVC_TARGET_PORT', '')}</div>
                </div>
                <div class="meta-row">
                    <div class="meta-label"><i data-lucide="external-link" style="width:12px"></i> Внешний порт</div>
                    <div class="meta-value" style="color: var(--accent-main); font-weight: 900;">{cfg.get('SVC_EXT_PORT', '')}</div>
                </div>
            </div>

            <div class="svc-actions">
                <button hx-post="/api/services/{name}/{'stop' if is_online else 'start'}" hx-swap="none"
                    class="btn-action primary {'off' if is_online else 'on'}">
                    <i data-lucide="power" style="width:16px"></i>
                    <span>{'Стоп' if is_online else 'Старт'}</span>
                </button>
                <button onclick="editService('{name}')" class="btn-action" title="Редактировать">
                    <i data-lucide="edit-3" style="width:18px"></i>
                </button>
                <button onclick="showLogs('{name}')" class="btn-action" title="Логи">
                    <i data-lucide="file-text" style="width:18px"></i>
                </button>
                <button class="btn-action danger" hx-post="/api/services/{name}/remove" hx-confirm="Удалить сервис {name}?" hx-swap="none">
                    <i data-lucide="trash-2" style="width:18px"></i>
                </button>
            </div>
        </div>
        """
    return html

@route('/api/services/new')
def service_form_new():
    return f"""
    <form hx-post="/api/services/save" hx-target="#modal-body" class="svc-form">
        <div class="form-group">
            <label>Имя сервиса (англ.)</label>
            <input type="text" name="name" placeholder="my-app" required>
        </div>
        <div class="form-group">
            <label>Тип сервиса</label>
            <select name="type">
                <option value="http">HTTP Proxy (Веб-сайт)</option>
                <option value="tcp">TCP Tunnel (SSH/Game/Database)</option>
            </select>
        </div>
        <div class="form-group">
            <label>Локальный IP</label>
            <input type="text" name="target_host" value="127.0.0.1" required>
        </div>
        <div class="form-group">
            <label>Локальный порт</label>
            <input type="number" name="target_port" placeholder="8080" required>
        </div>
        <div class="form-group">
            <label>Внешний домен (для HTTP)</label>
            <input type="text" name="domain" placeholder="app.example.com">
        </div>
        <div class="form-group">
            <label>Внешний порт (для TCP/Custom)</label>
            <input type="number" name="ext_port" placeholder="26001">
        </div>
        <div style="display: flex; gap: 12px; margin-top: 20px;">
            <button type="submit" class="btn-glow" style="flex: 1; padding: 12px;">Создать туннель</button>
            <button type="button" onclick="closeModal()" class="btn-action" style="flex: 1;">Отмена</button>
        </div>
    </form>
    """

@route('/api/services/<name>/edit')
def service_form_edit(name):
    cfg = parse_config(os.path.join(SERVICES_DIR, f"{name}.conf"))
    return f"""
    <form hx-post="/api/services/{name}/update" hx-target="#modal-body" class="svc-form">
        <div class="form-group">
            <label>Тип сервиса</label>
            <select name="type">
                <option value="http" {'selected' if cfg.get('SVC_TYPE') == 'http' else ''}>HTTP Proxy</option>
                <option value="tcp" {'selected' if cfg.get('SVC_TYPE') == 'tcp' else ''}>TCP Tunnel</option>
            </select>
        </div>
        <div class="form-group">
            <label>Локальный IP</label>
            <input type="text" name="target_host" value="{cfg.get('SVC_TARGET_HOST', '127.0.0.1')}" required>
        </div>
        <div class="form-group">
            <label>Локальный порт</label>
            <input type="number" name="target_port" value="{cfg.get('SVC_TARGET_PORT', '')}" required>
        </div>
        <div class="form-group">
            <label>Внешний домен</label>
            <input type="text" name="domain" value="{cfg.get('SVC_DOMAIN', '')}">
        </div>
        <div class="form-group">
            <label>Внешний порт</label>
            <input type="number" name="ext_port" value="{cfg.get('SVC_EXT_PORT', '')}">
        </div>
        <div style="display: flex; gap: 12px; margin-top: 20px;">
            <button type="submit" class="btn-glow" style="flex: 1; padding: 12px;">Сохранить изменения</button>
            <button type="button" onclick="closeModal()" class="btn-action" style="flex: 1;">Отмена</button>
        </div>
    </form>
    """

@post('/api/services/save')
def service_save():
    name = request.forms.get('name').strip().lower()
    if not name or not name.isalnum(): return "Ошибка: Неверное имя"
    
    data = {
        "SVC_TYPE": request.forms.get('type'),
        "SVC_TARGET_HOST": request.forms.get('target_host'),
        "SVC_TARGET_PORT": request.forms.get('target_port'),
        "SVC_DOMAIN": request.forms.get('domain', ''),
        "SVC_EXT_PORT": request.forms.get('ext_port', ''),
        "SVC_NAME": name
    }
    write_config(name, data)
    return """<div style="text-align: center; color: var(--accent-success); padding: 40px;">
        <i data-lucide="check-circle" style="width: 64px; height: 64px; margin-bottom: 20px;"></i>
        <h3>Сервис успешно создан!</h3>
        <script>setTimeout(closeModal, 1500);</script>
    </div>"""

@post('/api/services/<name>/update')
def service_update(name):
    data = {
        "SVC_TYPE": request.forms.get('type'),
        "SVC_TARGET_HOST": request.forms.get('target_host'),
        "SVC_TARGET_PORT": request.forms.get('target_port'),
        "SVC_DOMAIN": request.forms.get('domain', ''),
        "SVC_EXT_PORT": request.forms.get('ext_port', ''),
        "SVC_NAME": name
    }
    write_config(name, data)
    return """<div style="text-align: center; color: var(--accent-success); padding: 40px;">
        <i data-lucide="refresh-ccw" style="width: 64px; height: 64px; margin-bottom: 20px;"></i>
        <h3>Настройки обновлены!</h3>
        <script>setTimeout(closeModal, 1500);</script>
    </div>"""

@post('/api/services/<service_id>/<action>')
def service_action(service_id, action):
    try:
        subprocess.run(["/opt/bin/rproxy", action, service_id], capture_output=True)
        return {"status": "success"}
    except: return HTTPResponse(status=500)

@route('/api/logs/<service_id>')
def get_logs(service_id):
    log_file = f"/tmp/rproxy_ttyd_{service_id}.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
                content = lines[-50:]
                return "<br>".join([l.strip() for l in content]) if content else "Лог пуст..."
        except: return "Ошибка чтения лога."
    return "Лог-файл не найден. Запустите сервис с ttyd."

if __name__ == "__main__":
    run(host='0.0.0.0', port=3000, quiet=True)
