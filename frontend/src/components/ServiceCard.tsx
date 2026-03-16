import React from 'react';
import { motion } from 'framer-motion';
import { 
  Globe, 
  Server, 
  Power, 
  Trash2, 
  Edit3, 
  ExternalLink, 
  Shield, 
  Lock,
  Terminal,
  Activity,
  FileText
} from 'lucide-react';

interface Service {
  id: string;
  name: string;
  targetHost: string;
  targetPort: string;
  extPort: string;
  domain: string;
  type: string;
  enabled: boolean;
  ssl: boolean;
  auth: boolean;
  status: 'online' | 'offline';
}

interface ServiceCardProps {
  service: Service;
  onAction: (id: string, action: string) => void;
}

const ServiceCard: React.FC<ServiceCardProps> = ({ service, onAction }) => {
  const isOnline = service.status === 'online';

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      whileHover={{ y: -5 }}
      className={`neon-glass p-5 relative overflow-hidden group ${
        isOnline ? 'neon-border-emerald' : 'neon-border-purple'
      }`}
    >
      {/* Background Decorative Element */}
      <div className={`absolute -right-10 -top-10 w-32 h-32 rounded-full blur-3xl opacity-10 transition-colors duration-500 ${
        isOnline ? 'bg-emerald-500' : 'bg-purple-500'
      }`} />

      {/* Header */}
      <div className="flex justify-between items-start mb-6 relative z-10">
        <div className="flex items-center gap-3">
          <div className={`p-3 rounded-2xl ${isOnline ? 'bg-emerald-500/10 text-emerald-400' : 'bg-white/5 text-purple-400'}`}>
            {service.type === 'tcp' ? <Terminal size={24} /> : <Globe size={24} />}
          </div>
          <div>
            <h3 className="text-xl font-bold tracking-tight group-hover:neon-text-cyan transition-all">
              {service.name}
            </h3>
            <div className="flex items-center gap-2 mt-1">
              <span className={`status-dot ${isOnline ? 'online-dot' : 'offline-dot'}`} />
              <span className={`text-[10px] font-black uppercase tracking-[0.2em] ${isOnline ? 'text-emerald-400' : 'text-red-400'}`}>
                {isOnline ? 'On-Air' : 'Standby'}
              </span>
            </div>
          </div>
        </div>
        
        <div className="flex gap-1">
          {service.ssl && <Shield size={16} className="text-cyan-400 opacity-60" />}
          {service.auth && <Lock size={16} className="text-purple-400 opacity-60" />}
        </div>
      </div>

      {/* Connection Details */}
      <div className="space-y-2 mb-6 relative z-10">
        <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5 group-hover:bg-white/10 transition-all">
          <div className="flex items-center gap-2 text-[10px] font-bold uppercase text-gray-500">
            <Server size={12} />
            <span>Target</span>
          </div>
          <span className="font-mono text-sm text-gray-300">{service.targetHost}:{service.targetPort}</span>
        </div>

        <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/5 group-hover:bg-white/10 transition-all">
          <div className="flex items-center gap-2 text-[10px] font-bold uppercase text-gray-500">
            <ExternalLink size={12} />
            <span>Public</span>
          </div>
          <span className="font-mono text-sm text-cyan-400 font-bold">{service.extPort}</span>
        </div>

        {service.domain && (
          <div className="flex items-center justify-between p-3 rounded-xl bg-white/5 border border-white/10 group-hover:bg-cyan-500/10 transition-all">
            <div className="flex items-center gap-2 text-[10px] font-bold uppercase text-gray-500">
              <Activity size={12} />
              <span>Route</span>
            </div>
            <a 
              href={`https://${service.domain}`} 
              target="_blank" 
              rel="noreferrer"
              className="text-xs text-cyan-400 font-bold hover:underline underline-offset-4"
            >
              {service.domain}
            </a>
          </div>
        )}
      </div>

      {/* Quick Actions Footer */}
      <div className="flex items-center gap-2 pt-4 border-t border-white/5 relative z-10">
        <motion.button
          whileTap={{ scale: 0.95 }}
          onClick={() => onAction(service.id, isOnline ? 'stop' : 'start')}
          className={`flex-1 btn-action rounded-xl ${isOnline ? 'hover:text-red-400 hover:bg-red-400/10' : 'hover:text-emerald-400 hover:bg-emerald-400/10'}`}
        >
          <Power size={18} />
          <span className="ml-2 text-xs font-black uppercase">{isOnline ? 'OFF' : 'ON'}</span>
        </motion.button>

        <button 
          onClick={() => onAction(service.id, 'logs')}
          className="btn-action hover:text-cyan-400 hover:bg-cyan-400/10" 
          title="Streaming Logs"
        >
          <FileText size={18} />
        </button>

        <button 
          onClick={() => onAction(service.id, 'edit')}
          className="btn-action hover:text-white hover:bg-white/10" 
          title="Settings"
        >
          <Edit3 size={18} />
        </button>

        <button 
          onClick={() => onAction(service.id, 'remove')}
          className="btn-action hover:text-red-500 hover:bg-red-500/10" 
          title="Destroy"
        >
          <Trash2 size={18} />
        </button>
      </div>
    </motion.div>
  );
};

export default ServiceCard;
