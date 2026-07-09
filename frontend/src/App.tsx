import React, { useState, useEffect, useCallback } from 'react';
import { Toaster } from 'react-hot-toast';
import { Shield } from 'lucide-react';
import IncidentFeed from './components/IncidentFeed';
import RechartsGraph from './components/RechartsGraph';
import DataIngestor from './components/DataIngestor';
import ConnectionBanner from './components/ConnectionBanner';
import ErrorBoundary from './components/ErrorBoundary';
import { API_BASE } from './config';

function App() {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isApiError, setIsApiError] = useState(false);

  const fetchIncidents = useCallback(async () => {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);
    try {
      const response = await fetch(`${API_BASE}/api/incidents`, {
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (response.ok) {
        const data = await response.json();
        setIncidents(data);
        setIsApiError(false);
      } else {
        setIsApiError(true);
      }
    } catch (e) {
      clearTimeout(timeoutId);
      console.error("Failed to fetch incidents", e);
      setIsApiError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout>;
    let isMounted = true;
    
    const poll = async () => {
      if (!isMounted) return;
      await fetchIncidents();
      if (isMounted) {
        timeoutId = setTimeout(poll, 2000);
      }
    };
    
    poll();
    
    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
    };
  }, [fetchIncidents]);

  return (
    <div className="min-h-screen p-4 md:p-8 max-w-7xl mx-auto flex flex-col gap-8">
      <ConnectionBanner onStatusChange={(connected) => setIsApiError(!connected)} />
      <Toaster position="top-right" toastOptions={{ className: 'glass-panel !bg-slate-800 !text-slate-200' }} />
      
      <header className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 glass-panel p-6">
        <div className="flex items-center gap-4">
          <div className="p-3 bg-primary/20 rounded-xl">
            <Shield className="text-primary w-8 h-8" />
          </div>
          <div>
            <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-primary to-accent">
              SentinelOps
            </h1>
            <p className="text-slate-400 mt-1">Autonomous Remediation Dashboard</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 bg-slate-800/50 px-4 py-2 rounded-full border border-white/5">
            <div className={`w-3 h-3 rounded-full ${isApiError ? 'bg-danger shadow-[0_0_10px_rgba(239,68,68,0.7)]' : 'bg-success shadow-[0_0_10px_rgba(16,185,129,0.7)]'} animate-pulse`}></div>
            <span className="text-sm font-medium text-slate-300">
              {isApiError ? 'Connection Lost' : 'System Active'}
            </span>
          </div>
        </div>
      </header>

      {isApiError && (
        <div className="glass-panel p-4 border border-danger/30 bg-danger/10 text-danger flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-semibold">Offline:</span>
            <span>Failed to connect to SentinelOps API. Please check your backend connection.</span>
          </div>
          <button 
            onClick={() => {
              setLoading(true);
              fetchIncidents();
            }}
            className="px-4 py-1.5 bg-danger/20 hover:bg-danger/30 border border-danger/30 rounded text-xs font-semibold text-slate-200 uppercase transition-colors whitespace-nowrap"
          >
            Retry Connection
          </button>
        </div>
      )}

      <ErrorBoundary>
        <main className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2">
            <IncidentFeed incidents={incidents} loading={loading} />
          </div>
          <div className="flex flex-col gap-8">
            <DataIngestor onIngestSuccess={fetchIncidents} />
            
            <div className="glass-panel p-6 flex flex-col gap-4">
               <h2 className="text-xl font-semibold">Live Confidence Trends</h2>
               <p className="text-sm text-slate-400 mb-2">
                 Bayesian graph memory updates automatically after successful remediations.
               </p>
               <RechartsGraph incidents={incidents} />
            </div>
          </div>
        </main>
      </ErrorBoundary>
    </div>
  );
}

export default App;
