const express = require('express');
const cors = require('cors');
const { exec } = require('child_process');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;

// Конфигурационные пути rproxy
const RPROXY_CONF_DIR = '/opt/etc/rproxy';
const SERVICES_DIR = path.join(RPROXY_CONF_DIR, 'services');

app.use(cors());
app.use(express.json());

// Вспомогательная функция для выполнения shell-команд
const runCommand = (cmd) => {
  return new Promise((resolve, reject) => {
    exec(cmd, (error, stdout, stderr) => {
      if (error) {
        reject({ error, stderr });
        return;
      }
      resolve(stdout);
    });
  });
};

// Эндпоинт: Получение списка сервисов
app.get('/api/services', async (req, res) => {
  try {
    if (!fs.existsSync(SERVICES_DIR)) {
      return res.json([]);
    }

    const files = fs.readdirSync(SERVICES_DIR).filter(f => f.endsWith('.conf'));
    const services = files.map(file => {
      const content = fs.readFileSync(path.join(SERVICES_DIR, file), 'utf-8');
      const service = {};
      content.split('\n').forEach(line => {
        const match = line.match(/^SVC_(\w+)="(.+)"/);
        if (match) {
          service[match[1].toLowerCase()] = match[2];
        }
      });
      return { id: path.basename(file, '.conf'), ...service };
    });

    res.json(services);
  } catch (err) {
    res.status(500).json({ error: 'Ошибка при чтении сервисов', details: err.message });
  }
});

// Эндпоинт: Управление сервисом (start/stop/restart)
app.post('/api/services/:id/:action', async (req, res) => {
  const { id, action } = req.params;
  const validActions = ['start', 'stop', 'restart'];

  if (!validActions.includes(action)) {
    return res.status(400).json({ error: 'Неверное действие' });
  }

  try {
    // В реальности команда запускается через основной скрипт rproxy
    const cmd = `/opt/bin/rproxy ${action} ${id}`;
    const output = await runCommand(cmd);
    res.json({ message: `Команда ${action} для ${id} выполнена`, output });
  } catch (err) {
    res.status(500).json({ error: `Ошибка при выполнении ${action}`, details: err.stderr || err.message });
  }
});

// Статические файлы фронтенда
const frontendDist = path.join(__dirname, '../frontend/dist');
if (fs.existsSync(frontendDist)) {
  app.use(express.static(frontendDist));
  app.get('*', (req, res) => {
    res.sendFile(path.join(frontendDist, 'index.html'));
  });
} else {
  app.get('/', (req, res) => {
    res.send('<h1>rProxy API Bridge</h1><p>Сборка фронтенда не найдена. Запустите сборку во frontend/.</p>');
  });
}

app.listen(PORT, '0.0.0.0', () => {
  console.log(`Server running at http://0.0.0.0:${PORT}`);
});
