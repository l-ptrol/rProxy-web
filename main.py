import os
import subprocess
from typing import List, Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

app = FastAPI()

# Константы путей rProxy
RPROXY_ROOT = "/opt/etc/rproxy"
SERVICES_DIR = os.path.join(RPROXY_ROOT, "services")
VPS_DIR = os.path.join(RPROXY_ROOT, "vps")
GLOBAL_CONF = os.path.join(RPROXY_ROOT, "rproxy.conf")
PID_DIR = "/opt/var/run/rproxy"

# Настройка шаблонов
templates = Jinja2Templates(directory="templates")

# Вспомогательная функция для парсинга bash-подобных конфигов
def parse_config(file_path: str) -> dict:
    if not os.path.exists(file_path):
        return {}
    config = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip().strip("'").strip('"')
    return config

# Получение статуса сервиса
def get_service_status(service_name: str) -> str:
    pid_file = os.path.join(PID_DIR, f"{service_name}.pid")
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                pid = f.read().strip()
            if pid:
                # Проверка процесса на роутере (через kill -0)
                res = subprocess.run(["kill", "-0", pid], capture_output=True)
                return "online" if res.returncode == 0 else "offline"
        except:
            return "offline"
    return "offline"

class Service(BaseModel):
    id: str
    name: str
    vpsId: str
    targetHost: str
    targetPort: str
    extPort: str
    tunnelPort: str
    domain: str
    type: str
    enabled: bool
    ssl: bool
    auth: bool
    status: str

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/system")
async def get_system(request: Request):
    config = parse_config(GLOBAL_CONF)
    services = [f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")] if os.path.exists(SERVICES_DIR) else []
    
    data = {
        "version": config.get("VERSION", "2.0.1"),
        "vpsCount": len(os.listdir(VPS_DIR)) if os.path.exists(VPS_DIR) else 0,
        "servicesCount": len(services),
        "vpsHost": config.get("VPS_HOST", "Не настроено"),
        "onlineCount": sum(1 for f in services if get_service_status(f[:-5]) == "online")
    }
    
    html = f"""
    <div class="space-y-4">
        <div class="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
            <div class="flex items-center gap-2 text-gray-400">
                <i data-lucide="cpu" class="w-4 h-4"></i>
                <span class="text-xs font-bold uppercase">Version</span>
            </div>
            <span class="text-sm font-mono text-[#00f2ff]">{data['version']}</span>
        </div>
        <div class="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
            <div class="flex items-center gap-2 text-gray-400">
                <i data-lucide="hard-drive" class="w-4 h-4"></i>
                <span class="text-xs font-bold uppercase">VPS Active</span>
            </div>
            <span class="text-sm font-bold">{data['vpsCount']}</span>
        </div>
        <div class="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
            <div class="flex items-center gap-2 text-gray-400">
                <i data-lucide="activity" class="w-4 h-4"></i>
                <span class="text-xs font-bold uppercase">Online</span>
            </div>
            <span class="text-sm font-bold text-[#00ff88]">{data['onlineCount']}</span>
        </div>
    </div>
    """
    return HTMLResponse(content=html)

@app.get("/api/services")
async def get_services(request: Request):
    if not os.path.exists(SERVICES_DIR):
        return HTMLResponse(content='<div class="col-span-full py-20 text-center neon-glass text-gray-500">Сервисы не найдены</div>')
    
    services_html = ""
    files = sorted([f for f in os.listdir(SERVICES_DIR) if f.endswith(".conf")])
    
    for f in files:
        name = f[:-5]
        cfg = parse_config(os.path.join(SERVICES_DIR, f))
        status = get_service_status(name)
        is_online = status == "online"
        
        services_html += f"""
        <div class="neon-glass p-5 relative overflow-hidden group {'neon-border-emerald' if is_online else 'neon-border-purple'}">
            <div class="flex justify-between items-start mb-6 relative z-10">
                <div class="flex items-center gap-3">
                    <div class="p-3 rounded-2xl {'bg-emerald-500/10 text-[#00ff88]' if is_online else 'bg-white/5 text-[#bc13fe]'}">
                        <i data-lucide="{'terminal' if cfg.get('SVC_TYPE') == 'tcp' else 'globe'}" class="w-6 h-6"></i>
                    </div>
                    <div>
                        <h3 class="text-xl font-bold tracking-tight">{name}</h3>
                        <div class="flex items-center gap-2 mt-1">
                            <span class="status-dot {'online-dot' if is_online else 'offline-dot'}"></span>
                            <span class="text-[10px] font-black uppercase tracking-[0.2em] {'text-[#00ff88]' if is_online else 'text-red-400'}">
                                {'On-Air' if is_online else 'Standby'}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <div class="space-y-2 mb-6 relative z-10">
                <div class="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
                    <div class="flex items-center gap-2 text-[10px] font-bold uppercase text-gray-500">
                        <i data-lucide="server" class="w-3 h-3"></i>
                        <span>Target</span>
                    </div>
                    <span class="font-mono text-sm text-gray-300">{cfg.get('SVC_TARGET_HOST', '127.0.0.1')}:{cfg.get('SVC_TARGET_PORT', '')}</span>
                </div>
                <div class="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
                    <div class="flex items-center gap-2 text-[10px] font-bold uppercase text-gray-500">
                        <i data-lucide="external-link" class="w-3 h-3"></i>
                        <span>Public</span>
                    </div>
                    <span class="font-mono text-sm text-[#00f2ff] font-bold">{cfg.get('SVC_EXT_PORT', '')}</span>
                </div>
            </div>

            <div class="flex items-center gap-2 pt-4 border-t border-white/5 relative z-10">
                <button hx-post="/api/services/{name}/{'stop' if is_online else 'start'}" hx-swap="none"
                    class="flex-1 btn-action flex items-center justify-center gap-2 {'hover:text-red-400' if is_online else 'hover:text-[#00ff88]'}">
                    <i data-lucide="power" class="w-4 h-4"></i>
                    <span class="text-[10px] font-black uppercase">{'OFF' if is_online else 'ON'}</span>
                </button>
                <button class="btn-action hover:text-[#00f2ff]"><i data-lucide="file-text" class="w-4 h-4"></i></button>
                <button class="btn-action hover:text-white"><i data-lucide="edit-3" class="w-4 h-4"></i></button>
                <button hx-post="/api/services/{name}/remove" hx-confirm="Удалить сервис {name}?" hx-swap="none"
                    class="btn-action hover:text-red-500"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
            </div>
        </div>
        """
    
    return HTMLResponse(content=services_html)

@app.post("/api/services/{service_id}/{action}")
async def service_action(service_id: str, action: str):
    # Команды: start, stop, restart, remove
    cmd = ["/opt/bin/rproxy", action, service_id]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            return {"message": f"Действие {action} выполнено для {service_id}", "output": res.stdout}
        else:
            return JSONResponse(status_code=500, content={"error": res.stderr})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
