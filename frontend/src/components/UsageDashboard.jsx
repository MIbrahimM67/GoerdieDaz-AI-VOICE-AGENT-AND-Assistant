/**
 * GeordieDaz — Usage Dashboard
 * JARVIS-styled cost tracking panel showing API spend breakdown.
 * Displays total costs, per-service breakdown, and per-call detail.
 */
import { useState, useEffect, useCallback } from 'react';
import useAppStore from '../stores/appStore';
import { BarChart3, DollarSign, Zap, Radio, Brain, Mic, X } from 'lucide-react';

const SERVICE_CONFIG = {
  openai_realtime:  { label: 'Realtime Voice',   icon: Radio,     color: '#00d4ff' },
  elevenlabs_tts:   { label: 'ElevenLabs TTS',   icon: Mic,       color: '#10b981' },
  gpt4o_extraction: { label: 'Memory Extract',   icon: Brain,     color: '#ff9e00' },
  embedding:        { label: 'Embeddings',        icon: Zap,       color: '#a78bfa' },
  whisper:          { label: 'Whisper STT',       icon: Mic,       color: '#f472b6' },
};

export default function UsageDashboard({ onClose }) {
  const { accessToken } = useAppStore();
  const [summary, setSummary] = useState(null);
  const [detail, setDetail] = useState([]);
  const [daily, setDaily] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');
  const [period, setPeriod] = useState(30);

  const apiBase = import.meta.env.VITE_API_URL || '';

  const fetchUsage = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const headers = { Authorization: `Bearer ${accessToken}` };
      const [sumRes, dailyRes, detailRes] = await Promise.all([
        fetch(`${apiBase}/api/usage/summary?days=${period}`, { headers }),
        fetch(`${apiBase}/api/usage/daily?days=${period}`, { headers }),
        fetch(`${apiBase}/api/usage/detail?days=7&limit=50`, { headers }),
      ]);
      if (sumRes.ok) setSummary(await sumRes.json());
      if (dailyRes.ok) setDaily(await dailyRes.json());
      if (detailRes.ok) setDetail(await detailRes.json());
    } catch (e) {
      console.error('[Usage] Fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, [accessToken, period, apiBase]);

  useEffect(() => { fetchUsage(); }, [fetchUsage]);

  const formatCost = (usd) => {
    if (usd === undefined || usd === null) return '$0.00';
    if (usd < 0.01) return `$${usd.toFixed(4)}`;
    return `$${usd.toFixed(2)}`;
  };

  return (
    <div className="usage-dashboard-overlay" onClick={onClose}>
      <div className="usage-dashboard" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="usage-header">
          <div className="usage-header-left">
            <BarChart3 size={20} style={{ color: '#00f0ff' }} />
            <h2>USAGE TRACKER</h2>
          </div>
          <div className="usage-header-right">
            <select
              className="usage-period-select"
              value={period}
              onChange={e => setPeriod(Number(e.target.value))}
            >
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
            </select>
            <button className="usage-close-btn" onClick={onClose}>
              <X size={16} />
            </button>
          </div>
        </div>

        {loading ? (
          <div className="usage-loading">
            <div className="usage-spinner" />
            <p>Loading usage data...</p>
          </div>
        ) : (
          <>
            {/* Tabs */}
            <div className="usage-tabs">
              <button
                className={`usage-tab ${activeTab === 'overview' ? 'active' : ''}`}
                onClick={() => setActiveTab('overview')}
              >Overview</button>
              <button
                className={`usage-tab ${activeTab === 'detail' ? 'active' : ''}`}
                onClick={() => setActiveTab('detail')}
              >Call Log</button>
            </div>

            {activeTab === 'overview' && summary && (
              <div className="usage-content">
                {/* Total Card */}
                <div className="usage-total-card">
                  <div className="usage-total-label">TOTAL SPEND ({period} DAYS)</div>
                  <div className="usage-total-amount">{formatCost(summary.total_cost_usd)}</div>
                  <div className="usage-total-calls">{summary.total_calls} API calls</div>
                </div>

                {/* Service Breakdown */}
                <div className="usage-breakdown">
                  <h3>BY SERVICE</h3>
                  {Object.entries(summary.by_service || {}).map(([service, data]) => {
                    const cfg = SERVICE_CONFIG[service] || { label: service, color: '#64748b', icon: Zap };
                    const Icon = cfg.icon;
                    const pct = summary.total_cost_usd > 0
                      ? ((data.cost_usd / summary.total_cost_usd) * 100).toFixed(0)
                      : 0;
                    return (
                      <div key={service} className="usage-service-row">
                        <div className="usage-service-info">
                          <Icon size={14} style={{ color: cfg.color }} />
                          <span className="usage-service-label">{cfg.label}</span>
                        </div>
                        <div className="usage-service-bar-wrap">
                          <div
                            className="usage-service-bar"
                            style={{
                              width: `${Math.max(2, pct)}%`,
                              background: cfg.color,
                            }}
                          />
                        </div>
                        <div className="usage-service-stats">
                          <span className="usage-service-cost">{formatCost(data.cost_usd)}</span>
                          <span className="usage-service-pct">{pct}%</span>
                        </div>
                      </div>
                    );
                  })}
                  {Object.keys(summary.by_service || {}).length === 0 && (
                    <p className="usage-empty">No usage data yet. Start a voice session to begin tracking.</p>
                  )}
                </div>

                {/* Daily Chart (simplified bars) */}
                {daily.length > 0 && (
                  <div className="usage-daily">
                    <h3>DAILY COSTS</h3>
                    <div className="usage-daily-chart">
                      {daily.slice(0, 14).reverse().map((day, i) => {
                        const maxCost = Math.max(...daily.map(d => d.total), 0.01);
                        const barHeight = Math.max(4, (day.total / maxCost) * 80);
                        return (
                          <div key={i} className="usage-daily-bar-wrap" title={`${day.date}: ${formatCost(day.total)}`}>
                            <div
                              className="usage-daily-bar"
                              style={{ height: `${barHeight}px` }}
                            />
                            <span className="usage-daily-label">{day.date.slice(5)}</span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'detail' && (
              <div className="usage-content">
                <div className="usage-detail-table">
                  <div className="usage-detail-header">
                    <span>Time</span>
                    <span>Service</span>
                    <span>Operation</span>
                    <span>Tokens</span>
                    <span>Cost</span>
                  </div>
                  {detail.map((row, i) => {
                    const cfg = SERVICE_CONFIG[row.service] || { label: row.service, color: '#64748b' };
                    return (
                      <div key={i} className="usage-detail-row">
                        <span className="usage-detail-time">
                          {new Date(row.created_at).toLocaleString('en-GB', {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                          })}
                        </span>
                        <span className="usage-detail-service" style={{ color: cfg.color }}>
                          {cfg.label}
                        </span>
                        <span>{row.operation}</span>
                        <span>{row.tokens_in + row.tokens_out > 0 ? `${row.tokens_in}/${row.tokens_out}` : row.characters > 0 ? `${row.characters} chars` : `${row.duration_seconds.toFixed(1)}s`}</span>
                        <span className="usage-detail-cost">{formatCost(row.cost_usd)}</span>
                      </div>
                    );
                  })}
                  {detail.length === 0 && (
                    <p className="usage-empty">No calls logged yet.</p>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
