const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;

// Константы путей rProxy
const RPROXY_ROOT = '/opt/etc/rproxy';
const SERVICES_DIR = path.join(RPROXY_ROOT, 'services');
const VPS_DIR = path.join(RPROXY_ROOT, 'vps');
const GLOBAL_CONF = path.join(RPROXY_ROOT, 'rproxy.conf');
const PID_DIR = '/opt/var/run/rproxy';

// Базовые порты (как в скрипте)
const BASE_TUNNEL_PORT = 10000;
const BASE_EXT_PORT = 26000;

app.use(cors());
app.use(express.json());

// Отдача статики фронтенда
if (fs.existsSync(path.join(__dirname, '../frontend/dist'))) {
    app.use(express.static(path.join(__dirname, '../frontend/dist')));
}

// Вспомогательная функция для парсинга bash-подобных конфигов
const parseConfig = (filePath) => {
    if (!fs.existsSync(filePath)) return {};
    const content = fs.readFileSync(filePath, 'utf8');
    const config = {};
    const lines = content.split('\n');
    
    lines.forEach(line => {
        const trimmed = line.trim();
        if (trimmed && !trimmed.startsWith('#')) {
            const match = trimmed.match(/^([A-Z0-9_]+)=['"]?(.*?)['"]?$/);
            if (match) {
                config[match[1]] = match[2];
            }
        }
    });
    return config;
};

// Генерация следующего свободного порта
const getNextFreePort = (basePort, configKey) => {
    if (!fs.existsSync(SERVICES_DIR)) return basePort;
    const files = fs.readdirSync(SERVICES_DIR).filter(f => f.endsWith('.conf'));
    const usedPorts = files.map(f => {
        const cfg = parseConfig(path.join(SERVICES_DIR, f));
        return parseInt(cfg[configKey]);
    }).filter(p => !isNaN(p));
    
    let port = basePort;
    while (usedPorts.includes(port)) {
        port++;
    }
    return port;
};

// Проверка статуса сервиса через PID-файл
const getServiceStatus = (serviceName) => {
    const pidFile = path.join(PID_DIR, `${serviceName}.pid`);
    if (fs.existsSync(pidFile)) {
        try {
            const pid = fs.readFileSync(pidFile, 'utf8').trim();
            if (pid) {
                try {
                    process.kill(parseInt(pid), 0);
                    return 'online';
                } catch (e) {
                    return 'offline';
                }
            }
        } catch (e) {
            return 'offline';
        }
    }
    return 'offline';
};

// API: Получение общей информации системы
app.get('/api/system', (req, res) => {
    const globalConfig = parseConfig(GLOBAL_CONF);
    const services = fs.existsSync(SERVICES_DIR) ? fs.readdirSync(SERVICES_DIR).filter(f => f.endsWith('.conf')) : [];
    
    res.json({
        version: globalConfig.VERSION || '2.0.0',
        vpsCount: fs.existsSync(VPS_DIR) ? fs.readdirSync(VPS_DIR).length : 0,
        servicesCount: services.length,
        vpsHost: globalConfig.VPS_HOST || 'Not configured'
    });
});

// API: Список VPS профилей
app.get('/api/vps', (req, res) => {
    if (!fs.existsSync(VPS_DIR)) return res.json([]);
    const files = fs.readdirSync(VPS_DIR).filter(f => f.endsWith('.conf'));
    const vpsList = files.map(f => {
        const name = path.basename(f, '.conf');
        const cfg = parseConfig(path.join(VPS_DIR, f));
        return { id: name, host: cfg.VPS_HOST };
    });
    res.json(vpsList);
});

// API: Предложение свободных портов
app.get('/api/next-ports', (req, res) => {
    res.json({
        tunnel: getNextFreePort(BASE_TUNNEL_PORT, 'SVC_TUNNEL_PORT'),
        external: getNextFreePort(BASE_EXT_PORT, 'SVC_EXT_PORT')
    });
});

// API: Список всех сервисов
app.get('/api/services', (req, res) => {
    if (!fs.existsSync(SERVICES_DIR)) return res.json([]);
    
    const files = fs.readdirSync(SERVICES_DIR).filter(f => f.endsWith('.conf'));
    const services = files.map(file => {
        const name = path.basename(file, '.conf');
        const config = parseConfig(path.join(SERVICES_DIR, file));
        
        return {
            id: name,
            name: name,
            vpsId: config.SVC_VPS,
            targetHost: config.SVC_TARGET_HOST,
            targetPort: config.SVC_TARGET_PORT,
            extPort: config.SVC_EXT_PORT,
            tunnelPort: config.SVC_TUNNEL_PORT,
            domain: config.SVC_DOMAIN || '',
            type: config.SVC_TYPE || 'http',
            enabled: config.SVC_ENABLED === 'yes',
            ssl: config.SVC_SSL === 'yes',
            auth: config.SVC_NDM_AUTH === 'yes',
            status: getServiceStatus(name)
        };
    });
    
    res.json(services);
});

// API: Создание/Обновление сервиса
app.post('/api/services', (req, res) => {
    const s = req.body;
    if (!s.name || !s.vpsId || !s.targetPort || !s.extPort) {
        return res.status(400).json({ error: 'Missing required fields' });
    }

    const name = s.name.replace(/[^a-z0-9_-]/gi, '_');
    const confPath = path.join(SERVICES_DIR, `${name}.conf`);
    
    const content = `SVC_NAME="${name}"
SVC_VPS="${s.vpsId}"
SVC_TARGET_HOST="${s.targetHost || '127.0.0.1'}"
SVC_TARGET_PORT="${s.targetPort}"
SVC_TUNNEL_PORT="${s.tunnelPort}"
SVC_EXT_PORT="${s.extPort}"
SVC_DOMAIN="${s.domain || ''}"
SVC_SSL="${s.ssl ? 'yes' : 'no'}"
SVC_NDM_AUTH="${s.auth ? 'yes' : 'no'}"
SVC_HTPASSWD='${s.htpasswd || ''}'
SVC_TYPE="${s.type || 'http'}"
SVC_ENABLED="yes"
`;

    try {
        if (!fs.existsSync(SERVICES_DIR)) fs.mkdirSync(SERVICES_DIR, { recursive: true });
        fs.writeFileSync(confPath, content);
        
        // После сохранения файла вызываем rproxy для применения конфига (деплой на VPS и т.д.)
        // В v2 мы можем использовать rproxy setup-service или просто start
        // Но для полноценной настройки (SSL, Nginx на VPS) лучше использовать спец. команду если она есть.
        // Пока просто сообщаем об успехе.
        res.json({ message: `Service ${name} saved successfully` });
    } catch (e) {
        res.status(500).json({ error: 'Failed to write config file' });
    }
});

// API: Получение логов сервиса
app.get('/api/services/:id/logs', (req, res) => {
    const { id } = req.params;
    const logPath = `/tmp/rproxy_ttyd_${id}.log`;
    
    if (fs.existsSync(logPath)) {
        const logs = fs.readFileSync(logPath, 'utf8');
        res.json({ logs: logs.split('\n').slice(-100).join('\n') }); // Последние 100 строк
    } else {
        res.json({ logs: 'Logs not found. Service might be starting or not using ttyd.' });
    }
});

// API: Удаление, запуск и т.д. работаем через CLI
app.post('/api/services/:id/:action', (req, res) => {
    const { id, action } = req.params;
    const cmd = `/opt/bin/rproxy ${action} ${id}`;
    
    exec(cmd, (error, stdout, stderr) => {
        if (error) return res.status(500).json({ error: error.message, details: stderr });
        res.json({ message: `Service ${id} ${action}ed`, output: stdout });
    });
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`rProxy Web API running on port ${PORT}`);
});
