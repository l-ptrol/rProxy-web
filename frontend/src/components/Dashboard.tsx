import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  Activity, 
  Cpu, 
  Shield, 
  Zap, 
  PlusCircle, 
  RefreshCw, 
  HardDrive,
  Info,
  ChevronRight,
  Bell,
  Search
} from 'lucide-react';
import ServiceCard from './ServiceCard';
import ServiceEditor from './ServiceEditor';
import LogViewer from './LogViewer';

interface Service {
  id?: string;
  name: string;
  vpsId: string;
  targetHost: string;
  targetPort: string;
  extPort: string;
  tunnelPort: string;
  domain: string;
  type: string;
  enabled: boolean;
  ssl: boolean;
  auth: boolean;
  status: 'online' | 'offline';
}

interface SystemInfo {
  version: string;
  vpsCount: number;
  servicesCount: number;
  vpsHost: string;
}

const Dashboard: React.FC = () => {
  const [services, setServices] = useState<Service[]>([]);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [notification, setNotification] = useState<{message: string, type: 'success' | 'error'} | null>(null);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingService, setEditingService] = useState<Service | null>(null);
  const [viewingLogs, setViewingLogs] = useState<string | null>(null);

  const API_URL = 'http://' + window.location.hostname + ':3000/api';

  const fetchData = async () => {
    try {
      const [servicesRes, systemRes] = await Promise.all([
        fetch(`${API_URL}/services`),
        fetch(`${API_URL}/system`)
      ]);
      const servicesData = await servicesRes.json();
      const systemData = await systemRes.json();
      setServices(servicesData || []);
      setSystemInfo(systemData);
    } catch (error) {
      console.error('Fetch error:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const showNotification = (message: string, type: 'success' | 'error') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 3000);
  };

  const handleAction = async (id: string, action: string) => {
    if (action === 'edit') {
      const s = services.find(srv => srv.id === id);
      if (s) {
        setEditingService(s);
        setIsEditorOpen(true);
      }
      return;
    }

    if (action === 'logs') {
      setViewingLogs(id);
      return;
    }

    try {
      const res = await fetch(`${API_URL}/services/${id}/${action}`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        showNotification(data.message || `Action ${action} successful`, 'success');
        fetchData();
      } else {
        showNotification(data.error || 'Action failed', 'error');
      }
    } catch (error) {
      showNotification('Network error', 'error');
    }
  };

  const handleSaveService = async (service: any) => {
    try {
      const res = await fetch(`${API_URL}/services`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(service)
      });
      const data = await res.json();
      if (res.ok) {
        showNotification(data.message, 'success');
        setIsEditorOpen(false);
        setEditingService(null);
        fetchData();
      } else {
        showNotification(data.error, 'error');
      }
    } catch (error) {
      showNotification('Failed to save service', 'error');
    }
  };

  const filteredServices = services.filter(s => 
    s.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    s.domain?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen flex flex-col md:flex-row p-4 md:p-8 gap-8 max-w-[1600px] mx-auto overflow-hidden">
      {/* Sidebar - System Stats */}
      <aside className="w-full md:w-80 space-y-6">
        <motion.div 
          initial={{ x: -20, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          className="neon-glass p-6 neon-border-cyan relative overflow-hidden"
        >
          <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/10 rounded-bl-full blur-2xl" />
          <div className="flex items-center gap-3 mb-8">
            <div className="w-12 h-12 bg-cyan-500/20 rounded-2xl flex items-center justify-center text-cyan-400 shadow-lg shadow-cyan-500/20">
              <Zap size={28} />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tighter">rProxy <span className="text-cyan-400">WEB</span></h1>
              <p className="text-[10px] uppercase tracking-[0.2em] font-bold text-gray-500">Premium Management</p>
            </div>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
              <div className="flex items-center gap-2 text-gray-400"><Cpu size={16} /> <span className="text-xs font-bold uppercase">Version</span></div>
              <span className="text-sm font-mono text-cyan-400">{systemInfo?.version || '2.0.0'}</span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
              <div className="flex items-center gap-2 text-gray-400"><HardDrive size={16} /> <span className="text-xs font-bold uppercase">VPS Active</span></div>
              <span className="text-sm font-bold">{systemInfo?.vpsCount || 0}</span>
            </div>
            <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5">
              <div className="flex items-center gap-2 text-gray-400"><Activity size={16} /> <span className="text-xs font-bold uppercase">Online</span></div>
              <span className="text-sm font-bold text-emerald-400">{services.filter(s => s.status === 'online').length}</span>
            </div>
          </div>

          <div className="mt-8 pt-6 border-t border-white/5">
             <button className="w-full btn-action gap-2 group hover:text-cyan-400 py-3">
               <span className="text-xs font-bold uppercase">System Setup</span>
               <ChevronRight size={14} className="group-hover:translate-x-1 transition-transform" />
             </button>
          </div>
        </motion.div>

        {/* Global Action Cards */}
        <div className="grid grid-cols-2 gap-4">
          <button className="neon-glass p-4 text-center hover:neon-border-cyan transition-all group">
            <Shield size={24} className="mx-auto mb-2 text-cyan-400 group-hover:scale-110 transition-transform" />
            <span className="text-[10px] font-bold uppercase">Update SSL</span>
          </button>
          <button className="neon-glass p-4 text-center hover:neon-border-emerald transition-all group">
            <RefreshCw size={24} className="mx-auto mb-2 text-emerald-400 group-hover:rotate-180 transition-transform duration-500" />
            <span className="text-[10px] font-bold uppercase">Self Update</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 space-y-6 flex flex-col">
        {/* Header - Search & Global Actions */}
        <header className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div className="relative w-full sm:w-96">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={18} />
            <input 
              type="text" 
              placeholder="Search services or domains..." 
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-2xl py-4 pl-12 pr-4 outline-none focus:border-cyan-500/50 focus:bg-white/10 transition-all font-medium placeholder:text-gray-600 shadow-xl"
            />
          </div>

          <div className="flex items-center gap-3 w-full sm:w-auto">
            <button 
              onClick={() => { setEditingService(null); setIsEditorOpen(true); }}
              className="flex-1 sm:flex-none px-8 py-4 bg-cyan-600 hover:bg-cyan-500 rounded-2xl font-black uppercase text-sm flex items-center justify-center gap-2 transition-all shadow-lg shadow-cyan-600/30 active:scale-95"
            >
              <PlusCircle size={20} />
              <span>Add Service</span>
            </button>
            <button className="p-4 neon-glass rounded-2xl text-gray-400 hover:text-white group">
              <Bell size={20} className="group-hover:animate-bounce" />
            </button>
          </div>
        </header>

        {/* Services Grid */}
        <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar">
          <div className="grid grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3 gap-6 pb-20">
            <AnimatePresence mode="popLayout">
              {loading ? (
                [...Array(4)].map((_, i) => (
                  <div key={i} className="neon-glass h-64 animate-pulse bg-white/5 border-none" />
                ))
              ) : filteredServices.length > 0 ? (
                filteredServices.map(service => (
                  <ServiceCard key={service.id} service={service as any} onAction={handleAction} />
                ))
              ) : (
                <div className="col-span-full py-20 text-center neon-glass">
                  <Info size={48} className="mx-auto mb-4 text-gray-700" />
                  <h3 className="text-xl font-bold text-gray-500">No services found</h3>
                  <p className="text-gray-600">Try adjusting your search or add a new service.</p>
                </div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>

      {/* Editor Modal */}
      <AnimatePresence>
        {isEditorOpen && (
          <ServiceEditor 
            service={editingService as any}
            onClose={() => { setIsEditorOpen(false); setEditingService(null); }}
            onSave={handleSaveService}
          />
        )}
      </AnimatePresence>

      {/* Log Viewer Modal */}
      <AnimatePresence>
        {viewingLogs && (
          <LogViewer 
            serviceId={viewingLogs}
            onClose={() => setViewingLogs(null)}
          />
        )}
      </AnimatePresence>

      {/* Pop Notifications */}
      <AnimatePresence>
        {notification && (
          <motion.div
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 50, opacity: 0 }}
            className={`fixed bottom-8 right-8 px-8 py-5 rounded-2xl shadow-2xl z-[200] flex items-center gap-3 backdrop-blur-2xl border ${
              notification.type === 'success' ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-400' : 'bg-red-500/20 border-red-500/50 text-red-400'
            }`}
          >
            {notification.type === 'success' ? <Shield size={24} /> : <Info size={24} />}
            <span className="font-black uppercase tracking-tight">{notification.message}</span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default Dashboard;
