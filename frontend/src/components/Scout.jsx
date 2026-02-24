import { useState, useEffect, useCallback, useMemo } from 'react'

const API = '/api'

function orgHeaders(orgId) {
  const h = { 'Content-Type': 'application/json' }
  if (orgId) h['X-Org-Id'] = String(orgId)
  return h
}

const SOURCE_TYPES = [
  {
    key: 'scout_github_repos',
    label: 'GitHub Repos',
    placeholder: 'owner/repo',
    signalTypes: ['github_release', 'github_commit'],
    signalLabel: 'GITHUB',
  },
  {
    key: 'scout_hn_keywords',
    label: 'Hacker News Keywords',
    placeholder: 'keyword or phrase',
    signalTypes: ['hackernews'],
    signalLabel: 'HN',
  },
  {
    key: 'scout_subreddits',
    label: 'Reddit',
    placeholder: 'subreddit (no r/)',
    signalTypes: ['reddit'],
    signalLabel: 'REDDIT',
  },
  {
    key: 'scout_rss_feeds',
    label: 'RSS Feeds',
    placeholder: 'https://example.com/feed.xml',
    signalTypes: ['rss'],
    signalLabel: 'RSS',
  },
]

const SIGNAL_TAG_MAP = {
  github_release: 'RELEASE', github_commit: 'COMMITS', hackernews: 'HN',
  reddit: 'REDDIT', rss: 'RSS', trend: 'TREND',
  support: 'SUPPORT', performance: 'PERF',
}

