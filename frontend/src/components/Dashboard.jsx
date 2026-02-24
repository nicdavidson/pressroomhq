import { useState, useEffect } from 'react'

const API = '/api'

function StatCard({ label, value, sub }) {
  return (
    <div className="dash-stat">
      <div className="dash-stat-value">{value}</div>
      <div className="dash-stat-label">{label}</div>
      {sub && <div className="dash-stat-sub">{sub}</div>}
    </div>
  )
}

function SignalRow({ signal }) {
  return (
    <div className="dash-signal-row">
      <span className="dash-signal-type">{signal.type}</span>
      <span className="dash-signal-title">{signal.title?.slice(0, 80)}</span>
      <span className="dash-signal-count">
        {signal.times_used > 0 && <span style={{ color: 'var(--green)' }}>{signal.times_used} used</span>}
        {signal.times_spiked > 0 && <span style={{ color: 'var(--red, #c44)' }}>{signal.times_spiked} spiked</span>}
      </span>
    </div>
  )
}

export default function Dashboard({ orgId }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const headers = { 'Content-Type': 'application/json', ...(orgId ? { 'X-Org-Id': String(orgId) } : {}) }

  useEffect(() => {
    setLoading(true)
    fetch(`${API}/analytics/dashboard`, { headers })
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [orgId])

  if (loading) {
    return (
      <div className="settings-page">
        <div className="settings-header">
          <h2 className="settings-title">Dashboard</h2>
        </div>
        <p style={{ color: 'var(--text-dim)', padding: 20 }}>Loading analytics...</p>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="settings-page">
        <div className="settings-header">
          <h2 className="settings-title">Dashboard</h2>
        </div>
        <p style={{ color: 'var(--text-dim)', padding: 20 }}>No data available yet. Run the pipeline to generate analytics.</p>
      </div>
    )
  }

  const { signals, content, pipeline, approval_rate, top_signals, top_spiked } = data
  const statusMap = content?.by_status || {}
  const channelMap = content?.by_channel || {}
  const typeMap = signals?.by_type || {}
  const dayMap = signals?.by_day || {}

  // Last activity times
  const lastScout = pipeline?.last_scout_run ? new Date(pipeline.last_scout_run).toLocaleString() : 'Never'
  const lastGen = pipeline?.last_generate_run ? new Date(pipeline.last_generate_run).toLocaleString() : 'Never'

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">Dashboard</h2>
        <p className="settings-description">Signal pipeline and content performance at a glance.</p>
      </div>

      {/* Summary cards */}
      <div className="dash-stats-row">
        <StatCard label="Signals" value={signals?.total || 0} sub={`${Object.keys(typeMap).length} sources`} />
        <StatCard label="Content" value={content?.total || 0} sub={`${Object.keys(channelMap).length} channels`} />
        <StatCard label="Queued" value={statusMap.queued || 0} />
        <StatCard label="Approved" value={statusMap.approved || 0} />
        <StatCard label="Published" value={statusMap.published || 0} />
        <StatCard label="Approval Rate" value={`${approval_rate}%`} sub={`${statusMap.spiked || 0} spiked`} />
      </div>

      {/* Two column layout */}
      <div className="dash-grid">
        {/* Signals by source */}
        <div className="dash-section">
          <div className="section-label">Signals by Source</div>
          <div className="dash-bar-list">
            {Object.entries(typeMap).map(([type, count]) => (
              <div key={type} className="dash-bar-row">
                <span className="dash-bar-label">{type}</span>
                <div className="dash-bar-track">
                  <div
                    className="dash-bar-fill"
                    style={{ width: `${Math.min(100, (count / (signals?.total || 1)) * 100)}%` }}
                  />
                </div>
                <span className="dash-bar-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Content by channel */}
        <div className="dash-section">
          <div className="section-label">Content by Channel</div>
          <div className="dash-bar-list">
            {Object.entries(channelMap).map(([ch, count]) => (
              <div key={ch} className="dash-bar-row">
                <span className="dash-bar-label">{ch.replace('_', ' ')}</span>
                <div className="dash-bar-track">
                  <div
                    className="dash-bar-fill"
                    style={{ width: `${Math.min(100, (count / (content?.total || 1)) * 100)}%` }}
                  />
                </div>
                <span className="dash-bar-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Signal volume by day */}
        <div className="dash-section">
          <div className="section-label">Signal Volume (7 Days)</div>
          <div className="dash-day-chart">
            {Object.entries(dayMap).length === 0 ? (
              <p style={{ color: 'var(--text-dim)', fontSize: 11 }}>No signals in the last 7 days</p>
            ) : (
              <div className="dash-day-bars">
                {Object.entries(dayMap).map(([day, count]) => {
                  const max = Math.max(...Object.values(dayMap))
                  return (
                    <div key={day} className="dash-day-col">
                      <div className="dash-day-bar" style={{ height: `${(count / (max || 1)) * 100}%` }} />
                      <div className="dash-day-label">{day.slice(5)}</div>
                      <div className="dash-day-count">{count}</div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {/* Pipeline timing */}
        <div className="dash-section">
          <div className="section-label">Pipeline</div>
          <div className="dash-meta-list">
            <div className="dash-meta-row">
              <span className="dash-meta-label">Last Scout</span>
              <span className="dash-meta-value">{lastScout}</span>
            </div>
            <div className="dash-meta-row">
              <span className="dash-meta-label">Last Generate</span>
              <span className="dash-meta-value">{lastGen}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Top signals */}
      {top_signals?.length > 0 && (
        <div className="dash-section" style={{ marginTop: 16 }}>
          <div className="section-label">Top Producing Signals</div>
          {top_signals.map(s => <SignalRow key={s.id} signal={s} />)}
        </div>
      )}

      {top_spiked?.length > 0 && (
        <div className="dash-section" style={{ marginTop: 16 }}>
          <div className="section-label">Most Spiked Signals</div>
          {top_spiked.map(s => <SignalRow key={s.id} signal={s} />)}
        </div>
      )}
    </div>
  )
}
