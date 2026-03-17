import React from 'react';
import { Globe, Server, Power, RefreshCw, Trash2, Edit3, ExternalLink, Shield, Lock, Terminal } from 'lucide-react';

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
  SVC_NDM_AUTH?: string;
  status: 'online' | 'offline';
}

interface ServiceCardProps {
  service: Service;
  onStart: () => void;
  onStop: () => void;
  onRedeployNginx: () => void;
}

const ServiceCard: React.FC<ServiceCardProps> = ({ service, onStart, onStop, onRedeployNginx }) => {
  const isOnline = service.status === 'online';

  const getTypeIcon = () => {
    switch (service.SVC_TYPE) {
      case 'ttyd': return <Terminal size={14} />;
      case 'tcp': return <Server size={14} />;
      default: return <Globe size={14} />;
    }
  };

  const getUrl = () => {
    const proto = service.SVC_SSL === 'yes' ? 'https' : 'http';
    const domain = service.SVC_DOMAIN || 'localhost';
    const port = (service.SVC_EXT_PORT === '80' || service.SVC_EXT_PORT === '443') 
      ? '' 
      : `:${service.SVC_EXT_PORT}`;
    return `${proto}://${domain}${port}`;
  };

  return (
    <div className="glass-card group overflow-hidden flex flex-col h-full border-t-2 border-transparent hover:border-cyan-500/50 transition-all duration-500">
      {/* Card Header */}
      <div className="p-5 flex justify-between items-start">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-xl font-bold text-white group-hover:text-cyan-400 transition-colors">
              {service.name}
            </h3>
            <span className={isOnline ? 'status-online' : 'status-offline'}>
              {isOnline ? 'ONLINE' : 'OFFLINE'}
            </span>
          </div>
          <div className="flex items-center gap-2 text-white/40 text-xs font-bold uppercase tracking-widest">
            {getTypeIcon()}
            <span>{service.SVC_TYPE} Proxy</span>
          </div>
        </div>
        
        <div className="flex gap-2">
          <button className="p-2 bg-white/5 rounded-lg hover:bg-white/10 text-white/60 transition-colors">
            <Edit3 size={16} />
          </button>
          <button className="p-2 bg-white/5 rounded-lg hover:bg-red-500/20 text-white/60 hover:text-red-400 transition-colors">
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {/* Card Body */}
      <div className="px-5 py-4 space-y-4 flex-1">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-1">
            <div className="text-[10px] text-white/30 font-black uppercase tracking-tighter">Источник</div>
            <div className="text-sm font-mono text-cyan-100/80 truncate">
              {service.SVC_TARGET_HOST}:{service.SVC_TARGET_PORT}
            </div>
          </div>
          <div className="space-y-1">
            <div className="text-[10px] text-white/30 font-black uppercase tracking-tighter">Внешний порт</div>
            <div className="text-sm font-mono text-purple-100/80">
              {service.SVC_EXT_PORT}
            </div>
          </div>
        </div>

        {service.SVC_DOMAIN && (
          <div className="space-y-1 p-3 bg-black/20 rounded-xl border border-white/5">
            <div className="text-[10px] text-white/30 font-black uppercase tracking-tighter flex items-center gap-1">
              <Globe size={10} /> Домен доступа
            </div>
            <div className="text-sm font-medium text-white/90 truncate flex items-center justify-between">
              {service.SVC_DOMAIN}
              <a href={getUrl()} target="_blank" rel="noreferrer" className="text-cyan-400 hover:text-cyan-300">
                <ExternalLink size={14} />
              </a>
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-2">
          {service.SVC_SSL === 'yes' && (
            <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-emerald-500/10 text-emerald-400 text-[10px] font-bold border border-emerald-500/20">
              <Shield size={10} /> SSL ACTIVE
            </div>
          )}
          {service.SVC_NDM_AUTH === 'yes' && (
            <div className="flex items-center gap-1 px-2 py-1 rounded-md bg-amber-500/10 text-amber-400 text-[10px] font-bold border border-amber-500/20">
              <Lock size={10} /> AUTH ENABLED
            </div>
          )}
        </div>
      </div>

      {/* Card Footer */}
      <div className="p-4 bg-white/5 border-t border-white/5 flex gap-3">
        {isOnline ? (
          <button 
            onClick={onStop}
            className="flex-1 flex items-center justify-center gap-2 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-500 rounded-xl font-bold text-sm transition-all"
          >
            <Power size={16} /> ОСТАНОВИТЬ
          </button>
        ) : (
          <button 
            onClick={onStart}
            className="flex-1 flex items-center justify-center gap-2 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-500 rounded-xl font-bold text-sm transition-all"
          >
            <Power size={16} /> ЗАПУСТИТЬ
          </button>
        )}
        <button 
          onClick={onRedeployNginx}
          title="Исправить (перезаписать) конфигурацию nginx"
          className="px-4 py-2 bg-white/5 hover:bg-cyan-500/10 text-white hover:text-cyan-400 rounded-xl transition-all"
        >
          <RefreshCw size={16} className={isOnline ? 'animate-spin-slow' : ''} />
        </button>
      </div>
    </div>
  );
};

export default ServiceCard;