export default function Scout({ onLog, orgId }) {
  const [settings, setSettings] = useState({})
  const [edits, setEdits] = useState({})
  const [saving, setSaving] = useState(false)
  const [signals, setSignals] = useState([])
  const [scouting, setScouting] = useState(false)
  const [collapsed, setCollapsed] = useState({})
  const [signalStats, setSignalStats] = useState([])

  const load = useCallback(async () => {
    if (!orgId) return
    try {
      const [setRes, sigRes, statsRes] = await Promise.all([
        fetch(`${API}/settings`, { headers: orgHeaders(orgId) }),
        fetch(`${API}/signals?limit=50`, { headers: orgHeaders(orgId) }),
        fetch(`${API}/signals/stats/performance`, { headers: orgHeaders(orgId) }),
      ])
      if (setRes.ok) setSettings(await setRes.json())
      if (sigRes.ok) setSignals(await sigRes.json())
      if (statsRes.ok) setSignalStats(await statsRes.json())
    } catch (e) {
      onLog?.('Failed to load scout data', 'error')
    }
  }, [orgId, onLog])

  useEffect(() => { load() }, [load])

  // Reset edits when org changes
  useEffect(() => { setEdits({}) }, [orgId])

  const edit = (key, val) => setEdits(prev => ({ ...prev, [key]: val }))
  const getVal = (key) => edits[key] ?? settings[key]?.value ?? ''
  const isDirty = Object.keys(edits).length > 0

  // Tag helpers
  const getTags = (key) => {
    try { return JSON.parse(getVal(key) || '[]') }
    catch { return [] }
  }

  const addTag = (key, currentTags, newTag) => {
    if (!newTag.trim() || currentTags.includes(newTag.trim())) return
    edit(key, JSON.stringify([...currentTags, newTag.trim()]))
  }

  const removeTag = (key, currentTags, idx) => {
    edit(key, JSON.stringify(currentTags.filter((_, i) => i !== idx)))
  }

  // Save sources
  const save = async () => {
    if (!isDirty) return
    setSaving(true)
    onLog?.('Saving scout sources...', 'action')
    try {
      await fetch(`${API}/settings`, {
        method: 'PUT',
        headers: orgHeaders(orgId),
        body: JSON.stringify({ settings: edits }),
      })
      setEdits({})
      onLog?.('Scout sources saved', 'success')
      await load()
    } catch (e) {
      onLog?.(`Save failed: ${e.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  // Run scout
  const runScout = async () => {
    if (scouting) return
    setScouting(true)
    onLog?.('SCOUT \u2014 scanning GitHub, HN, Reddit, RSS...', 'action')
    try {
      const res = await fetch(`${API}/pipeline/scout`, {
        method: 'POST',
        headers: orgHeaders(orgId),
      })
      const data = await res.json()
      if (data.error) {
        onLog?.(`SCOUT FAILED \u2014 ${data.error}`, 'error')
        return
      }
      const raw = data.signals_raw || 0
      const kept = data.signals_saved || data.signals_relevant || 0
      onLog?.(`SCOUT COMPLETE \u2014 ${kept} signals kept${raw > kept ? ` (${raw - kept} filtered)` : ''}`, 'success')
      // Reload signals
      const sigRes = await fetch(`${API}/signals?limit=50`, { headers: orgHeaders(orgId) })
      if (sigRes.ok) setSignals(await sigRes.json())
    } catch (e) {
      onLog?.(`SCOUT ERROR \u2014 ${e.message}`, 'error')
    } finally {
      setScouting(false)
    }
  }

  // Group signals by source type
  const groupedSignals = useMemo(() => {
    const knownTypes = SOURCE_TYPES.flatMap(st => st.signalTypes)
    const groups = []
    for (const st of SOURCE_TYPES) {
      const matching = signals.filter(s => st.signalTypes.includes(s.type))
      if (matching.length > 0) {
        groups.push({ key: st.key, label: st.signalLabel, count: matching.length, signals: matching })
      }
    }
    const other = signals.filter(s => !knownTypes.includes(s.type))
    if (other.length > 0) {
      groups.push({ key: '_other', label: 'OTHER', count: other.length, signals: other })
    }
    return groups
  }, [signals])

  const toggleGroup = (key) => setCollapsed(prev => ({ ...prev, [key]: !prev[key] }))

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">Scout</h2>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className={`btn btn-run ${scouting ? 'loading' : ''}`}
            onClick={runScout}
            disabled={scouting}
          >
            {scouting ? 'Scouting...' : 'Run Scout'}
          </button>
          <button
            className={`btn btn-approve ${saving ? 'loading' : ''}`}
            onClick={save}
            disabled={!isDirty || saving}
          >
            {saving ? 'Saving...' : 'Save Sources'}
          </button>
        </div>
      </div>

      {/* SCOUT SOURCES */}
      {SOURCE_TYPES.map(st => {
        const tags = getTags(st.key)
        return (
          <div key={st.key} className="settings-section">
            <div className="section-label">{st.label} <span className="section-count">{tags.length}</span></div>
            <div className="tag-list">
              {tags.map((t, i) => (
                <span key={i} className="tag tag-amber" onClick={() => removeTag(st.key, tags, i)}>
                  {t} <span className="tag-x">&times;</span>
                </span>
              ))}
              <TagInput onAdd={(v) => addTag(st.key, tags, v)} placeholder={`add ${st.placeholder}...`} />
            </div>
          </div>
        )
      })}

      {/* SIGNAL RESULTS */}
      <div className="settings-section">
        <div className="section-label">
          Signals <span className="section-count">{signals.length}</span>
        </div>

        {signals.length === 0 && !scouting && (
          <div className="scout-empty">
            No signals yet. Hit <strong>Run Scout</strong> to scan your sources.
          </div>
        )}

        {scouting && signals.length === 0 && (
          <div className="scout-empty">
            <div className="loader-bar" />
            <p style={{ marginTop: 12 }}>Working the wire...</p>
          </div>
        )}

        {groupedSignals.map(group => (
          <div key={group.key} className="scout-group">
            <div className="scout-group-header" onClick={() => toggleGroup(group.key)}>
              <div className="scout-group-label">
                <span className="scout-group-toggle">{collapsed[group.key] ? '\u25B6' : '\u25BC'}</span>
                {group.label}
              </div>
              <span className="scout-group-count">{group.count}</span>
            </div>
            {!collapsed[group.key] && (
              <div className="scout-group-signals">
                {group.signals.map(s => (
                  <div key={s.id} className="signal-item">
                    <span className="signal-tag">{SIGNAL_TAG_MAP[s.type] || s.type}</span>
                    <div className="signal-title">
                      {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title}</a> : s.title}
                    </div>
                    <div className="signal-source">{s.source}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* SIGNAL PERFORMANCE */}
      {signalStats.some(s => s.times_used > 0) && (
        <div className="settings-section">
          <div className="section-label">
            Signal Performance <span className="section-count">wire dashboard</span>
          </div>

          <table className="perf-table">
            <thead>
              <tr>
                <th>TYPE</th>
                <th>SIGNAL</th>
                <th>USED</th>
                <th>SPIKED</th>
                <th>RATE</th>
              </tr>
            </thead>
            <tbody>
              {signalStats.filter(s => s.times_used > 0).slice(0, 20).map(s => {
                const spikeRate = s.times_used > 0 ? (s.times_spiked / s.times_used) : 0
                const isHot = spikeRate > 0.5 && s.times_used >= 2
                return (
                  <tr key={s.id} className={isHot ? 'perf-row-hot' : ''}>
                    <td className="perf-type">{SIGNAL_TAG_MAP[s.type] || s.type}</td>
                    <td className="perf-title">{s.title?.slice(0, 50)}{s.title?.length > 50 ? '...' : ''}</td>
                    <td className="perf-num">{s.times_used}</td>
                    <td className="perf-num perf-spike">{s.times_spiked}</td>
                    <td className={`perf-num ${isHot ? 'perf-rate-bad' : 'perf-rate-ok'}`}>
                      {(spikeRate * 100).toFixed(0)}%
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>

          {signalStats.filter(s => s.times_used >= 2 && (s.times_spiked / s.times_used) > 0.5).length > 0 && (
            <div className="perf-warning">
              ADVISORY — signals marked in red have high spike rates. Consider removing from sources.
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TagInput({ onAdd, placeholder }) {
  const [val, setVal] = useState('')
  const submit = () => {
    if (val.trim()) {
      onAdd(val)
      setVal('')
    }
  }
  return (
    <input
      className="tag-input"
      value={val}
      onChange={e => setVal(e.target.value)}
      onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); submit() } }}
      onBlur={submit}
      placeholder={placeholder}
    />
  )
}
