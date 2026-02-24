import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import Settings from './components/Settings'
import Voice from './components/Voice'
import Scout from './components/Scout'
import Import from './components/Import'
import Onboard from './components/Onboard'
import Connections from './components/Connections'
import Audit from './components/Audit'
import Assets from './components/Assets'
import StoryWorkbench from './components/StoryWorkbench'
import Team from './components/Team'

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

// Build headers with org context
function orgHeaders(orgId) {
  const h = { 'Content-Type': 'application/json' }
  if (orgId) h['X-Org-Id'] = String(orgId)
  return h
}

function orgFetch(url, orgId, opts = {}) {
  const headers = { ...orgHeaders(orgId), ...(opts.headers || {}) }
  return fetch(url, { ...opts, headers })
}

export default function App() {
  const [signals, setSignals] = useState([])
  const [queue, setQueue] = useState([])
  const [allContent, setAllContent] = useState([])
  const [time, setTime] = useState(formatTime())
  const [expanded, setExpanded] = useState(null)
  const [view, setView] = useState('desk')
  // Rewrite modal state
  const [rewriteTarget, setRewriteTarget] = useState(null) // content item being rewritten
  const [rewriteFeedback, setRewriteFeedback] = useState('')

  // Multi-tenant state
  const [orgs, setOrgs] = useState([])
  const [currentOrg, setCurrentOrg] = useState(null) // { id, name, domain }
  const [sidebarOpen, setSidebarOpen] = useState(true)

  // Wire panel state
  const [wireCollapsed, setWireCollapsed] = useState({})

  // Loading states per action
  const [loading, setLoading] = useState({})
  // Activity log
  const [logs, setLogs] = useState([{ ts: ts(), msg: 'WIRE ONLINE — Pressroom v0.1.0', type: 'system' }])
  const logRef = useRef(null)

  const log = useCallback((msg, type = 'info') => {
    setLogs(prev => [...prev.slice(-200), { ts: ts(), msg, type }])
  }, [])

  const orgId = currentOrg?.id || null

  // Group signals by source type for the Wire panel
  const WIRE_GROUPS = [
    { types: ['github_release', 'github_commit'], label: 'GITHUB' },
    { types: ['hackernews'], label: 'HN' },
    { types: ['reddit'], label: 'REDDIT' },
    { types: ['rss'], label: 'RSS' },
  ]

  const wireGroups = useMemo(() => {
    const knownTypes = WIRE_GROUPS.flatMap(g => g.types)
    const groups = []
    for (const g of WIRE_GROUPS) {
      const items = signals.filter(s => g.types.includes(s.type))
      if (items.length > 0) groups.push({ ...g, signals: items })
    }
    const other = signals.filter(s => !knownTypes.includes(s.type))
    if (other.length > 0) groups.push({ label: 'OTHER', types: [], signals: other })
    return groups
  }, [signals])

  const toggleWireGroup = (label) => setWireCollapsed(prev => ({ ...prev, [label]: !prev[label] }))

  const deleteSignal = async (id) => {
    try {
      await orgFetch(`${API}/signals/${id}`, orgId, { method: 'DELETE' })
      setSignals(prev => prev.filter(s => s.id !== id))
    } catch (e) {
      log(`DELETE SIGNAL FAILED — ${e.message}`, 'error')
    }
  }

  // Load organizations on mount
  useEffect(() => {
    fetch(`${API}/orgs`).then(r => r.json()).then(data => {
      if (Array.isArray(data) && data.length > 0) {
        setOrgs(data)
        // Auto-select saved or first org
        const saved = localStorage.getItem('pressroom_org_id')
        const found = saved ? data.find(o => o.id === Number(saved)) : null
        setCurrentOrg(found || data[0])
      } else {
        setView('onboard')
      }
    }).catch(() => setView('onboard'))
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

  // Save selected org to localStorage
  useEffect(() => {
    if (currentOrg) localStorage.setItem('pressroom_org_id', String(currentOrg.id))
  }, [currentOrg])

  // Load data (org-scoped)
  const refresh = useCallback(async () => {
    if (!orgId) return
    try {
      const [sigRes, queueRes, contentRes] = await Promise.all([
        orgFetch(`${API}/signals?limit=30`, orgId),
        orgFetch(`${API}/content/queue`, orgId),
        orgFetch(`${API}/content?limit=50`, orgId),
      ])
      if (!sigRes.ok || !queueRes.ok || !contentRes.ok) return
      setSignals(await sigRes.json())
      setQueue(await queueRes.json())
      setAllContent(await contentRes.json())
    } catch (e) {
      // silent on refresh
    }
  }, [orgId])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 8000)
    return () => clearInterval(interval)
  }, [refresh])

  // Clear data when switching orgs
  useEffect(() => {
    setSignals([])
    setQueue([])
    setAllContent([])
    setExpanded(null)
  }, [orgId])

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

  // Switch org
  const switchOrg = (org) => {
    setCurrentOrg(org)
    log(`SWITCHED — now working on ${org.name}`, 'system')
    if (view === 'onboard') setView('desk')
  }

  // Delete org
  const deleteOrg = async (org, e) => {
    e.stopPropagation()
    if (!confirm(`Delete "${org.name}" and ALL its data?\n\nSignals, content, settings — everything goes. This cannot be undone.`)) return
    try {
      await fetch(`${API}/orgs/${org.id}`, { method: 'DELETE' })
      const remaining = orgs.filter(o => o.id !== org.id)
      setOrgs(remaining)
      if (currentOrg?.id === org.id) {
        setCurrentOrg(remaining[0] || null)
        if (remaining.length === 0) setView('onboard')
      }
      log(`DELETED — ${org.name} removed`, 'warn')
    } catch (e) {
      log(`DELETE FAILED — ${e.message}`, 'error')
    }
  }

  // Onboard complete callback
  const onOnboardComplete = (newOrg) => {
    if (newOrg?.id) {
      setOrgs(prev => {
        const exists = prev.some(o => o.id === newOrg.id)
        return exists ? prev : [newOrg, ...prev]
      })
      setCurrentOrg(newOrg)
    }
    fetch(`${API}/orgs`).then(r => r.json()).then(data => {
      if (Array.isArray(data)) setOrgs(data)
    }).catch(() => {})
    setView('desk')
    log(`ONBOARDED — ${newOrg?.name || 'Company'} is ready`, 'success')
  }

  // Actions
  const runScout = withLoading('scout', async () => {
    log('SCOUT — scanning GitHub, HN, Reddit, RSS...', 'action')
    try {
      const res = await orgFetch(`${API}/pipeline/scout`, orgId, { method: 'POST' })
      const data = await res.json()
      if (data.error) {
        log(`SCOUT FAILED — ${data.error}`, 'error')
        return
      }
      log(`SCOUT COMPLETE — ${data.signals_saved || 0} signals (${data.signals_raw || 0} raw, ${data.signals_raw - data.signals_relevant || 0} filtered)`, 'success')
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
      const res = await orgFetch(`${API}/pipeline/generate`, orgId, { method: 'POST' })
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
      const res = await orgFetch(`${API}/pipeline/run`, orgId, { method: 'POST' })
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
      const res = await orgFetch(`${API}/publish`, orgId, { method: 'POST' })
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
      await orgFetch(`${API}/content/${id}/action`, orgId, {
        method: 'POST',
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

  const openRewriteModal = (item) => {
    setRewriteTarget(item)
    setRewriteFeedback('')
  }

  const submitRewrite = async () => {
    if (!rewriteTarget) return
    const id = rewriteTarget.id
    const label = `[${channelLabel(rewriteTarget.channel)}] ${rewriteTarget.headline?.slice(0, 60)}`
    setRewriteTarget(null)
    setLoading(prev => ({ ...prev, [`card-${id}`]: true }))
    log(`REWRITE — ${label}${rewriteFeedback ? ` (feedback: ${rewriteFeedback.slice(0, 60)})` : ''}`, 'action')
    try {
      const res = await orgFetch(`${API}/pipeline/regenerate/${id}`, orgId, {
        method: 'POST',
        body: JSON.stringify({ feedback: rewriteFeedback }),
      })
      const data = await res.json()
      if (data.error) {
        log(`REWRITE FAILED — ${data.error}`, 'error')
      } else {
        log(`REWRITE DONE — ${data.headline?.slice(0, 80)}`, 'success')
        refresh()
      }
    } catch (e) {
      log(`REWRITE ERROR — ${e.message}`, 'error')
    } finally {
      setLoading(prev => ({ ...prev, [`card-${id}`]: false }))
    }
  }

  const togglePriority = async (signalId) => {
    try {
      const res = await orgFetch(`${API}/signals/${signalId}/prioritize`, orgId, { method: 'PATCH' })
      const data = await res.json()
      if (data.error) return
      setSignals(prev => prev.map(s => s.id === signalId ? { ...s, prioritized: data.prioritized } : s))
    } catch (e) {
      log(`PRIORITIZE FAILED — ${e.message}`, 'error')
    }
  }

  // Build a signal lookup map for source attribution on content cards
  const signalMap = useMemo(() => {
    const m = {}
    signals.forEach(s => { m[s.id] = s })
    return m
  }, [signals])

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
            <div className="header-edition">
              {currentOrg ? currentOrg.name : 'Daily Edition'}
            </div>
          </div>
          <nav className="nav-tabs">
            <button className={`nav-tab ${view === 'desk' ? 'active' : ''}`} onClick={() => setView('desk')}>Desk</button>
            <button className={`nav-tab ${view === 'scout' ? 'active' : ''}`} onClick={() => setView('scout')}>Scout</button>
            <button className={`nav-tab ${view === 'voice' ? 'active' : ''}`} onClick={() => setView('voice')}>Voice</button>
            <button className={`nav-tab ${view === 'import' ? 'active' : ''}`} onClick={() => setView('import')}>Import</button>
            <button className={`nav-tab ${view === 'connections' ? 'active' : ''}`} onClick={() => setView('connections')}>Connect</button>
            <button className={`nav-tab ${view === 'assets' ? 'active' : ''}`} onClick={() => setView('assets')}>Assets</button>
            <button className={`nav-tab ${view === 'team' ? 'active' : ''}`} onClick={() => setView('team')}>Team</button>
            <button className={`nav-tab ${view === 'stories' ? 'active' : ''}`} onClick={() => setView('stories')}>Stories</button>
            <button className={`nav-tab ${view === 'audit' ? 'active' : ''}`} onClick={() => setView('audit')}>Audit</button>
            <button className={`nav-tab ${view === 'settings' ? 'active' : ''}`} onClick={() => setView('settings')}>Account</button>
            <button className={`nav-tab ${view === 'onboard' ? 'active' : ''}`} onClick={() => setView('onboard')}>+ Company</button>
          </nav>
        </div>
        <div>
          <div className="header-date">{formatDate()}</div>
          <div className="header-date">{time}</div>
        </div>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* ORG SIDEBAR */}
        <div className={`org-sidebar ${sidebarOpen ? 'open' : 'collapsed'}`}>
          <div className="org-sidebar-header" onClick={() => setSidebarOpen(!sidebarOpen)}>
            {sidebarOpen ? 'Companies' : ''}
            <span className="org-sidebar-toggle">{sidebarOpen ? '\u25C0' : '\u25B6'}</span>
          </div>
          {sidebarOpen && (
            <div className="org-list">
              {orgs.map(org => (
                <div
                  key={org.id}
                  className={`org-item ${currentOrg?.id === org.id ? 'active' : ''}`}
                  onClick={() => switchOrg(org)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                    <div>
                      <div className="org-item-name">{org.name}</div>
                      <div className="org-item-domain">{org.domain}</div>
                    </div>
                    <button
                      className="org-delete-btn"
                      onClick={(e) => deleteOrg(org, e)}
                      title={`Delete ${org.name}`}
                    >&times;</button>
                  </div>
                </div>
              ))}
              {orgs.length === 0 && (
                <div className="org-item" style={{ color: 'var(--text-dim)', cursor: 'default' }}>
                  No companies yet
                </div>
              )}
              <div
                className="org-item org-add"
                onClick={() => setView('onboard')}
              >
                + Add Company
              </div>
            </div>
          )}
        </div>

        {/* MAIN CONTENT */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {(view === 'settings' || view === 'voice' || view === 'scout' || view === 'import' || view === 'onboard' || view === 'connections' || view === 'audit' || view === 'assets' || view === 'team') && (
            <div className="pressroom" style={{ gridTemplateColumns: '1fr' }}>
              <div className="desk-area" style={{ gridTemplateRows: '1fr 220px' }}>
                {view === 'settings' && <Settings onLog={log} orgId={orgId} />}
                {view === 'voice' && <Voice onLog={log} orgId={orgId} />}
                {view === 'scout' && <Scout onLog={log} orgId={orgId} />}
                {view === 'import' && <Import onLog={log} orgId={orgId} />}
                {view === 'onboard' && <Onboard onLog={log} onComplete={onOnboardComplete} />}
                {view === 'connections' && <Connections onLog={log} orgId={orgId} />}
                {view === 'audit' && <Audit onLog={log} orgId={orgId} />}
                {view === 'assets' && <Assets orgId={orgId} />}
                {view === 'team' && <Team orgId={orgId} />}
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

          {view === 'stories' && (
            <div className="pressroom" style={{ gridTemplateColumns: '1fr' }}>
              <StoryWorkbench orgId={orgId} signals={signals} />
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
              {wireGroups.map(group => (
                <div key={group.label} className="wire-group">
                  <div className="wire-group-header" onClick={() => toggleWireGroup(group.label)}>
                    <span className="wire-group-label">
                      <span className="wire-group-toggle">{wireCollapsed[group.label] ? '\u25B6' : '\u25BC'}</span>
                      {group.label}
                    </span>
                    <span className="wire-group-count">{group.signals.length}</span>
                  </div>
                  {!wireCollapsed[group.label] && group.signals.map(s => (
                    <div key={s.id} className={`signal-item signal-item-grouped ${s.prioritized ? 'signal-prioritized' : ''}`}>
                      <button
                        className={`signal-star ${s.prioritized ? 'active' : ''}`}
                        onClick={() => togglePriority(s.id)}
                        title={s.prioritized ? 'Remove priority' : 'Prioritize for content gen'}
                      >{s.prioritized ? '\u2605' : '\u2606'}</button>
                      <div className="signal-item-main">
                        <span className="signal-tag">{signalTag(s.type)}</span>
                        <div className="signal-title">
                          {s.url
                            ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a>
                            : s.title}
                        </div>
                        <div className="signal-source">{s.source}</div>
                      </div>
                      <button className="signal-remove" onClick={() => deleteSignal(s.id)} title="Remove signal">&times;</button>
                    </div>
                  ))}
                </div>
              ))}
            </div>

            {/* DESK + LOG */}
            <div className="desk-area">
              <div className="desk">
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

                {!currentOrg && (
                  <div className="empty-state">
                    <h2>No Company Selected</h2>
                    <p>Add a company using "+ Company" to get started.</p>
                  </div>
                )}

                {currentOrg && queue.length === 0 && signals.length === 0 && !isAnyLoading && (
                  <div className="empty-state">
                    <h2>The Wire Opens at Dawn</h2>
                    <p>Hit "Full Run" to scout signals and generate content for {currentOrg.name}.</p>
                  </div>
                )}

                {currentOrg && queue.length === 0 && signals.length > 0 && !isAnyLoading && (
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
                      {/* Source attribution tags */}
                      {c.source_signal_ids && c.source_signal_ids.trim() && (
                        <div className="card-sources">
                          <span className="card-sources-label">SRC</span>
                          {c.source_signal_ids.split(',').map(sid => sid.trim()).filter(Boolean).map(sid => {
                            const sig = signalMap[Number(sid)]
                            if (!sig) return null
                            return (
                              <span key={sid} className="card-source-tag">
                                [{signalTag(sig.type)}] {sig.title?.slice(0, 40)}{sig.title?.length > 40 ? '...' : ''}
                              </span>
                            )
                          })}
                        </div>
                      )}
                      <div className="card-actions">
                        {c.status === 'queued' && !loading[`card-${c.id}`] && (
                          <>
                            <button className="btn btn-approve" onClick={() => contentAction(c.id, 'approve')}>
                              Approve
                            </button>
                            <button className="btn btn-run" onClick={() => openRewriteModal(c)}>
                              Rewrite
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
        </div>
      </div>

      {/* REWRITE MODAL */}
      {rewriteTarget && (
        <div className="modal-overlay" onClick={() => setRewriteTarget(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <span>Rewrite: {channelLabel(rewriteTarget.channel)}</span>
              <button className="modal-close" onClick={() => setRewriteTarget(null)}>&times;</button>
            </div>
            <div className="modal-headline">{rewriteTarget.headline}</div>
            <div className="modal-body-preview">{rewriteTarget.body?.slice(0, 300)}...</div>
            <label className="modal-label">Editor Instructions (optional)</label>
            <textarea
              className="setting-input modal-textarea"
              value={rewriteFeedback}
              onChange={e => setRewriteFeedback(e.target.value)}
              placeholder="e.g. make it punchier, focus more on the security angle, lead with the DF integration..."
              rows={4}
              autoFocus
              onKeyDown={e => { if (e.key === 'Enter' && e.metaKey) submitRewrite() }}
            />
            <div className="modal-actions">
              <button className="btn btn-run" onClick={submitRewrite}>
                Rewrite
              </button>
              <button className="btn btn-spike" onClick={() => { setRewriteFeedback(''); submitRewrite() }}>
                Rewrite (No Instructions)
              </button>
              <button className="btn" style={{ color: 'var(--text-dim)', borderColor: 'var(--border)' }} onClick={() => setRewriteTarget(null)}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* STATUS BAR */}
      <div className="status-bar">
        <span>
          <span className={`status-indicator ${isAnyLoading ? 'busy' : 'online'}`}></span>
          {isAnyLoading ? Object.entries(loading).filter(([,v]) => v).map(([k]) => k.toUpperCase()).join(' + ') : 'WIRE ONLINE'}
        </span>
        <span>
          {currentOrg ? `${currentOrg.name} | ` : ''}PRESSROOM v0.1.0
        </span>
      </div>
    </>
  )
}
