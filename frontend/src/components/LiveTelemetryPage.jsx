/**
 * GeordieDaz — Live Telemetry & Financial Traceability Page
 * Full-Page JARVIS Command Center for Real-Time Cost & AI Operations Auditing.
 */
import { useState, useEffect, useMemo, useCallback } from 'react';
import useAppStore from '../stores/appStore';
import {
  Activity,
  ArrowLeft,
  BarChart3,
  Brain,
  CheckCircle2,
  Clock,
  Coins,
  Cpu,
  Database,
  Download,
  Filter,
  Flame,
  Layers,
  Mic,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Terminal,
  Trash2,
  Volume2,
  Zap,
} from 'lucide-react';

const SERVICE_META = {
  openai_realtime: {
    label: 'OpenAI Realtime Voice',
    short: 'Realtime Voice',
    model: 'gpt-realtime-mini',
    icon: Radio,
    color: '#00f0ff',
    badgeClass: 'badge-realtime',
    rateInfo: '$0.06/min in, $0.24/min out',
  },
  elevenlabs_tts: {
    label: 'ElevenLabs TTS (Cloned Voice)',
    short: 'ElevenLabs TTS',
    model: 'eleven_flash_v2_5',
    icon: Volume2,
    color: '#10b981',
    badgeClass: 'badge-elevenlabs',
    rateInfo: '~$0.15 / 1k characters',
  },
  gpt4o_extraction: {
    label: 'Memory Extraction (LLM)',
    short: 'GPT-4o Mini Extract',
    model: 'gpt-4o-mini',
    icon: Brain,
    color: '#ff9e00',
    badgeClass: 'badge-gpt4o',
    rateInfo: '$0.15/1M in, $0.60/1M out',
  },
  embedding: {
    label: 'Vector Embeddings (pgvector)',
    short: 'Vector Embed',
    model: 'text-embedding-3-small',
    icon: Zap,
    color: '#a78bfa',
    badgeClass: 'badge-embedding',
    rateInfo: '$0.02 / 1M tokens',
  },
  whisper: {
    label: 'Whisper Speech-to-Text',
    short: 'Whisper STT',
    model: 'whisper-1',
    icon: Mic,
    color: '#f472b6',
    badgeClass: 'badge-whisper',
    rateInfo: '$0.006 / min',
  },
};

