import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Activity, Plus, Settings, Cpu, Shield } from 'lucide-react';
import ServiceCard from './ServiceCard';

interface Service {
  id: string;
  name?: string;
  target_host?: string;
  target_port?: string;
  ext_port?: string;
  domain?: string;
  enabled?: string;
  running?: boolean;
}

const Dashboard: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);

  // В реальном приложении здесь будет fetch к API бэкенда
  useEffect(() => {
    // Симуляция загрузки для демонстрации интерфейса
    setTimeout(() => {
      setServices([
        { id: 'nas', name: 'Home NAS', target_host: '192.168.1.10', target_port: '5000', ext_port: '443', domain: 'nas.example.com', enabled: 'yes', running: true },
        { id: 'ssh', name: 'SSH Tunnel', target_host: '127.0.0.1', target_port: '22', ext_port: '2222', enabled: 'yes', running: false },
        { id: 'plex', name: 'Media Server', target_host: '192.168.1.15', target_port: '32400', ext_port: '32400', domain: 'plex.home.ru', enabled: 'no', running: true },
      ]);
      setLoading(false);
    }, 1000);
  }, []);

  return (
    <div className="min-h-screen p-4 md:p-8 relative">
      <div className="bg-mesh" />
      
      {/* Шапка */}
      <header className="max-w-6xl mx-auto mb-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex items-center gap-4"
        >
          <div className="p-3 glass-card bg-cyan-500/10 border-cyan-500/20">
            <Shield className="w-8 h-8 text-accent-cyan" />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-white/60">
              rProxy Dashboard
            </h1>
            <p className="text-white/40 text-sm font-medium flex items-center gap-2">
              <Activity className="w-3 h-3 text-emerald-400 animate-pulse" />
              Все системы работают штатно
            </p>
          </div>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex items-center gap-3 overflow-x-auto pb-2 md:pb-0"
        >
          <button className="btn-secondary flex items-center gap-2 whitespace-nowrap">
            <Cpu className="w-4 h-4" /> Настройки VPS
          </button>
          <button className="btn-primary flex items-center gap-2 whitespace-nowrap">
            <Plus className="w-4 h-4" /> Добавить сервис
          </button>
        </motion.div>
      </header>

      {/* Сетка сервисов */}
      <main className="max-w-6xl mx-auto">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
          <AnimatePresence>
            {loading ? (
              [1, 2, 3].map(i => (
                <div key={i} className="glass-card h-48 animate-pulse-slow" />
              ))
            ) : (
              services.map((svc, idx) => (
                <ServiceCard key={svc.id} service={svc} index={idx} />
              ))
            )}
          </AnimatePresence>
        </div>
      </main>

      {/* Мобильный статус бар (опционально) */}
      <footer className="md:hidden fixed bottom-6 left-4 right-4 z-50">
        <div className="glass-card p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
            <span className="text-xs font-bold uppercase tracking-wider text-white/60">Keenetic Online</span>
          </div>
          <Settings className="w-5 h-5 text-white/40" />
        </div>
      </footer>
    </div>
  );
};

export default Dashboard;
