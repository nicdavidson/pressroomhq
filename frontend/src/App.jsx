import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function formatDate() {
  const d = new Date()
  const months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
  return `${months[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}`
}

function formatTime() {
  const d = new Date()
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
}

function channelLabel(ch) {
  const labels = {
    linkedin: 'LINKEDIN',
    x_thread: 'X THREAD',
    facebook: 'FACEBOOK',
    blog: 'BLOG DRAFT',
    release_email: 'RELEASE EMAIL',
    newsletter: 'NEWSLETTER',
    yt_script: 'YT SCRIPT',
  }
  return labels[ch] || ch.toUpperCase()
}

function signalTag(type) {
  const tags = {
    github_release: 'RELEASE',
    github_commit: 'COMMITS',
    hackernews: 'HN',
    reddit: 'REDDIT',
    rss: 'RSS',
    trend: 'TREND',
    support: 'SUPPORT',
    performance: 'PERF',
  }
  return tags[type] || type.toUpperCase()
}

export default function App() {
  const [signals, setSignals] = useState([])
  const [queue, setQueue] = useState([])
  const [allContent, setAllContent] = useState([])
  const [status, setStatus] = useState('idle')
  const [time, setTime] = useState(formatTime())
  const [expanded, setExpanded] = useState(null)

  // Clock
  useEffect(() => {
    const t = setInterval(() => setTime(formatTime()), 10000)
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
      setSignals(await sigRes.json())
      setQueue(await queueRes.json())
      setAllContent(await contentRes.json())
    } catch (e) {
      console.error('Refresh failed:', e)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 15000)
    return () => clearInterval(interval)
  }, [refresh])

  // Actions
  const runScout = async () => {
    setStatus('scouting')
    try {
      const res = await fetch(`${API}/pipeline/scout`, { method: 'POST' })
      const data = await res.json()
      setStatus(`scouted ${data.signals_found} signals`)
      refresh()
    } catch (e) {
      setStatus('scout failed')
    }
  }

  const runGenerate = async () => {
    setStatus('generating')
    try {
      const res = await fetch(`${API}/pipeline/generate`, { method: 'POST' })
      const data = await res.json()
      setStatus(`generated ${data.content_generated} pieces`)
      refresh()
    } catch (e) {
      setStatus('generate failed')
    }
  }

  const runFull = async () => {
    setStatus('full run')
    try {
      const res = await fetch(`${API}/pipeline/run`, { method: 'POST' })
      const data = await res.json()
      setStatus(`done — ${data.signals} signals, ${data.content?.length || 0} pieces`)
      refresh()
    } catch (e) {
      setStatus('run failed')
    }
  }

  const contentAction = async (id, action) => {
    try {
      await fetch(`${API}/content/${id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
      refresh()
    } catch (e) {
      console.error('Action failed:', e)
    }
  }

  const queuedCount = queue.length
  const approvedCount = allContent.filter(c => c.status === 'approved').length

  return (
    <>
      {/* HEADER */}
      <div className="header">
        <div>
          <div className="header-title">Pressroom HQ</div>
          <div className="header-edition">Daily Edition</div>
        </div>
        <div>
          <div className="header-date">{formatDate()}</div>
          <div className="header-date">{time}</div>
        </div>
      </div>

      {/* MAIN LAYOUT */}
      <div className="pressroom">
        {/* WIRE PANEL */}
        <div className="wire-panel">
          <div className="panel-header">
            <span>Wire In</span>
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

        {/* DESK */}
        <div className="desk">
          {/* Toolbar */}
          <div className="toolbar">
            <button className="btn btn-run" onClick={runScout}>Scout</button>
            <button className="btn btn-run" onClick={runGenerate}>Generate</button>
            <button className="btn btn-run" onClick={runFull}>Full Run</button>
            <span style={{ marginLeft: 'auto', color: 'var(--text-dim)', fontSize: 12, alignSelf: 'center' }}>
              {queuedCount} queued &middot; {approvedCount} approved
            </span>
          </div>

          {/* Queue */}
          {queue.length === 0 && signals.length === 0 && (
            <div className="empty-state">
              <h2>The Wire Opens at Dawn</h2>
              <p>Hit "Full Run" to scout signals and generate content.</p>
            </div>
          )}

          {queue.length === 0 && signals.length > 0 && (
            <div className="empty-state">
              <h2>Signals On the Wire</h2>
              <p>{signals.length} signals waiting. Hit "Generate" to write the stories.</p>
            </div>
          )}

          <div className="content-grid">
            {(queue.length > 0 ? queue : allContent).map(c => (
              <div key={c.id} className={`content-card ${c.status}`}>
                <div className="card-channel">{channelLabel(c.channel)}</div>
                <div className="card-headline">{c.headline}</div>
                <div
                  className={`card-body ${expanded === c.id ? 'expanded' : ''}`}
                  onClick={() => setExpanded(expanded === c.id ? null : c.id)}
                >
                  {c.body}
                </div>
                <div className="card-actions">
                  {c.status === 'queued' && (
                    <>
                      <button className="btn btn-approve" onClick={() => contentAction(c.id, 'approve')}>
                        Approve
                      </button>
                      <button className="btn btn-spike" onClick={() => contentAction(c.id, 'spike')}>
                        Spike
                      </button>
                    </>
                  )}
                  {c.status === 'approved' && (
                    <span style={{ color: 'var(--green)', fontSize: 11 }}>✓ APPROVED</span>
                  )}
                  {c.status === 'spiked' && (
                    <span style={{ color: 'var(--red)', fontSize: 11 }}>✗ SPIKED</span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* STATUS BAR */}
      <div className="status-bar">
        <span>
          <span className={`status-indicator ${status === 'idle' ? 'online' : 'busy'}`}></span>
          {status === 'idle' ? 'WIRE ONLINE' : status.toUpperCase()}
        </span>
        <span>PRESSROOM v0.1.0</span>
      </div>
    </>
  )
}