export default function LiveTelemetryPage({ onBack }) {
  const { accessToken, isConnected, telemetryEvents, clearTelemetryEvents, setActiveView } = useAppStore();

  const [dbSummary, setDbSummary] = useState(null);
  const [dbDaily, setDbDaily] = useState([]);
  const [dbDetail, setDbDetail] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isStreamPaused, setIsStreamPaused] = useState(false);

  // Filters
  const [timeRange, setTimeRange] = useState(7); // 1, 7, 30, 90
  const [selectedService, setSelectedService] = useState('all');
  const [selectedOperation, setSelectedOperation] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [inspectedTrace, setInspectedTrace] = useState(null);

  const apiBase = import.meta.env.VITE_API_URL || '';

  // Fetch Database Records
  const fetchHistoricalData = useCallback(async (silent = false) => {
    if (!accessToken) return;
    if (!silent) setIsLoading(true);
    else setIsRefreshing(true);

    try {
      const headers = { Authorization: `Bearer ${accessToken}` };
      const [sumRes, dailyRes, detailRes] = await Promise.all([
        fetch(`${apiBase}/api/usage/summary?days=${timeRange}`, { headers }),
        fetch(`${apiBase}/api/usage/daily?days=${timeRange}`, { headers }),
        fetch(`${apiBase}/api/usage/detail?days=${timeRange}&limit=150`, { headers }),
      ]);

      if (sumRes.ok) setDbSummary(await sumRes.json());
      if (dailyRes.ok) setDbDaily(await dailyRes.json());
      if (detailRes.ok) setDbDetail(await detailRes.json());
    } catch (err) {
      console.error('[Telemetry] Fetch error:', err);
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, [accessToken, timeRange, apiBase]);

  useEffect(() => {
    fetchHistoricalData();
  }, [fetchHistoricalData]);

  // Periodic Auto-Sync (every 8 seconds to merge DB updates)
  useEffect(() => {
    const timer = setInterval(() => {
      if (!isStreamPaused) {
        fetchHistoricalData(true);
      }
    }, 8000);
    return () => clearInterval(timer);
  }, [fetchHistoricalData, isStreamPaused]);

  // Merge Live WS Stream Events with DB Detail Log (deduplicated by ID)
  const combinedTraces = useMemo(() => {
    const map = new Map();

    // 1. Add Live In-Memory Telemetry Events first (latest live state)
    if (!isStreamPaused) {
      telemetryEvents.forEach((evt) => {
        if (evt.id) map.set(evt.id, { ...evt, _isLive: true });
      });
    }

    // 2. Add DB Detail records
    dbDetail.forEach((evt) => {
      if (evt.id && !map.has(evt.id)) {
        map.set(evt.id, { ...evt, _isLive: false });
      }
    });

    // Convert to sorted list by created_at desc
    const list = Array.from(map.values()).sort((a, b) => {
      const tA = new Date(a.created_at || a._clientTimestamp || 0).getTime();
      const tB = new Date(b.created_at || b._clientTimestamp || 0).getTime();
      return tB - tA;
    });

    return list;
  }, [telemetryEvents, dbDetail, isStreamPaused]);

  // Filtered Trace List
  const filteredTraces = useMemo(() => {
    return combinedTraces.filter((trace) => {
      if (selectedService !== 'all' && trace.service !== selectedService) {
        return false;
      }
      if (selectedOperation !== 'all' && trace.operation !== selectedOperation) {
        return false;
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const str = `${trace.service} ${trace.operation} ${trace.id} ${JSON.stringify(trace.metadata || {})}`.toLowerCase();
        if (!str.includes(q)) return false;
      }
      return true;
    });
  }, [combinedTraces, selectedService, selectedOperation, searchQuery]);

  // Aggregate Metrics
  const metrics = useMemo(() => {
    let totalCost = dbSummary?.total_cost_usd || 0;
    let totalCalls = dbSummary?.total_calls || combinedTraces.length;
    let totalTokens = (dbSummary?.total_tokens_in || 0) + (dbSummary?.total_tokens_out || 0);
    let totalChars = dbSummary?.total_characters || 0;
    let totalDuration = dbSummary?.total_duration_seconds || 0;

    // Add un-synced live in-memory deltas
    telemetryEvents.forEach((evt) => {
      if (!dbDetail.some((d) => d.id === evt.id)) {
        totalCost += evt.cost_usd || 0;
        totalCalls += 1;
        totalTokens += (evt.tokens_in || 0) + (evt.tokens_out || 0);
        totalChars += evt.characters || 0;
        totalDuration += evt.duration_seconds || 0;
      }
    });

    const avgCostPerCall = totalCalls > 0 ? totalCost / totalCalls : 0;

    return {
      totalCost,
      totalCalls,
      totalTokens,
      totalChars,
      totalDuration,
      avgCostPerCall,
    };
  }, [dbSummary, dbDetail, combinedTraces.length, telemetryEvents]);

  // Format currency
  const fmtUSD = (amt) => {
    if (amt === undefined || amt === null) return '$0.0000';
    if (amt === 0) return '$0.0000';
    if (amt < 0.001) return `$${amt.toFixed(5)}`;
    if (amt < 0.01) return `$${amt.toFixed(4)}`;
    return `$${amt.toFixed(3)}`;
  };

  // Export CSV
  const handleExportCSV = () => {
    if (filteredTraces.length === 0) return;
    const headers = ['Timestamp (UTC)', 'Trace ID', 'Service', 'Operation', 'Tokens In', 'Tokens Out', 'Characters', 'Duration (s)', 'Cost (USD)', 'Metadata JSON'];
    const rows = filteredTraces.map((t) => [
      t.created_at,
      t.id,
      t.service,
      t.operation,
      t.tokens_in || 0,
      t.tokens_out || 0,
      t.characters || 0,
      t.duration_seconds || 0,
      t.cost_usd || 0,
      `"${JSON.stringify(t.metadata || {}).replace(/"/g, '""')}"`,
    ]);

    const csvContent = [headers.join(','), ...rows.map((r) => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.setAttribute('href', url);
    link.setAttribute('download', `geordiedaz_telemetry_audit_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="telemetry-page">
      {/* ── Top Command Bar ────────────────────────────────────────── */}
      <header className="telemetry-topbar">
        <div className="telemetry-topbar-left">
          <button
            className="telemetry-back-btn"
            onClick={() => {
              if (onBack) onBack();
              else setActiveView('cockpit');
            }}
            title="Return to JARVIS Cockpit HUD"
          >
            <ArrowLeft size={16} />
            <span>COCKPIT HUD</span>
          </button>

          <div className="telemetry-title-group">
            <div className="telemetry-title-badge">
              <Activity size={14} className="pulse-icon" />
              <span>LIVE TRACEABILITY ENGINE</span>
            </div>
            <h1 className="telemetry-title">COST & TELEMETRY COMMAND CENTER</h1>
          </div>
        </div>

        <div className="telemetry-topbar-right">
          {/* Live WS Status Indicator */}
          <div className="live-status-pill">
            <span className={`live-radar-dot ${isConnected ? 'live' : 'offline'}`} />
            <span className="live-status-text">
              {isConnected ? 'LIVE WS CONNECTED' : 'WS OFFLINE'}
            </span>
          </div>

          {/* Timeframe Selector */}
          <div className="telemetry-timeframe-wrap">
            <Clock size={13} color="var(--accent)" />
            <select
              className="telemetry-select"
              value={timeRange}
              onChange={(e) => setTimeRange(Number(e.target.value))}
            >
              <option value={1}>Today (24 Hours)</option>
              <option value={7}>Last 7 Days</option>
              <option value={30}>Last 30 Days</option>
              <option value={90}>Last 90 Days</option>
            </select>
          </div>

          {/* Pause / Resume Live Stream */}
          <button
            className={`telemetry-action-btn ${isStreamPaused ? 'paused' : ''}`}
            onClick={() => setIsStreamPaused(!isStreamPaused)}
            title={isStreamPaused ? 'Resume Live Stream' : 'Pause Live Stream'}
          >
            {isStreamPaused ? <Play size={13} /> : <Pause size={13} />}
            <span>{isStreamPaused ? 'RESUME STREAM' : 'PAUSE STREAM'}</span>
          </button>

          {/* Refresh Data */}
          <button
            className="telemetry-action-btn"
            onClick={() => fetchHistoricalData(false)}
            disabled={isRefreshing}
            title="Force refresh data from database"
          >
            <RefreshCw size={13} className={isRefreshing ? 'spin-icon' : ''} />
            <span>SYNC</span>
          </button>

          {/* Export CSV */}
          <button
            className="telemetry-action-btn export-btn"
            onClick={handleExportCSV}
            title="Download CSV report of filtered traces"
          >
            <Download size={13} />
            <span>EXPORT CSV</span>
          </button>
        </div>
      </header>

      {/* ── Main Content Body ──────────────────────────────────────── */}
      <div className="telemetry-body">
        {/* ── HUD Telemetry Metric Cards ───────────────────────────── */}
        <section className="telemetry-metrics-grid">
          {/* Total Spend */}
          <div className="telemetry-stat-card glow-cyan">
            <div className="stat-card-header">
              <span className="stat-card-label">TOTAL ACCUMULATED SPEND</span>
              <Coins size={16} className="stat-card-icon cyan" />
            </div>
            <div className="stat-card-value text-cyan">
              {fmtUSD(metrics.totalCost)}
            </div>
            <div className="stat-card-sub">
              <span>{metrics.totalCalls} total billable events</span>
              <span className="stat-badge-pulse">LIVE AUDITED</span>
            </div>
          </div>

          {/* Avg Cost per Call */}
          <div className="telemetry-stat-card">
            <div className="stat-card-header">
              <span className="stat-card-label">AVG COST PER INVOCATION</span>
              <Flame size={16} className="stat-card-icon amber" />
            </div>
            <div className="stat-card-value text-amber">
              {fmtUSD(metrics.avgCostPerCall)}
            </div>
            <div className="stat-card-sub">
              <span>Efficiency rating: High</span>
            </div>
          </div>

          {/* Total Tokens Processed */}
          <div className="telemetry-stat-card">
            <div className="stat-card-header">
              <span className="stat-card-label">TOTAL LLM / VECTOR TOKENS</span>
              <Cpu size={16} className="stat-card-icon purple" />
            </div>
            <div className="stat-card-value text-purple">
              {metrics.totalTokens.toLocaleString()}
            </div>
            <div className="stat-card-sub">
              <span>In: {dbSummary?.total_tokens_in?.toLocaleString() || 0} | Out: {dbSummary?.total_tokens_out?.toLocaleString() || 0}</span>
            </div>
          </div>

          {/* Voice & TTS Metrics */}
          <div className="telemetry-stat-card">
            <div className="stat-card-header">
              <span className="stat-card-label">VOICE AUDIO & TTS VOLUME</span>
              <Volume2 size={16} className="stat-card-icon emerald" />
            </div>
            <div className="stat-card-value text-emerald">
              {metrics.totalDuration > 0
                ? `${(metrics.totalDuration / 60).toFixed(1)} min`
                : `${metrics.totalChars.toLocaleString()} chars`}
            </div>
            <div className="stat-card-sub">
              <span>{metrics.totalChars.toLocaleString()} ElevenLabs chars generated</span>
            </div>
          </div>
        </section>

        {/* ── Service Breakdown & Daily Trend Section ────────────── */}
        <section className="telemetry-analytics-row">
          {/* Service Allocation Card */}
          <div className="analytics-card service-breakdown-card">
            <div className="analytics-card-header">
              <div className="analytics-card-title">
                <Layers size={15} color="var(--accent)" />
                <span>SERVICE COST ALLOCATION</span>
              </div>
              <span className="analytics-card-subtitle">{timeRange} Day Aggregation</span>
            </div>

            <div className="service-breakdown-list">
              {Object.entries(SERVICE_META).map(([srvKey, srvCfg]) => {
                const srvData = dbSummary?.by_service?.[srvKey] || {
                  cost_usd: 0,
                  call_count: 0,
                  tokens_in: 0,
                  tokens_out: 0,
                  characters: 0,
                  duration_seconds: 0,
                };
                const Icon = srvCfg.icon;
                const cost = srvData.cost_usd || 0;
                const pct = metrics.totalCost > 0 ? ((cost / metrics.totalCost) * 100).toFixed(1) : 0;

                return (
                  <div key={srvKey} className="service-progress-row">
                    <div className="service-progress-head">
                      <div className="service-name-wrap">
                        <Icon size={14} style={{ color: srvCfg.color }} />
                        <span className="service-name">{srvCfg.label}</span>
                        <span className="service-model-tag">{srvCfg.model}</span>
                      </div>
                      <div className="service-cost-tag">
                        <span className="cost-num">{fmtUSD(cost)}</span>
                        <span className="pct-num">({pct}%)</span>
                      </div>
                    </div>

                    <div className="service-bar-track">
                      <div
                        className="service-bar-fill"
                        style={{
                          width: `${Math.max(1.5, Number(pct))}%`,
                          backgroundColor: srvCfg.color,
                          boxShadow: `0 0 10px ${srvCfg.color}66`,
                        }}
                      />
                    </div>

                    <div className="service-meta-footer">
                      <span>{srvData.call_count} calls</span>
                      <span>
                        {srvData.tokens_in + srvData.tokens_out > 0
                          ? `${(srvData.tokens_in + srvData.tokens_out).toLocaleString()} tokens`
                          : srvData.characters > 0
                          ? `${srvData.characters.toLocaleString()} chars`
                          : `${srvData.duration_seconds.toFixed(1)}s audio`}
                      </span>
                      <span className="rate-info">{srvCfg.rateInfo}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Daily Trend Visualizer Card */}
          <div className="analytics-card daily-trend-card">
            <div className="analytics-card-header">
              <div className="analytics-card-title">
                <BarChart3 size={15} color="var(--accent)" />
                <span>DAILY SPEND TEMPORAL PROFILE</span>
              </div>
              <span className="analytics-card-subtitle">Daily Invocations & Costs</span>
            </div>

            <div className="daily-chart-container">
              {dbDaily.length === 0 ? (
                <div className="chart-empty-state">
                  <Database size={24} color="var(--text-muted)" />
                  <p>No historical daily records found in this time range.</p>
                </div>
              ) : (
                <div className="daily-bars-wrapper">
                  {dbDaily.slice(0, 14).reverse().map((day, idx) => {
                    const maxVal = Math.max(...dbDaily.map((d) => d.total || 0), 0.005);
                    const barHeightPct = Math.max(8, ((day.total || 0) / maxVal) * 100);

                    return (
                      <div key={idx} className="daily-bar-column" title={`${day.date}: ${fmtUSD(day.total)} (${day.calls} calls)`}>
                        <div className="daily-bar-tooltip">
                          <span className="tooltip-date">{day.date}</span>
                          <span className="tooltip-cost">{fmtUSD(day.total)}</span>
                          <span className="tooltip-calls">{day.calls} calls</span>
                        </div>
                        <div className="daily-bar-track">
                          <div
                            className="daily-bar-fill"
                            style={{ height: `${barHeightPct}%` }}
                          />
                        </div>
                        <span className="daily-bar-label">{day.date.slice(5)}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* ── Live Trace Stream & Detailed Audit Table ─────────────── */}
        <section className="telemetry-stream-section">
          <div className="stream-section-header">
            <div className="stream-header-left">
              <Terminal size={17} color="var(--accent)" />
              <h2>LIVE TRACE AUDIT STREAM</h2>
              <span className="stream-count-badge">
                {filteredTraces.length} / {combinedTraces.length} TRACES
              </span>
              {telemetryEvents.length > 0 && (
                <button
                  className="clear-stream-btn"
                  onClick={clearTelemetryEvents}
                  title="Clear live in-memory buffer"
                >
                  <Trash2 size={12} />
                  <span>CLEAR LIVE BUFFER</span>
                </button>
              )}
            </div>

            {/* Filter Bar */}
            <div className="stream-filters">
              {/* Search */}
              <div className="search-input-wrap">
                <Search size={13} className="search-icon" />
                <input
                  type="text"
                  placeholder="Search trace, query, UUID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="stream-search-input"
                />
              </div>

              {/* Service Filter */}
              <select
                className="filter-select"
                value={selectedService}
                onChange={(e) => setSelectedService(e.target.value)}
              >
                <option value="all">All Services</option>
                <option value="openai_realtime">OpenAI Realtime Voice</option>
                <option value="elevenlabs_tts">ElevenLabs TTS</option>
                <option value="gpt4o_extraction">GPT-4o Fact Extraction</option>
                <option value="embedding">Vector Embedding</option>
                <option value="whisper">Whisper STT</option>
              </select>

              {/* Operation Filter */}
              <select
                className="filter-select"
                value={selectedOperation}
                onChange={(e) => setSelectedOperation(e.target.value)}
              >
                <option value="all">All Operations</option>
                <option value="voice_turn">voice_turn</option>
                <option value="store_fact_embed">store_fact_embed</option>
                <option value="search_memory_embed">search_memory_embed</option>
                <option value="search_history_embed">search_history_embed</option>
                <option value="extract_facts">extract_facts</option>
                <option value="tts_stream">tts_stream</option>
              </select>
            </div>
          </div>

          {/* Traces Table / Feed */}
          <div className="trace-table-container">
            <div className="trace-table-head">
              <span className="col-status">STATE</span>
              <span className="col-time">TIMESTAMP</span>
              <span className="col-service">SERVICE / MODEL</span>
              <span className="col-op">OPERATION</span>
              <span className="col-metrics">METRICS / TOKENS</span>
              <span className="col-cost">COST (USD)</span>
              <span className="col-actions">ACTION</span>
            </div>

            <div className="trace-table-rows">
              {filteredTraces.length === 0 ? (
                <div className="empty-stream-state">
                  <Activity size={32} color="var(--cyan-dim)" />
                  <p>No traces match your filter.</p>
                  <span>Start speaking in the Cockpit HUD or run memory tools to see live real-time traces stream here.</span>
                </div>
              ) : (
                filteredTraces.map((trace) => {
                  const srvCfg = SERVICE_META[trace.service] || {
                    label: trace.service,
                    model: 'custom',
                    icon: Zap,
                    color: '#64748b',
                  };
                  const Icon = srvCfg.icon;
                  const isLive = trace._isLive;

                  return (
                    <div
                      key={trace.id || Math.random()}
                      className={`trace-row ${isLive ? 'live-incoming-row' : ''} ${
                        inspectedTrace?.id === trace.id ? 'active-inspect' : ''
                      }`}
                      onClick={() => setInspectedTrace(trace)}
                    >
                      {/* Status / Live Badge */}
                      <span className="col-status">
                        {isLive ? (
                          <span className="live-pill-tag">
                            <span className="pulse-dot" />
                            LIVE
                          </span>
                        ) : (
                          <span className="db-pill-tag">
                            <CheckCircle2 size={12} color="var(--text-muted)" />
                            LOGGED
                          </span>
                        )}
                      </span>

                      {/* Timestamp */}
                      <span className="col-time">
                        {new Date(trace.created_at || Date.now()).toLocaleTimeString('en-GB', {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                        })}
                      </span>

                      {/* Service */}
                      <span className="col-service">
                        <div className="service-badge-pill" style={{ borderColor: `${srvCfg.color}44`, backgroundColor: `${srvCfg.color}15` }}>
                          <Icon size={12} style={{ color: srvCfg.color }} />
                          <span style={{ color: srvCfg.color }}>{srvCfg.short || trace.service}</span>
                        </div>
                      </span>

                      {/* Operation */}
                      <span className="col-op">
                        <code className="op-code">{trace.operation}</code>
                      </span>

                      {/* Metrics / Payload snippet */}
                      <span className="col-metrics">
                        {trace.tokens_in + trace.tokens_out > 0 ? (
                          <span className="token-metric">
                            <span className="token-in">{trace.tokens_in} in</span> /{' '}
                            <span className="token-out">{trace.tokens_out} out</span>
                          </span>
                        ) : trace.characters > 0 ? (
                          <span className="char-metric">{trace.characters} chars</span>
                        ) : trace.duration_seconds > 0 ? (
                          <span className="dur-metric">{trace.duration_seconds.toFixed(1)}s audio</span>
                        ) : (
                          <span className="text-muted">1 call</span>
                        )}

                        {trace.metadata?.query && (
                          <span className="trace-query-snippet" title={trace.metadata.query}>
                            &ldquo;{trace.metadata.query.slice(0, 35)}...&rdquo;
                          </span>
                        )}
                        {trace.metadata?.entity_key && (
                          <span className="trace-key-snippet">
                            key: {trace.metadata.entity_key}
                          </span>
                        )}
                      </span>

                      {/* Cost */}
                      <span className="col-cost">
                        <span className="trace-cost-val">{fmtUSD(trace.cost_usd)}</span>
                      </span>

                      {/* Action */}
                      <span className="col-actions">
                        <button
                          className="inspect-btn"
                          onClick={(e) => {
                            e.stopPropagation();
                            setInspectedTrace(trace);
                          }}
                        >
                          INSPECT
                        </button>
                      </span>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </section>
      </div>

      {/* ── Deep Trace Inspector Slide-Over / Modal ────────────────── */}
      {inspectedTrace && (
        <div className="trace-inspector-overlay" onClick={() => setInspectedTrace(null)}>
          <div className="trace-inspector-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <div className="drawer-title-group">
                <Terminal size={18} color="var(--accent)" />
                <div>
                  <h3>TRACE DEEP INSPECTION</h3>
                  <p className="drawer-id">UUID: {inspectedTrace.id}</p>
                </div>
              </div>
              <button className="drawer-close-btn" onClick={() => setInspectedTrace(null)}>
                &times;
              </button>
            </div>

            <div className="drawer-body">
              {/* Top Summary Box */}
              <div className="inspector-card">
                <h4>FINANCIAL & EXECUTION AUDIT</h4>
                <div className="inspector-grid">
                  <div>
                    <label>SERVICE</label>
                    <span>{inspectedTrace.service}</span>
                  </div>
                  <div>
                    <label>OPERATION</label>
                    <span className="text-cyan">{inspectedTrace.operation}</span>
                  </div>
                  <div>
                    <label>CALCULATED COST (USD)</label>
                    <span className="text-amber font-mono font-bold">
                      {fmtUSD(inspectedTrace.cost_usd)}
                    </span>
                  </div>
                  <div>
                    <label>TIMESTAMP (ISO)</label>
                    <span className="font-mono text-sm">{inspectedTrace.created_at}</span>
                  </div>
                  <div>
                    <label>INPUT TOKENS / DURATION</label>
                    <span>
                      {inspectedTrace.tokens_in > 0
                        ? `${inspectedTrace.tokens_in} tokens`
                        : inspectedTrace.duration_seconds > 0
                        ? `${inspectedTrace.duration_seconds.toFixed(2)} seconds`
                        : `${inspectedTrace.characters} characters`}
                    </span>
                  </div>
                  <div>
                    <label>OUTPUT TOKENS</label>
                    <span>{inspectedTrace.tokens_out || 0} tokens</span>
                  </div>
                </div>
              </div>

              {/* Metadata JSON Viewer */}
              <div className="inspector-card">
                <h4>PAYLOAD & ENGINE METADATA</h4>
                <pre className="json-viewer">
                  {JSON.stringify(inspectedTrace.metadata || {}, null, 2)}
                </pre>
              </div>

              {/* Raw Trace Object */}
              <div className="inspector-card">
                <h4>RAW EVENT SCHEME</h4>
                <pre className="json-viewer">
                  {JSON.stringify(inspectedTrace, null, 2)}
                </pre>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
