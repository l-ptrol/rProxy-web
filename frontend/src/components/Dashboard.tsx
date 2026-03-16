import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Plus, Cpu, Shield, Server, Globe, X, Trash2, Terminal } from 'lucide-react';
import ServiceCard from './ServiceCard';

interface Service {
  id: string;
  name: string;
  SVC_TYPE: string;
  SVC_TARGET_HOST: string;
  SVC_TARGET_PORT: string;
  SVC_TUNNEL_PORT: string;
  SVC_DOMAIN?: string;
  SVC_EXT_PORT: string;
  SVC_SSL: string;
  status: 'online' | 'offline';
}

interface VPS {
  id: string;
  HOST: string;
  PORT: string;
  USER: string;
}

const Dashboard: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [vpsList, setVpsList] = useState<VPS[]>([]);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showVpsModal, setShowVpsModal] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  
  // Состояние новой формы
  const [newSvc, setNewSvc] = useState({
    name: '',
    type: 'http',
    targetHost: '127.0.0.1',
    targetPort: '',
    vps: '',
    domain: '',
    extPort: '443',
    ssl: 'no'
  });

  const [newVps, setNewVps] = useState({
    id: '',
    host: '',
    port: '22',
    user: 'root'
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      const [svcRes, vpsRes] = await Promise.all([
        fetch('http://localhost:3000/api/services'),
        fetch('http://localhost:3000/api/vps')
      ]);
      setServices(await svcRes.json());
      setVpsList(await vpsRes.json());
    } catch (err) {
      console.error('Ошибка загрузки данных:', err);
    }
  };

  const executeCommand = (command: string, target?: string) => {
    setShowLogs(true);
    setLogs(prev => [...prev, `> rproxy ${command} ${target || ''}`]);
    
    const url = `http://localhost:3000/api/execute/${command}${target ? `/${target}` : ''}`;
    const eventSource = new EventSource(url);

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'done') {
        eventSource.close();
        fetchData();
        return;
      }
      setLogs(prev => [...prev, data.message || data.error]);
    };

    eventSource.onerror = () => {
      eventSource.close();
      setLogs(prev => [...prev, "Ошибка соединения с сервером"]);
    };
  };

  const handleCreateVps = async () => {
    await fetch('http://localhost:3000/api/vps', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newVps)
    });
    setShowVpsModal(false);
    fetchData();
  };

  return (
    <div className="space-y-8 pb-20">
      {/* Header & Stats */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-4xl font-black bg-gradient-to-r from-cyan-400 to-purple-500 bg-clip-text text-transparent">
            rProxy Dashboard
          </h1>
          <p className="text-white/40 mt-1 font-medium italic">Управление туннелями Keenetic × Entware</p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={() => setShowVpsModal(true)}
            className="btn-secondary flex items-center gap-2 group"
          >
            <Server size={18} className="group-hover:text-cyan-400 transition-colors" />
            <span>Серверы ({vpsList.length})</span>
          </button>
          <button 
            onClick={() => setShowAddModal(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus size={20} />
            <span>Новый сервис</span>
          </button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="glass-card p-4 flex items-center gap-4 border-l-4 border-cyan-500">
          <div className="w-12 h-12 rounded-xl bg-cyan-500/20 flex items-center justify-center text-cyan-400">
            <Activity size={24} />
          </div>
          <div>
            <div className="text-2xl font-bold">{services.filter(s => s.status === 'online').length}</div>
            <div className="text-white/40 text-xs font-bold uppercase tracking-wider">Активно</div>
          </div>
        </div>
        <div className="glass-card p-4 flex items-center gap-4 border-l-4 border-purple-500">
          <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center text-purple-400">
            <Globe size={24} />
          </div>
          <div>
            <div className="text-2xl font-bold">{services.filter(s => s.SVC_DOMAIN).length}</div>
            <div className="text-white/40 text-xs font-bold uppercase tracking-wider">Доменов</div>
          </div>
        </div>
        <div className="glass-card p-4 flex items-center gap-4 border-l-4 border-emerald-500">
          <div className="w-12 h-12 rounded-xl bg-emerald-500/20 flex items-center justify-center text-emerald-400">
            <Shield size={24} />
          </div>
          <div>
            <div className="text-2xl font-bold">{services.filter(s => s.SVC_SSL === 'yes').length}</div>
            <div className="text-white/40 text-xs font-bold uppercase tracking-wider">SSL OK</div>
          </div>
        </div>
        <div className="glass-card p-4 flex items-center gap-4 border-l-4 border-amber-500">
          <div className="w-12 h-12 rounded-xl bg-amber-500/20 flex items-center justify-center text-amber-400">
            <Cpu size={24} />
          </div>
          <div>
            <div className="text-2xl font-bold">{vpsList.length}</div>
            <div className="text-white/40 text-xs font-bold uppercase tracking-wider">VPS Ноды</div>
          </div>
        </div>
      </div>

      {/* Services Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <AnimatePresence>
          {services.map((service, index) => (
            <motion.div
              key={service.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ delay: index * 0.05 }}
            >
              <ServiceCard 
                service={service} 
                onStart={() => executeCommand('start', service.name)}
                onStop={() => executeCommand('stop', service.name)}
              />
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Log Terminal Overlay */}
      {showLogs && (
        <motion.div 
          initial={{ y: 300 }}
          animate={{ y: 0 }}
          className="fixed bottom-0 left-0 right-0 z-50 p-4"
        >
          <div className="max-w-4xl mx-auto glass-card h-64 flex flex-col overflow-hidden border-cyan-500/30">
            <div className="p-3 bg-black/40 flex justify-between items-center border-b border-white/10">
              <div className="flex items-center gap-2 text-cyan-400 font-mono text-sm">
                <Terminal size={14} />
                <span>Системный лог выполнения</span>
              </div>
              <button 
                onClick={() => setShowLogs(false)}
                className="hover:bg-white/10 p-1 rounded transition-colors"
              >
                <X size={18} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 font-mono text-xs text-white/70 space-y-1">
              {logs.map((log, i) => (
                <div key={i}>{log}</div>
              ))}
            </div>
          </div>
        </motion.div>
      )}

      {/* Modals placeholders - simplified for UI demo */}
      <AnimatePresence>
        {showAddModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <motion.div 
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="glass-card w-full max-w-lg overflow-hidden flex flex-col"
            >
              <div className="p-6 border-b border-white/10 flex justify-between items-center">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Plus className="text-cyan-400" />
                  Новый сервис
                </h2>
                <button onClick={() => setShowAddModal(false)}><X /></button>
              </div>
              <div className="p-6 space-y-4">
                <div className="space-y-1">
                  <label className="text-xs font-bold text-white/40 uppercase">Название</label>
                  <input 
                    type="text" 
                    className="glass-input w-full" 
                    placeholder="my-cool-app"
                    value={newSvc.name}
                    onChange={e => setNewSvc({...newSvc, name: e.target.value})}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-white/40 uppercase">Тип</label>
                    <select 
                      className="glass-input w-full appearance-none"
                      value={newSvc.type}
                      onChange={e => setNewSvc({...newSvc, type: e.target.value})}
                    >
                      <option value="http">HTTP Proxy</option>
                      <option value="tcp">TCP Tunnel</option>
                      <option value="ttyd">Web Terminal</option>
                    </select>
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs font-bold text-white/40 uppercase">VPS</label>
                    <select 
                      className="glass-input w-full appearance-none"
                      value={newSvc.vps}
                      onChange={e => setNewSvc({...newSvc, vps: e.target.value})}
                    >
                      <option value="">Выберите VPS</option>
                      {vpsList.map(v => <option key={v.id} value={v.id}>{v.id}</option>)}
                    </select>
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-bold text-white/40 uppercase">IP Цели : Порт</label>
                  <div className="flex gap-2">
                    <input 
                      className="glass-input flex-1" 
                      value={newSvc.targetHost}
                      onChange={e => setNewSvc({...newSvc, targetHost: e.target.value})}
                    />
                    <input 
                      placeholder="8080" 
                      className="glass-input w-24"
                      value={newSvc.targetPort}
                      onChange={e => setNewSvc({...newSvc, targetPort: e.target.value})}
                    />
                  </div>
                </div>
              </div>
              <div className="p-6 bg-white/5 flex gap-3">
                <button className="btn-secondary flex-1" onClick={() => setShowAddModal(false)}>Отмена</button>
                <button className="btn-primary flex-1" onClick={() => {
                  executeCommand('add-service', newSvc.name);
                  setShowAddModal(false);
                }}>Создать</button>
              </div>
            </motion.div>
          </div>
        )}

        {showVpsModal && (
          <div className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
            <motion.div 
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              className="glass-card w-full max-w-lg overflow-hidden flex flex-col"
            >
              <div className="p-6 border-b border-white/10 flex justify-between items-center">
                <h2 className="text-xl font-bold flex items-center gap-2">
                  <Server className="text-purple-400" />
                  Управление VPS
                </h2>
                <button onClick={() => setShowVpsModal(false)}><X /></button>
              </div>
              <div className="p-6 space-y-4 max-h-[60vh] overflow-y-auto">
                {vpsList.map(v => (
                  <div key={v.id} className="p-3 bg-white/5 rounded-xl border border-white/10 flex justify-between items-center">
                    <div>
                      <div className="font-bold">{v.id}</div>
                      <div className="text-xs text-white/40">{v.USER}@{v.HOST}:{v.PORT}</div>
                    </div>
                    <button className="text-red-400/60 hover:text-red-400 p-2 transition-colors">
                      <Trash2 size={16} />
                    </button>
                  </div>
                ))}
                
                <div className="pt-4 border-t border-white/10 space-y-3">
                   <div className="text-sm font-bold text-white/60">Добавить новый сервер</div>
                   <input 
                    placeholder="Название (ID)" 
                    className="glass-input w-full"
                    value={newVps.id}
                    onChange={e => setNewVps({...newVps, id: e.target.value})}
                   />
                   <div className="flex gap-2">
                    <input 
                      placeholder="IP Адрес" 
                      className="glass-input flex-1"
                      value={newVps.host}
                      onChange={e => setNewVps({...newVps, host: e.target.value})}
                    />
                    <input 
                      placeholder="Порт" 
                      className="glass-input w-24"
                      value={newVps.port}
                      onChange={e => setNewVps({...newVps, port: e.target.value})}
                    />
                   </div>
                </div>
              </div>
              <div className="p-6 bg-white/5 flex gap-3">
                <button className="btn-secondary flex-1" onClick={() => setShowVpsModal(false)}>Закрыть</button>
                <button className="btn-primary flex-1" onClick={handleCreateVps}>Сохранить VPS</button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Dashboard;
