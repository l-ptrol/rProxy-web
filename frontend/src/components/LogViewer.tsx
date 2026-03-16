import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { X, Terminal, RefreshCw, Trash2, Download } from 'lucide-react';

interface LogViewerProps {
  serviceId: string;
  onClose: () => void;
}

const LogViewer: React.FC<LogViewerProps> = ({ serviceId, onClose }) => {
  const [logs, setLogs] = useState<string>('Loading logs...');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const logEndRef = useRef<HTMLDivElement>(null);
  
  const API_URL = 'http://' + window.location.hostname + ':3000/api';

  const fetchLogs = async () => {
    try {
      const res = await fetch(`${API_URL}/services/${serviceId}/logs`);
      const data = await res.json();
      setLogs(data.logs);
    } catch (error) {
      setLogs('Error fetching logs. Make sure service is running.');
    }
  };

  useEffect(() => {
    fetchLogs();
    let interval: any;
    if (autoRefresh) {
      interval = setInterval(fetchLogs, 3000);
    }
    return () => clearInterval(interval);
  }, [serviceId, autoRefresh]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[150] flex items-center justify-center p-4 bg-black/80 backdrop-blur-xl"
    >
      <motion.div
        initial={{ scale: 0.9, y: 30 }}
        animate={{ scale: 1, y: 0 }}
        className="w-full max-w-4xl h-[80vh] neon-glass bg-[#05070a] border-cyan-500/30 flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="p-4 border-b border-white/5 flex justify-between items-center bg-white/5">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-cyan-500/20 rounded-lg text-cyan-400">
              <Terminal size={20} />
            </div>
            <div>
              <h3 className="font-bold text-lg">System Logs: {serviceId}</h3>
              <div className="flex items-center gap-2">
                 <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                 <span className="text-[10px] font-bold text-gray-500 uppercase tracking-widest">Live Stream</span>
              </div>
            </div>
          </div>
          
          <div className="flex items-center gap-2">
            <button 
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`p-2 rounded-lg transition-all ${autoRefresh ? 'text-cyan-400 bg-cyan-400/10' : 'text-gray-500 bg-white/5'}`}
              title="Auto Refresh"
            >
              <RefreshCw size={18} className={autoRefresh ? 'animate-spin-slow' : ''} />
            </button>
            <button 
              onClick={onClose}
              className="p-2 hover:bg-white/10 rounded-lg transition-colors text-gray-400"
            >
              <X size={24} />
            </button>
          </div>
        </div>

        {/* Log Content */}
        <div className="flex-1 overflow-y-auto p-6 font-mono text-sm custom-scrollbar">
          <pre className="whitespace-pre-wrap break-all text-gray-300 selection:bg-cyan-500/30">
            {logs || 'No log data available...'}
          </pre>
          <div ref={logEndRef} />
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-white/5 bg-white/5 flex justify-between items-center">
           <p className="text-[10px] font-bold text-gray-600 uppercase tracking-widest">
             Path: /tmp/rproxy_ttyd_{serviceId}.log
           </p>
           <div className="flex gap-2">
              <button className="btn-action text-xs font-bold gap-2 px-4 py-2">
                <Download size={14} /> Download
              </button>
              <button className="btn-action text-xs font-bold gap-2 px-4 py-2 hover:text-red-400">
                <Trash2 size={14} /> Clear
              </button>
           </div>
        </div>
      </motion.div>
    </motion.div>
  );
};

export default LogViewer;
