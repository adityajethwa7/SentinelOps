import React, { useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

function RechartsGraph({ incidents }) {
  // Extract confidence over time for the demo
  const data = useMemo(() => {
    // Sort incidents by time
    const sorted = [...incidents].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
    
    const chartData = [];
    let idx = 1;
    for (const inc of sorted) {
      if (inc.plans && inc.plans.length > 0) {
        // Take the highest confidence plan
        const maxConf = Math.max(...inc.plans.map(p => p.confidence));
        chartData.push({
          name: `Inc ${idx}`,
          confidence: Math.round((maxConf * 100) * 10) / 10,
          time: new Date(inc.created_at).toLocaleTimeString()
        });
        idx++;
      }
    }
    
    // If empty, return a flat line starting at 19.6%
    if (chartData.length === 0) {
      return [
        { name: 'Start', confidence: 19.6 },
        { name: 'Now', confidence: 19.6 }
      ];
    }
    
    return chartData;
  }, [incidents]);

  return (
    <div className="w-full h-[300px]">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart
          data={data}
          margin={{ top: 10, right: 30, left: 0, bottom: 0 }}
        >
          <defs>
            <linearGradient id="colorConfidence" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
          <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} />
          <YAxis stroke="#94a3b8" fontSize={12} tickLine={false} axisLine={false} domain={[0, 100]} />
          <Tooltip 
            contentStyle={{ backgroundColor: '#1e293b', borderColor: '#334155', borderRadius: '8px', color: '#f8fafc' }}
            itemStyle={{ color: '#3b82f6' }}
          />
          <Area 
            type="monotone" 
            dataKey="confidence" 
            stroke="#3b82f6" 
            strokeWidth={3}
            fillOpacity={1} 
            fill="url(#colorConfidence)" 
            animationDuration={1500}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export default RechartsGraph;
