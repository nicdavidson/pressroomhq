import { useState, useEffect, useCallback, useRef } from 'react'
import Settings from './components/Settings'
import Voice from './components/Voice'
import Import from './components/Import'

const API = '/api'

function formatDate() {
  const d = new Date()
  const months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`
}

function formatTime() {
  const d = new Date()
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

function ts() {
  return new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

function channelLabel(ch) {
  const labels = {
    linkedin: 'LINKEDIN', x_thread: 'X THREAD', facebook: 'FACEBOOK',
    blog: 'BLOG DRAFT', release_email: 'RELEASE EMAIL',
    newsletter: 'NEWSLETTER', yt_script: 'YT SCRIPT',
  }
  return labels[ch] || ch.toUpperCase()
}

function signalTag(type) {
  const tags = {
    github_release: 'RELEASE', github_commit: 'COMMITS', hackernews: 'HN',
    reddit: 'REDDIT', rss: 'RSS', trend: 'TREND',
    support: 'SUPPORT', performance: 'PERF',
  }
  return tags[type] || type.toUpperCase()
}

export default function App() {
  const [signals, setSignals] = useState([])
  const [queue, setQueue] = useState([])
  const [allContent, setAllContent] = useState([])
  const [time, setTime] = useState(formatTime())
  const [expanded, setExpanded] = useState(null)
  const [view, setView] = useState('desk') // 'desk' | 'voice' | 'import' | 'settings'

  // Loading states per action
  const [loading, setLoading] = useState({})
  // Activity log
  const [logs, setLogs] = useState([{ ts: ts(), msg: 'WIRE ONLINE — Pressroom v0.1.0', type: 'system' }])
  const logRef = useRef(null)

  const log = useCallback((msg, type = 'info') => {
    setLogs(prev => [...prev.slice(-200), { ts: ts(), msg, type }])
  }, [])

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [logs])

  // Clock
  useEffect(() => {
    const t = setInterval(() => setTime(formatTime()), 1000)
    return () => clearInterval(t)
  }, [])

  // Load data
  const refresh = useCallback(async () => {
    try {
      const [sigRes, queueRes, contentRes] = await Promise.all([
        fetch(`${API}/signals?limit=30`),
        fetch(`${API}/content/queue`),
        fetch(`${API}/content?limit=50`),
      ])
      if (!sigRes.ok || !queueRes.ok || !contentRes.ok) return
      setSignals(await sigRes.json())
      setQueue(await queueRes.json())
      setAllContent(await contentRes.json())
    } catch (e) {
      // silent on refresh
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 8000)
    return () => clearInterval(interval)
  }, [refresh])

  // Wrap action in loading state
  const withLoading = (key, fn) => async () => {
    if (loading[key]) return
    setLoading(prev => ({ ...prev, [key]: true }))
    try {
      await fn()
    } finally {
      setLoading(prev => ({ ...prev, [key]: false }))
    }
  }

  // Actions
  const runScout = withLoading('scout', async () => {
    log('SCOUT — scanning GitHub, HN, Reddit, RSS...', 'action')
    try {
      const res = await fetch(`${API}/pipeline/scout`, { method: 'POST' })
      const data = await res.json()
      if (data.error) {
        log(`SCOUT FAILED — ${data.error}`, 'error')
        return
      }
      log(`SCOUT COMPLETE — ${data.signals_found} signals pulled from the wire`, 'success')
      if (data.signals) {
        data.signals.forEach(s => log(`  [${s.type}] ${s.source}: ${s.title}`, 'detail'))
      }
      refresh()
    } catch (e) {
      log(`SCOUT ERROR — ${e.message}`, 'error')
    }
  })

  const runGenerate = withLoading('generate', async () => {
    log('GENERATE — Claude is writing the stories...', 'action')
    try {
      const res = await fetch(`${API}/pipeline/generate`, { method: 'POST' })
      const data = await res.json()
      if (data.error) {
        log(`GENERATE BLOCKED — ${data.error}`, 'error')
        return
      }
      log(`BRIEF — angle: ${data.brief?.angle || 'n/a'}`, 'detail')
      log(`GENERATE COMPLETE — ${data.content_generated} pieces written`, 'success')
      if (data.items) {
        data.items.forEach(i => log(`  [${i.channel}] ${i.headline}`, 'detail'))
      }
      refresh()
    } catch (e) {
      log(`GENERATE ERROR — ${e.message}`, 'error')
    }
  })

  const runFull = withLoading('full', async () => {
    log('FULL RUN — scout + brief + generate + humanize', 'action')
    log('  Scanning sources...', 'detail')
    try {
      const res = await fetch(`${API}/pipeline/run`, { method: 'POST' })
      const data = await res.json()
      if (data.status === 'no_signals') {
        log('WIRE QUIET — no signals found. Try widening search.', 'warn')
        return
      }
      log(`  Scout: ${data.signals} signals`, 'detail')
      log(`  Brief angle: ${data.brief?.angle || 'n/a'}`, 'detail')
      log(`FULL RUN COMPLETE — ${data.content?.length || 0} pieces on the desk`, 'success')
      if (data.content) {
        data.content.forEach(c => log(`  [${c.channel}] ${c.headline}`, 'detail'))
      }
      refresh()
    } catch (e) {
      log(`FULL RUN ERROR — ${e.message}`, 'error')
    }
  })

  const runPublish = withLoading('publish', async () => {
    log('PUBLISH — sending approved content to destinations...', 'action')
    try {
      const res = await fetch(`${API}/publish`, { method: 'POST' })
      const data = await res.json()
      log(`PUBLISH COMPLETE — ${data.published} sent, ${data.errors} errors`, data.errors > 0 ? 'warn' : 'success')
      if (data.results) {
        data.results.forEach(r => {
          if (r.error) log(`  [${r.channel}] FAILED: ${r.error}`, 'error')
          else log(`  [${r.channel}] sent`, 'detail')
        })
      }
      refresh()
    } catch (e) {
      log(`PUBLISH ERROR — ${e.message}`, 'error')
    }
  })

  const contentAction = async (id, action) => {
    const item = [...queue, ...allContent].find(c => c.id === id)
    const label = item ? `[${channelLabel(item.channel)}] ${item.headline?.slice(0, 60)}` : `#${id}`
    setLoading(prev => ({ ...prev, [`card-${id}`]: true }))
    try {
      await fetch(`${API}/content/${id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
      log(`${action.toUpperCase()} — ${label}`, action === 'approve' ? 'success' : 'warn')
      refresh()
    } catch (e) {
      log(`${action.toUpperCase()} FAILED — ${e.message}`, 'error')
    } finally {
      setLoading(prev => ({ ...prev, [`card-${id}`]: false }))
    }
  }

  const queuedCount = queue.length
  const approvedCount = allContent.filter(c => c.status === 'approved').length
  const publishedCount = allContent.filter(c => c.status === 'published').length
  const isAnyLoading = Object.values(loading).some(Boolean)

  return (
    <>
      {/* HEADER */}
      <div className="header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <div>
            <div className="header-title">Pressroom HQ</div>
            <div className="header-edition">Daily Edition</div>
          </div>
          <nav className="nav-tabs">
            <button className={`nav-tab ${view === 'desk' ? 'active' : ''}`} onClick={() => setView('desk')}>Desk</button>
            <button className={`nav-tab ${view === 'voice' ? 'active' : ''}`} onClick={() => setView('voice')}>Voice</button>
            <button className={`nav-tab ${view === 'import' ? 'active' : ''}`} onClick={() => setView('import')}>Import</button>
            <button className={`nav-tab ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>Config</button>
          </nav>
        </div>
        <div>
          <div className="header-date">{formatDate()}</div>
          <div className="header-date">{time}</div>
        </div>
      </div>

      {/* MAIN LAYOUT */}
      {(view === 'settings' || view === 'voice' || view === 'import') && (
        <div className="pressroom" style={{ gridTemplateColumns: '1fr' }}>
          <div className="desk-area" style={{ gridTemplateRows: '1fr 220px' }}>
            {view === 'settings' && <Settings onLog={log} />}
            {view === 'voice' && <Voice onLog={log} />}
            {view === 'import' && <Import onLog={log} />}
            {/* ACTIVITY LOG */}
            <div className="log-panel">
              <div className="panel-header">
                <span>Activity Log</span>
                <span>{isAnyLoading && <span className="spinner" />}</span>
              </div>
              <div className="log-feed" ref={logRef}>
                {logs.map((l, i) => (
                  <div key={i} className={`log-line log-${l.type}`}>
                    <span className="log-ts">{l.ts}</span> {l.msg}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {view === 'desk' && <div className="pressroom">
        {/* WIRE PANEL */}
        <div className="wire-panel">
          <div className="panel-header">
            <span>Wire In {loading.scout && <span className="spinner" />}</span>
            <span>{signals.length} signals</span>
          </div>
          {signals.length === 0 && (
            <div style={{ color: 'var(--text-dim)', padding: '20px 0', fontSize: 12 }}>
              Wire is quiet. Run the scout.
            </div>
          )}
          {signals.map(s => (
            <div key={s.id} className="signal-item">
              <span className="signal-tag">{signalTag(s.type)}</span>
              <div className="signal-title">{s.title}</div>
              <div className="signal-source">{s.source}</div>
            </div>
          ))}
        </div>

        {/* DESK + LOG */}
        <div className="desk-area">
          {/* DESK */}
          <div className="desk">
            {/* Toolbar */}
            <div className="toolbar">
              <button className={`btn btn-run ${loading.scout ? 'loading' : ''}`} onClick={runScout} disabled={loading.scout}>
                {loading.scout ? 'Scouting...' : 'Scout'}
              </button>
              <button className={`btn btn-run ${loading.generate ? 'loading' : ''}`} onClick={runGenerate} disabled={loading.generate}>
                {loading.generate ? 'Writing...' : 'Generate'}
              </button>
              <button className={`btn btn-run ${loading.full ? 'loading' : ''}`} onClick={runFull} disabled={loading.full}>
                {loading.full ? 'Running...' : 'Full Run'}
              </button>
              <button className={`btn btn-approve ${loading.publish ? 'loading' : ''}`} onClick={runPublish} disabled={loading.publish || approvedCount === 0}>
                {loading.publish ? 'Sending...' : 'Publish'}
              </button>
              <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 12, alignSelf: 'center' }}>
                {queuedCount} queued &middot; {approvedCount} approved &middot; {publishedCount} published
              </span>
            </div>

            {/* Queue */}
            {queue.length === 0 && signals.length === 0 && !isAnyLoading && (
              <div className="empty-state">
                <h2>The Wire Opens at Dawn</h2>
                <p>Hit "Full Run" to scout signals and generate content.</p>
              </div>
            )}

            {queue.length === 0 && signals.length > 0 && !isAnyLoading && (
              <div className="empty-state">
                <h2>Signals On the Wire</h2>
                <p>{signals.length} signals waiting. Hit "Generate" to write the stories.</p>
              </div>
            )}

            {isAnyLoading && queue.length === 0 && (
              <div className="empty-state">
                <div className="loader-bar" />
                <p style={{ marginTop: 16 }}>Working the wire...</p>
              </div>
            )}

            <div className="content-grid">
              {(queue.length > 0 ? queue : allContent).map(c => (
                <div key={c.id} className={`content-card ${c.status} ${loading[`card-${c.id}`] ? 'card-loading' : ''}`}>
                  <div className="card-channel">{channelLabel(c.channel)}</div>
                  <div className="card-headline">{c.headline}</div>
                  <div
                    className={`card-body ${expanded === c.id ? 'expanded' : ''}`}
                    onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                  >
                    {c.body}
                  </div>
                  <div className="card-actions">
                    {c.status === 'queued' && !loading[`card-${c.id}`] && (
                      <>
                        <button className="btn btn-approve" onClick={() => contentAction(c.id, 'approve')}>
                          Approve
                        </button>
                        <button className="btn btn-spike" onClick={() => contentAction(c.id, 'spike')}>
                          Spike
                        </button>
                      </>
                    )}
                    {c.status === 'queued' && loading[`card-${c.id}`] && (
                      <span className="card-status-text processing">Processing...</span>
                    )}
                    {c.status === 'approved' && (
                      <span className="card-status-text approved-text">APPROVED — awaiting publish</span>
                    )}
                    {c.status === 'published' && (
                      <span className="card-status-text published-text">PUBLISHED</span>
                    )}
                    {c.status === 'spiked' && (
                      <span className="card-status-text spiked-text">SPIKED</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ACTIVITY LOG */}
          <div className="log-panel">
            <div className="panel-header">
              <span>Activity Log</span>
              <span>{isAnyLoading && <span className="spinner" />}</span>
            </div>
            <div className="log-feed" ref={logRef}>
              {logs.map((l, i) => (
                <div key={i} className={`log-line log-${l.type}`}>
                  <span className="log-ts">{l.ts}</span> {l.msg}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>}

      {/* STATUS BAR */}
      <div className="status-bar">
        <span>
          <span className={`status-indicator ${isAnyLoading ? 'busy' : 'online'}`}></span>
          {isAnyLoading ? Object.entries(loading).filter(([,v]) => v).map(([k]) => k.toUpperCase()).join(' + ') : 'WIRE ONLINE'}
        </span>
        <span>PRESSROOM v0.1.0</span>
      </div>
    </>
  )
}
