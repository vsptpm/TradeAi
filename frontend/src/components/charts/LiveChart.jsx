import { useEffect, useRef, useState } from 'react';
import { createChart, CrosshairMode, CandlestickSeries } from 'lightweight-charts';
import { useAuth } from '../../context/AuthContext';

const CHART_OPTIONS = {
  layout: {
    background: { color: '#0d1321' },
    textColor: '#9ca3af',
    fontFamily: "'Inter', system-ui, sans-serif",
    fontSize: 11,
  },
  grid: {
    vertLines: { visible: false },
    horzLines: { color: '#1f2937' },
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: '#374151', width: 1, style: 1 },
    horzLine: { color: '#374151', width: 1, style: 1 },
  },
  rightPriceScale: {
    borderColor: '#1f2937',
    scaleMargins: { top: 0.1, bottom: 0.1 },
  },
  timeScale: {
    borderColor: '#1f2937',
    timeVisible: true,
    secondsVisible: false,
  },
  handleScroll: true,
  handleScale: true,
};

const CANDLE_OPTIONS = {
  upColor: '#10b981',
  downColor: '#ef4444',
  borderUpColor: '#10b981',
  borderDownColor: '#ef4444',
  wickUpColor: '#10b981',
  wickDownColor: '#ef4444',
};

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/live-feed';
const RECONNECT_DELAY_MS = 3000;

export default function LiveChart() {
  const { token, logout } = useAuth();
  const containerRef = useRef(null);
  const [status, setStatus] = useState('connecting'); // connecting | live | error | no-token

  useEffect(() => {
    if (!token) {
      setStatus('no-token');
      return;
    }
    if (!containerRef.current) return;

    // ── 1. Create chart ─────────────────────────────────────────────
    const chart = createChart(containerRef.current, {
      ...CHART_OPTIONS,
      width: containerRef.current.offsetWidth,
      height: containerRef.current.offsetHeight,
    });
    const series = chart.addSeries(CandlestickSeries, CANDLE_OPTIONS);

    // ── 2. Responsive resize ─────────────────────────────────────────
    const ro = new ResizeObserver(() => {
      if (!containerRef.current) return;
      chart.applyOptions({
        width: containerRef.current.offsetWidth,
        height: containerRef.current.offsetHeight,
      });
    });
    ro.observe(containerRef.current);

    // ── 3. WebSocket ─────────────────────────────────────────────────
    let ws;
    let reconnectTimer = null;
    let destroyed = false;

    function connect() {
      if (destroyed) return;
      setStatus('connecting');
      try {
        ws = new WebSocket(`${WS_URL}?token=${token}`);
      } catch {
        setStatus('error');
        return;
      }

      let wasOpen = false;
      ws.onopen = () => {
        wasOpen = true;
        if (!destroyed) setStatus('live');
      };

      ws.onmessage = (e) => {
        if (destroyed) return;
        try {
          const candle = JSON.parse(e.data);
          // lightweight-charts expects time in seconds
          series.update({
            time: candle.time,
            open: candle.open,
            high: candle.high,
            low: candle.low,
            close: candle.close,
          });
        } catch {
          // malformed frame — ignore
        }
      };

      ws.onerror = () => {
        if (!destroyed) setStatus('error');
      };

      ws.onclose = (e) => {
        if (destroyed) return;
        // If WS was never opened (rejected with 401), force re-login
        if (!wasOpen) {
          logout();
          return;
        }
        setStatus('connecting');
        reconnectTimer = setTimeout(connect, RECONNECT_DELAY_MS);
      };
    }

    connect();

    // ── 4. Cleanup ───────────────────────────────────────────────────
    return () => {
      destroyed = true;
      clearTimeout(reconnectTimer);
      if (ws) {
        ws.onmessage = null;
        ws.onerror = null;
        ws.onclose = null;
        ws.close();
      }
      ro.disconnect();
      chart.remove();
    };
  }, [token]);

  return (
    <div className="relative w-full h-full">
      {/* Status badge */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1.5 px-2 py-1 rounded bg-black/40 backdrop-blur-sm">
        <span
          className={`w-1.5 h-1.5 rounded-full ${
            status === 'live'
              ? 'bg-emerald-400 animate-pulse'
              : status === 'error'
              ? 'bg-red-500'
              : 'bg-yellow-400 animate-pulse'
          }`}
        />
        <span className="text-[10px] text-gray-400 uppercase tracking-wider">
          {status === 'live'
            ? 'Live'
            : status === 'error'
            ? 'Error'
            : status === 'no-token'
            ? 'Auth required'
            : 'Connecting…'}
        </span>
      </div>

      {/* Chart mount point — must fill parent */}
      <div ref={containerRef} className="w-full h-full" />
    </div>
  );
}
