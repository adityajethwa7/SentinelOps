import React, { useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Upload } from 'lucide-react';
import { API_BASE } from '../config';

function DataIngestor({ onIngestSuccess }) {
  const fileInputRef = useRef(null);
  const [isUploading, setIsUploading] = useState(false);

  const handleUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    setIsUploading(true);
    const loadingToast = toast.loading('Ingesting historical data (Day-1 Trust)...');

    try {
      const response = await fetch(`${API_BASE}/api/ingest`, {
        method: 'POST',
        headers: {
          'X-API-Key': import.meta.env.VITE_API_KEY || 'sentinelops-hackathon-2026'
        },
        body: formData
      });

      if (response.ok) {
        const data = await response.json();
        toast.success(`Successfully trained memory with ${data.rows_ingested} records!`, { id: loadingToast });
        if (onIngestSuccess) onIngestSuccess();
      } else {
        throw new Error('Failed to ingest');
      }
    } catch (err) {
      console.error(err);
      toast.error('Failed to ingest historical data.', { id: loadingToast });
    } finally {
      setIsUploading(false);
      // Reset input
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="glass-panel p-6">
      <div className="flex justify-between items-start">
        <div>
          <h2 className="text-xl font-semibold mb-1">Self-Learning Harness</h2>
          <p className="text-sm text-slate-400 mb-4">
            Upload a CSV of past successful remediations (PagerDuty/Jira) to instantly train the Bayesian memory graph.
          </p>
        </div>
      </div>
      
      <input 
        type="file" 
        accept=".csv" 
        className="hidden" 
        ref={fileInputRef} 
        onChange={handleUpload}
      />
      
      <button 
        onClick={() => fileInputRef.current?.click()}
        disabled={isUploading}
        className="w-full py-3 px-4 bg-slate-800 hover:bg-slate-700 border border-slate-600 rounded-lg flex items-center justify-center gap-2 transition-colors text-slate-200"
      >
        <Upload size={18} />
        {isUploading ? 'Ingesting...' : 'Upload Historical Data (CSV)'}
      </button>
    </div>
  );
}

export default DataIngestor;
