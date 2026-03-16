import React from 'react';
import { motion } from 'framer-motion';
import { Globe, Server, Power, RefreshCw, Trash2, Edit3, ExternalLink } from 'lucide-react';

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

interface Props {
  service: Service;
  index: number;
}

const ServiceCard: React.FC<Props> = ({ service, index }) => {
  const isHttp = service.ext_port === '443' || (service.domain && service.domain.length > 0);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.1 }}
      whileHover={{ y: -5 }}
      className="glass-card p-6 flex flex-col justify-between group"
    >
      <div>
        <div className="flex justify-between items-start mb-4">
          <div className={`p-2 rounded-lg ${service.running ? 'bg-emerald-500/10' : 'bg-white/5'}`}>
            {isHttp ? (
              <Globe className={`w-6 h-6 ${service.running ? 'text-emerald-400' : 'text-white/40'}`} />
            ) : (
              <Server className={`w-6 h-6 ${service.running ? 'text-emerald-400' : 'text-white/40'}`} />
            )}
          </div>
          <div className={service.running ? 'status-online' : 'status-offline'}>
            {service.running ? 'ОНЛАЙН' : 'ОФЛАЙН'}
          </div>
        </div>

        <h3 className="text-xl font-bold mb-1 truncate text-white group-hover:text-accent-cyan transition-colors">
          {service.name || service.id}
        </h3>
        
        <div className="space-y-2 mb-6">
          <div className="flex items-center gap-2 text-white/40 text-sm">
            <span className="font-mono text-xs px-2 py-0.5 bg-black/30 rounded border border-white/5">
              {service.target_host}:{service.target_port}
            </span>
          </div>
          {service.domain && (
            <div className="flex items-center gap-2 text-accent-cyan text-sm font-medium">
              <ExternalLink className="w-3 h-3" />
              <span className="truncate">{service.domain}</span>
            </div>
          )}
          {!service.domain && service.ext_port && (
            <div className="text-white/60 text-sm">
              Внешний порт: <span className="text-white font-mono">{service.ext_port}</span>
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between gap-2 pt-4 border-t border-white/5">
        <div className="flex gap-1">
          <button title="Редактировать" className="p-2 hover:bg-white/5 rounded-lg text-white/40 hover:text-white transition-colors">
            <Edit3 className="w-4 h-4" />
          </button>
          <button title="Удалить" className="p-2 hover:bg-red-500/10 rounded-lg text-white/40 hover:text-red-400 transition-colors">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
        
        <div className="flex gap-2">
          {service.running ? (
            <>
              <button className="p-2 bg-white/5 hover:bg-white/10 rounded-lg text-white/60 transition-all">
                <RefreshCw className="w-4 h-4" />
              </button>
              <button className="p-2 bg-red-500/20 hover:bg-red-500/30 rounded-lg text-red-400 transition-all">
                <Power className="w-4 h-4" />
              </button>
            </>
          ) : (
            <button className="flex items-center gap-2 px-4 py-2 bg-emerald-500/20 hover:bg-emerald-500/30 rounded-lg text-emerald-400 font-bold text-sm transition-all">
              <Power className="w-4 h-4" /> ЗАПУСК
            </button>
          )}
        </div>
      </div>
    </motion.div>
  );
};

export default ServiceCard;
