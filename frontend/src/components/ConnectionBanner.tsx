import React, { useState, useEffect, useRef } from 'react';
import { WifiOff } from 'lucide-react';
import { API_BASE } from '../config';

interface ConnectionBannerProps {
  onStatusChange?: (connected: boolean) => void;
}

function ConnectionBanner({ onStatusChange }: ConnectionBannerProps) {
  const [connected, setConnected] = useState(true);
  const [visible, setVisible] = useState(false);
  const onStatusChangeRef = useRef(onStatusChange);

  useEffect(() => {
    onStatusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  useEffect(() => {
    let isMounted = true;

    const checkHealth = async () => {
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 3000);
        const res = await fetch(`${API_BASE}/health`, {
          signal: controller.signal,
        });
        clearTimeout(timeout);
        if (isMounted) {
          setConnected(res.ok);
          onStatusChangeRef.current?.(res.ok);
        }
      } catch {
        if (isMounted) {
          setConnected(false);
          onStatusChangeRef.current?.(false);
        }
      }
    };

    checkHealth();
    const interval = setInterval(checkHealth, 5000);
    return () => {
      isMounted = false;
      clearInterval(interval);
    };
  }, []);

  // Manage visibility with a delay for the exit animation
  useEffect(() => {
    if (!connected) {
      setVisible(true);
    } else {
      // Small delay to allow CSS transition to play before unmounting
      const timer = setTimeout(() => setVisible(false), 400);
      return () => clearTimeout(timer);
    }
  }, [connected]);

  if (!visible && connected) return null;

  return (
    <div
      className="connection-banner"
      style={{
        opacity: connected ? 0 : 1,
        transform: connected ? 'translateY(-100%)' : 'translateY(0)',
        transition: 'opacity 0.4s ease, transform 0.4s ease',
      }}
    >
      <div className="connection-banner-inner">
        <WifiOff size={16} className="connection-banner-icon" />
        <span className="connection-banner-text">
          API unreachable — Reconnecting...
        </span>
        <span className="connection-banner-pulse" />
      </div>
    </div>
  );
}

export default ConnectionBanner;
