import React from 'react';
import toast from 'react-hot-toast';
import { Check, X, Bot, ShieldCheck } from 'lucide-react';
import LoadingSkeleton from './LoadingSkeleton';
import { API_BASE } from '../config';

function IncidentFeed({ incidents, loading }) {
  if (loading) {
    return <LoadingSkeleton />;
  }

  if (!incidents || incidents.length === 0) {
    return (
      <div className="glass-panel p-12 flex flex-col items-center justify-center text-center text-slate-400 gap-4">
        <div className="p-4 bg-success/10 rounded-full">
          <ShieldCheck className="w-12 h-12 text-success" />
        </div>
        <div>
          <h3 className="text-xl font-semibold text-slate-200">Systems Healthy</h3>
          <p className="mt-1">No active incidents. The autonomous agent is standing by.</p>
        </div>
      </div>
    );
  }

  const approvePlan = async (planId) => {
    try {
      const res = await fetch(`${API_BASE}/api/plans/${planId}/approve`, { 
      	method: 'POST',
        headers: { 'X-API-Key': import.meta.env.VITE_API_KEY || 'sentinelops-hackathon-2026' }
      });
      if (res.ok) toast.success('Plan Approved & Executed successfully');
      else toast.error('Failed to approve plan');
    } catch {
      toast.error('API Error');
    }
  };

  const denyPlan = async (planId) => {
    try {
      const res = await fetch(`http://localhost:8000/api/plans/${planId}/deny`, { 
      	method: 'POST',
      	headers: { 'X-API-Key': import.meta.env.VITE_API_KEY || 'sentinelops-hackathon-2026' }
      });
      if (res.ok) toast.success('Plan Denied');
      else toast.error('Failed to deny plan');
    } catch {
      toast.error('API Error');
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <h2 className="text-xl font-semibold mb-2 flex items-center gap-2">
        Live Incident Feed
      </h2>
      {incidents.map((incident) => (
        <div key={incident.id} className="glass-panel overflow-hidden">
          <div className="p-4 border-b border-white/10 flex justify-between items-center bg-slate-800/50">
            <div className="flex items-center gap-3">
              <span className={`px-2 py-1 rounded text-xs font-bold ${incident.severity === 'high' ? 'bg-danger/20 text-danger' : 'bg-warning/20 text-warning'}`}>
                {incident.severity.toUpperCase()}
              </span>
              <span className="font-mono text-slate-300">{incident.resource}</span>
            </div>
            <span className="text-sm text-slate-400">
              {new Date(incident.created_at).toLocaleTimeString()}
            </span>
          </div>
          
          <div className="p-6">
            <div className="flex flex-col gap-4">
              <div>
                <h3 className="text-sm font-medium text-slate-400">Symptoms</h3>
                <div className="flex gap-2 mt-2">
                  {incident.symptom_tags.map(tag => (
                    <span key={tag} className="px-3 py-1 bg-slate-700/50 rounded-full text-sm border border-slate-600">
                      {tag}
                    </span>
                  ))}
                </div>
              </div>

              {incident.plans && incident.plans.length > 0 && (
                <div className="mt-4 p-5 rounded-lg border border-slate-700 bg-slate-800/30">
                  <h3 className="text-sm font-medium text-slate-400 mb-3">Proposed Action</h3>
                  {incident.plans.map(plan => (
                    <div key={plan.id} className="flex flex-col gap-4">
                      <div className="flex justify-between items-center">
                        <span className="font-mono text-primary text-lg">{plan.action}</span>
                        <div className="flex items-center gap-2 bg-slate-900/50 px-3 py-1 rounded-full border border-slate-700">
                           <span className="text-sm text-slate-400">Confidence</span>
                           <span className="font-bold text-success">{(plan.confidence * 100).toFixed(1)}%</span>
                        </div>
                      </div>
                      
                      <div className="text-sm font-mono text-slate-400 bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                        {JSON.stringify(plan.params)}
                      </div>

                      <div className="mt-2 border-t border-slate-700/50 pt-4">
                        {plan.gate_decision === 'pending_human' ? (
                          <div className="flex gap-3">
                            <button 
                              onClick={() => approvePlan(plan.id)}
                              className="px-5 py-2.5 bg-success/20 text-success hover:bg-success/30 rounded-lg font-medium transition-colors border border-success/30 flex items-center gap-2"
                            >
                              <Check size={18} /> Approve & Execute
                            </button>
                            <button 
                              onClick={() => denyPlan(plan.id)}
                              className="px-5 py-2.5 bg-slate-700 text-slate-300 hover:bg-slate-600 rounded-lg font-medium transition-colors flex items-center gap-2"
                            >
                              <X size={18} /> Deny
                            </button>
                          </div>
                        ) : plan.gate_decision === 'approved' ? (
                          <div className="flex items-center gap-2 text-success font-medium bg-success/10 px-4 py-2 rounded-lg inline-flex border border-success/20">
                            <Bot size={18} />
                            Autonomous Execution Approved
                          </div>
                        ) : (
                          <div className="flex items-center gap-2 text-danger font-medium bg-danger/10 px-4 py-2 rounded-lg inline-flex border border-danger/20">
                            <X size={18} />
                            Action Denied
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export default IncidentFeed;
