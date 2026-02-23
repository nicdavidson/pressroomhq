import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export default function StoryWorkbench({ orgId, signals }) {
  const [stories, setStories] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [digging, setDigging] = useState(null) // signal id currently digging

  const headers = { 'Content-Type': 'application/json', ...(orgId ? { 'X-Org-Id': String(orgId) } : {}) }

  // ── Fetch stories list ──
  const fetchStories = useCallback(async () => {
    try {
      const res = await fetch(`${API}/stories`, { headers })
      const data = await res.json()
      setStories(Array.isArray(data) ? data : [])
    } catch { /* ignore */ }
    setLoading(false)
  }, [orgId])

  // ── Fetch single story with signals ──
  const fetchStory = useCallback(async (id) => {
    try {
      const res = await fetch(`${API}/stories/${id}`, { headers })
      const data = await res.json()
      if (!data.error) setSelected(data)
    } catch { /* ignore */ }
  }, [orgId])

  useEffect(() => { fetchStories() }, [fetchStories])
  useEffect(() => { if (selectedId) fetchStory(selectedId) }, [selectedId, fetchStory])

  // ── CRUD ──
  const createStory = async () => {
    const res = await fetch(`${API}/stories`, {
      method: 'POST', headers, body: JSON.stringify({ title: 'New Story' })
    })
    const data = await res.json()
    if (data.id) {
      await fetchStories()
      setSelectedId(data.id)
    }
  }

  const updateField = async (field, value) => {
    if (!selectedId) return
    setSelected(prev => ({ ...prev, [field]: value }))
    await fetch(`${API}/stories/${selectedId}`, {
      method: 'PUT', headers, body: JSON.stringify({ [field]: value })
    })
    fetchStories() // refresh list for title changes
  }

  const deleteStory = async (id) => {
    await fetch(`${API}/stories/${id}`, { method: 'DELETE', headers })
    if (selectedId === id) { setSelectedId(null); setSelected(null) }
    fetchStories()
  }

  // ── Signal management ──
  const addSignal = async (signalId) => {
    if (!selectedId) return
    await fetch(`${API}/stories/${selectedId}/signals`, {
      method: 'POST', headers, body: JSON.stringify({ signal_id: signalId })
    })
    fetchStory(selectedId)
  }

  const removeSignal = async (storySignalId) => {
    if (!selectedId) return
    await fetch(`${API}/stories/${selectedId}/signals/${storySignalId}`, {
      method: 'DELETE', headers
    })
    fetchStory(selectedId)
  }

  const updateSignalNotes = async (storySignalId, notes) => {
    if (!selectedId) return
    await fetch(`${API}/stories/${selectedId}/signals/${storySignalId}`, {
      method: 'PUT', headers, body: JSON.stringify({ editor_notes: notes })
    })
  }

  const digDeeper = async (signalId) => {
    setDigging(signalId)
    try {
      await fetch(`${API}/signals/${signalId}/dig-deeper`, { method: 'POST', headers })
      fetchStory(selectedId)
    } catch { /* ignore */ }
    setDigging(null)
  }

  // ── Generate ──
  const generateFromStory = async () => {
    if (!selectedId) return
    setGenerating(true)
    try {
      await fetch(`${API}/stories/${selectedId}/generate`, {
        method: 'POST', headers, body: JSON.stringify({ channels: [] })
      })
      fetchStory(selectedId)
      fetchStories()
    } catch { /* ignore */ }
    setGenerating(false)
  }

  // Signals not yet in the story
  const storySignalIds = (selected?.signals || []).map(ss => ss.signal?.id || ss.signal_id)
  const availableSignals = (signals || []).filter(s => !storySignalIds.includes(s.id))

  const statusColor = { draft: 'var(--text-dim)', generating: 'var(--amber)', complete: 'var(--green)' }

  return (
    <div className="story-workbench">
      {/* LEFT: Story list */}
      <div className="story-list-panel">
        <div className="story-list-header">
          <span className="section-label" style={{ margin: 0 }}>Stories</span>
          <button className="btn btn-approve btn-sm" onClick={createStory}>+ New</button>
        </div>
        {loading ? (
          <p style={{ color: 'var(--text-dim)', padding: 12, fontSize: 11 }}>Loading...</p>
        ) : stories.length === 0 ? (
          <p style={{ color: 'var(--text-dim)', padding: 12, fontSize: 11 }}>No stories yet. Create one to start curating.</p>
        ) : (
          stories.map(s => (
            <div
              key={s.id}
              className={`story-list-item ${selectedId === s.id ? 'active' : ''}`}
              onClick={() => setSelectedId(s.id)}
            >
              <div className="story-list-title">{s.title || 'Untitled'}</div>
              <div className="story-list-meta">
                <span style={{ color: statusColor[s.status] || 'var(--text-dim)' }}>{s.status}</span>
                <span>{s.signal_count || 0} signals</span>
              </div>
            </div>
          ))
        )}
      </div>

      {/* RIGHT: Story editor */}
      <div className="story-editor-panel">
        {!selected ? (
          <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)' }}>
            Select a story or create a new one
          </div>
        ) : (
          <>
            <div className="story-editor-header">
              <input
                className="story-title-input"
                value={selected.title || ''}
                onChange={e => setSelected(prev => ({ ...prev, title: e.target.value }))}
                onBlur={e => updateField('title', e.target.value)}
                placeholder="Story title..."
              />
              <button className="asset-delete" onClick={() => deleteStory(selected.id)} title="Delete story">&times;</button>
            </div>

            <div className="story-field">
              <label className="story-field-label">Angle</label>
              <input
                className="setting-input"
                value={selected.angle || ''}
                onChange={e => setSelected(prev => ({ ...prev, angle: e.target.value }))}
                onBlur={e => updateField('angle', e.target.value)}
                placeholder="What's the editorial angle?"
              />
            </div>

            <div className="story-field">
              <label className="story-field-label">Editorial Notes</label>
              <textarea
                className="setting-input story-notes-input"
                value={selected.editorial_notes || ''}
                onChange={e => setSelected(prev => ({ ...prev, editorial_notes: e.target.value }))}
                onBlur={e => updateField('editorial_notes', e.target.value)}
                placeholder="Context, direction, things to emphasize..."
                rows={3}
              />
            </div>

            {/* Curated signals */}
            <div className="story-section">
              <div className="section-label">Curated Signals ({selected.signals?.length || 0})</div>
              {(selected.signals || []).length === 0 ? (
                <p style={{ color: 'var(--text-dim)', fontSize: 11 }}>Add signals from the wire below</p>
              ) : (
                (selected.signals || []).map(ss => {
                  const sig = ss.signal || {}
                  return (
                    <div key={ss.id} className="story-signal-card">
                      <div className="story-signal-header">
                        <span className="story-signal-type">{sig.type}</span>
                        <span className="story-signal-title">{sig.title}</span>
                        <div className="story-signal-actions">
                          <button
                            className="btn btn-sm"
                            onClick={() => digDeeper(sig.id)}
                            disabled={digging === sig.id}
                            title="Dig deeper — fetch source and enrich"
                          >
                            {digging === sig.id ? 'Digging...' : 'Dig Deeper'}
                          </button>
                          <button className="btn btn-sm btn-spike" onClick={() => removeSignal(ss.id)} title="Remove from story">&times;</button>
                        </div>
                      </div>
                      {sig.body && (
                        <div className="story-signal-body">
                          {sig.body.slice(0, 200)}{sig.body.length > 200 ? '...' : ''}
                        </div>
                      )}
                      <textarea
                        className="story-signal-notes"
                        placeholder="Editor notes for this signal..."
                        defaultValue={ss.editor_notes || ''}
                        onBlur={e => updateSignalNotes(ss.id, e.target.value)}
                        rows={2}
                      />
                    </div>
                  )
                })
              )}
            </div>

            {/* Add from wire */}
            {availableSignals.length > 0 && (
              <div className="story-section">
                <div className="section-label">Add from Wire</div>
                <div className="story-wire-list">
                  {availableSignals.slice(0, 15).map(s => (
                    <div key={s.id} className="story-wire-item">
                      <span className="story-signal-type">{s.type}</span>
                      <span className="story-wire-title">{s.title}</span>
                      <button className="btn btn-sm btn-approve" onClick={() => addSignal(s.id)}>+</button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Generate */}
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--border)' }}>
              <button
                className={`btn btn-approve ${generating ? 'loading' : ''}`}
                onClick={generateFromStory}
                disabled={generating || (selected.signals || []).length === 0}
                style={{ width: '100%', padding: '10px 0', fontSize: 13 }}
              >
                {generating ? 'Generating...' : `Generate from Story (${selected.signals?.length || 0} signals)`}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
