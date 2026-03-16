import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { 
  X, 
  Save, 
  Globe, 
  Server, 
  Shield, 
  Lock, 
  Terminal, 
  PlusCircle
} from 'lucide-react';

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
  ssl: boolean;
  auth: boolean;
  htpasswd?: string;
}

interface ServiceEditorProps {
  service?: Service | null;
  onClose: () => void;
  onSave: (service: Service) => void;
}

const ServiceEditor: React.FC<ServiceEditorProps> = ({ service, onClose, onSave }) => {
  const [formData, setFormData] = useState<Service>({
    name: '',
    vpsId: 'default',
    targetHost: '127.0.0.1',
    targetPort: '80',
    extPort: '',
    tunnelPort: '',
    domain: '',
    type: 'http',
    ssl: false,
    auth: false
  });

  const [vpsList, setVpsList] = useState<{id: string, host: string}[]>([]);

  const API_URL = 'http://' + window.location.hostname + ':3000/api';

  useEffect(() => {
    const init = async () => {
      try {
        const [vpsRes, portsRes] = await Promise.all([
          fetch(`${API_URL}/vps`),
          fetch(`${API_URL}/next-ports`)
        ]);
        
        const vpsData = await vpsRes.json();
        const portsData = await portsRes.json();
        
        setVpsList(vpsData);
        
        if (service) {
          setFormData(service);
        } else {
          setFormData(prev => ({
            ...prev,
            vpsId: vpsData.length > 0 ? vpsData[0].id : 'default',
            extPort: portsData.external.toString(),
            tunnelPort: portsData.tunnel.toString()
          }));
        }
      } catch (error) {
        console.error('Failed to init editor:', error);
      }
    };
    init();
  }, [service]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSave(formData);
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/60 backdrop-blur-md"
    >
      <motion.div
        initial={{ scale: 0.9, y: 20 }}
        animate={{ scale: 1, y: 0 }}
        className="w-full max-w-2xl neon-glass bg-[#0a0d14] overflow-hidden flex flex-col max-h-[90vh]"
      >
        {/* Header */}
        <div className="p-6 border-b border-white/5 flex justify-between items-center">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/20 rounded-lg text-cyan-400">
              <PlusCircle size={24} />
            </div>
            <h2 className="text-2xl font-bold">{service ? 'Edit Service' : 'Add New Service'}</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-white/5 rounded-full transition-colors">
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Basic Info */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase text-gray-500 ml-1">Service Name</label>
              <input 
                required
                disabled={!!service}
                placeholder="e.g., home-nas"
                className="w-full glass-input"
                value={formData.name}
                onChange={e => setFormData({...formData, name: e.target.value})}
              />
            </div>
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase text-gray-500 ml-1">type</label>
              <div className="flex gap-2">
                <button 
                  type="button"
                  onClick={() => setFormData({...formData, type: 'http'})}
                  className={`flex-1 py-2 px-4 rounded-xl border transition-all flex items-center justify-center gap-2 ${
                    formData.type === 'http' ? 'bg-cyan-500/20 border-cyan-500 text-cyan-400' : 'bg-white/5 border-white/10'
                  }`}
                >
                  <Globe size={16} /> HTTP
                </button>
                <button 
                  type="button"
                  onClick={() => setFormData({...formData, type: 'tcp'})}
                  className={`flex-1 py-2 px-4 rounded-xl border transition-all flex items-center justify-center gap-2 ${
                    formData.type === 'tcp' ? 'bg-purple-500/20 border-purple-500 text-purple-400' : 'bg-white/5 border-white/10'
                  }`}
                >
                  <Terminal size={16} /> TCP
                </button>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase text-gray-500 ml-1">Target Host</label>
              <div className="relative">
                 <Server className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
                 <input 
                  required
                  placeholder="127.0.0.1"
                  className="w-full glass-input pl-12"
                  value={formData.targetHost}
                  onChange={e => setFormData({...formData, targetHost: e.target.value})}
                />
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-bold uppercase text-gray-500 ml-1">Target Port</label>
              <input 
                required
                type="number"
                placeholder="8080"
                className="w-full glass-input"
                value={formData.targetPort}
                onChange={e => setFormData({...formData, targetPort: e.target.value})}
              />
            </div>
          </div>

          {/* VPS & Ports */}
          <div className="p-4 rounded-2xl bg-white/5 border border-white/5 space-y-4">
             <div className="flex items-center gap-2 mb-2">
                <Shield size={16} className="text-cyan-400" />
                <span className="text-xs font-black uppercase tracking-widest text-cyan-400">Endpoint Config</span>
             </div>
             
             <div className="space-y-2">
                <label className="text-[10px] font-bold uppercase text-gray-500">Select VPS Node</label>
                <select 
                  className="w-full glass-input appearance-none bg-black/40"
                  value={formData.vpsId}
                  onChange={e => setFormData({...formData, vpsId: e.target.value})}
                >
                  {vpsList.map(v => (
                    <option key={v.id} value={v.id}>{v.id} ({v.host})</option>
                  ))}
                </select>
             </div>

             <div className="grid grid-cols-2 gap-4">
               <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase text-gray-500">External Port (Public)</label>
                  <input 
                    type="number"
                    className="w-full glass-input"
                    value={formData.extPort}
                    onChange={e => setFormData({...formData, extPort: e.target.value})}
                  />
               </div>
               <div className="space-y-2">
                  <label className="text-[10px] font-bold uppercase text-gray-500">SSH Tunnel Port</label>
                  <input 
                    type="number"
                    className="w-full glass-input"
                    value={formData.tunnelPort}
                    onChange={e => setFormData({...formData, tunnelPort: e.target.value})}
                  />
               </div>
             </div>
          </div>

          {/* Advanced / Optional */}
          <div className="space-y-4">
             <div className="space-y-2">
                <label className="text-xs font-bold uppercase text-gray-500 ml-1">Domain Name (Optional)</label>
                <div className="relative">
                   <Globe className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-500" size={16} />
                   <input 
                    placeholder="app.example.com"
                    className="w-full glass-input pl-12"
                    value={formData.domain}
                    onChange={e => setFormData({...formData, domain: e.target.value})}
                  />
                </div>
             </div>

             <div className="flex gap-4">
                <button 
                  type="button"
                  onClick={() => setFormData({...formData, ssl: !formData.ssl})}
                  className={`flex-1 p-4 rounded-2xl border transition-all flex flex-col items-center gap-2 ${
                    formData.ssl ? 'bg-cyan-500/10 border-cyan-500/50 text-cyan-400' : 'bg-white/5 border-white/5 text-gray-500'
                  }`}
                >
                  <Shield size={24} />
                  <span className="text-[10px] font-black uppercase">Enable SSL</span>
                </button>

                <button 
                  type="button"
                  onClick={() => setFormData({...formData, auth: !formData.auth})}
                  className={`flex-1 p-4 rounded-2xl border transition-all flex flex-col items-center gap-2 ${
                    formData.auth ? 'bg-purple-500/10 border-purple-500/50 text-purple-400' : 'bg-white/5 border-white/5 text-gray-500'
                  }`}
                >
                  <Lock size={24} />
                  <span className="text-[10px] font-black uppercase">Basic Auth</span>
                </button>
             </div>
          </div>
        </form>

        {/* Footer */}
        <div className="p-6 border-t border-white/5 flex gap-3">
          <button 
            type="button"
            onClick={onClose}
            className="flex-1 py-3 px-6 rounded-2xl bg-white/5 font-bold hover:bg-white/10 transition-all text-gray-400"
          >
            Cancel
          </button>
          <button 
            onClick={handleSubmit}
            className="flex-[2] py-3 px-6 rounded-2xl bg-gradient-to-r from-cyan-600 to-purple-600 font-bold hover:from-cyan-500 hover:to-purple-500 transition-all flex items-center justify-center gap-2 shadow-xl shadow-cyan-600/20"
          >
            <Save size={20} />
            Save Configuration
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default ServiceEditor;
