const express = require('express');
const cors = require('cors');
const { exec, spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const app = express();
const port = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// Пути к конфигурациям rProxy
const RPROXY_DIR = '/opt/etc/rproxy';
const SERVICES_DIR = path.join(RPROXY_DIR, 'services');
const VPS_DIR = path.join(RPROXY_DIR, 'vps');
const MAIN_CONF = path.join(RPROXY_DIR, 'rproxy.conf');

// Убедимся, что директории существуют (для отладки на Windows подменяем пути если нужно)
if (!fs.existsSync(SERVICES_DIR)) fs.mkdirSync(SERVICES_DIR, { recursive: true });
if (!fs.existsSync(VPS_DIR)) fs.mkdirSync(VPS_DIR, { recursive: true });

// --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

// Парсер bash-подобных конфигов
function parseConf(filePath) {
  if (!fs.existsSync(filePath)) return null;
  const content = fs.readFileSync(filePath, 'utf8');
  const config = {};
  const lines = content.split('\n');
  
  lines.forEach(line => {
    // Игнорируем комментарии и пустые строки
    if (line.trim().startsWith('#') || !line.includes('=')) return;
    
    // Извлекаем ключ и значение (поддержка одинарных и двойных кавычек)
    const match = line.match(/^([^=]+)=(['"]?)(.*)\2$/);
    if (match) {
      const key = match[1].trim();
      let value = match[3].trim();
      config[key] = value;
    }
  });
  return config;
}

// Запись bash-подобного конфига
function writeConf(filePath, data, prefix = 'SVC_') {
  let content = '';
  for (const [key, value] of Object.entries(data)) {
    const fullKey = key.startsWith(prefix) ? key : `${prefix}${key}`;
    content += `${fullKey}="${value}"\n`;
  }
  fs.writeFileSync(filePath, content, 'utf8');
}

// --- API ЭНДПОИНТЫ ---

// 1. СЕРВИСЫ
app.get('/api/services', (req, res) => {
  try {
    const files = fs.readdirSync(SERVICES_DIR).filter(f => f.endsWith('.conf'));
    const services = files.map(file => {
      const name = path.basename(file, '.conf');
      const config = parseConf(path.join(SERVICES_DIR, file));
      
      // Проверка статуса (наличие PID файла)
      const pidFile = `/opt/var/run/rproxy/${name}.pid`;
      const isOnline = fs.existsSync(pidFile);
      
      return { 
        id: name, 
        name, 
        ...config,
        status: isOnline ? 'online' : 'offline'
      };
    });
    res.json(services);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 2. VPS СЕРВЕРЫ
app.get('/api/vps', (req, res) => {
  try {
    const files = fs.readdirSync(VPS_DIR).filter(f => f.endsWith('.conf'));
    const vpsList = files.map(file => {
      const id = path.basename(file, '.conf');
      const config = parseConf(path.join(VPS_DIR, file));
      return { id, ...config };
    });
    res.json(vpsList);
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post('/api/vps', (req, res) => {
  const { id, host, port, user } = req.body;
  if (!id || !host) return res.status(400).json({ error: 'ID и Host обязательны' });
  
  const vpsData = {
    HOST: host,
    PORT: port || '22',
    USER: user || 'root',
    AUTH: 'key'
  };
  
  try {
    writeConf(path.join(VPS_DIR, `${id}.conf`), vpsData, 'VPS_');
    res.json({ success: true, id });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

// 3. ВЫПОЛНЕНИЕ КОМАНД (SSE для стриминга логов)
app.get('/api/execute/:command/:target?', (req, res) => {
  const { command, target } = req.params;
  
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('Connection', 'keep-alive');
  
  const send = (data) => res.write(`data: ${JSON.stringify(data)}\n\n`);
  
  let cmdArgs = [command];
  if (target) cmdArgs.push(target);
  
  // Добавляем флаг версии для проверки
  if (command === 'version') {
     cmdArgs = ['--version'];
  }

  const process = spawn('/opt/bin/rproxy', cmdArgs);

  process.stdout.on('data', (data) => {
    send({ type: 'log', message: data.toString() });
  });

  process.stderr.on('data', (data) => {
    send({ type: 'error', message: data.toString() });
  });

  process.on('close', (code) => {
    send({ type: 'done', code });
    res.end();
  });
});

// Раздача статики фронтенда
app.use(express.static(path.join(__dirname, '../frontend_dist')));

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend_dist/index.html'));
});

app.listen(port, () => {
  console.log(`rProxy Web API running on port ${port}`);
});
