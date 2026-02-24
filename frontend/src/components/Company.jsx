import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function orgHeaders(orgId) {
  const h = { 'Content-Type': 'application/json' }
  if (orgId) h['X-Org-Id'] = String(orgId)
  return h
}

function TagEditor({ tags, onUpdate, placeholder }) {
  const [input, setInput] = useState('')
  const add = () => {
    const v = input.trim()
    if (v && !tags.includes(v)) {
      onUpdate([...tags, v])
      setInput('')
    }
  }
  const remove = (i) => onUpdate(tags.filter((_, idx) => idx !== i))
  return (
    <div className="tag-list">
      {tags.map((t, i) => (
        <span key={i} className="tag tag-amber" onClick={() => remove(i)}>
          {t} <span className="tag-x">&times;</span>
        </span>
      ))}
      <input
        className="tag-input"
        value={input}
        onChange={e => setInput(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add() } }}
        onBlur={add}
        placeholder={placeholder}
      />
    </div>
  )
}

export default function Company({ orgId, onLog }) {
  const [settings, setSettings] = useState({})
  const [name, setName] = useState('')
  const [domain, setDomain] = useState('')
  const [industry, setIndustry] = useState('')
  const [topics, setTopics] = useState([])
  const [competitors, setCompetitors] = useState([])
  const [socials, setSocials] = useState({ linkedin: '', x: '', github: '', facebook: '', instagram: '', youtube: '' })
  const [ghOrgs, setGhOrgs] = useState([])
  const [saving, setSaving] = useState(null) // which section is saving
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState(null)

  const headers = orgHeaders(orgId)

  const getVal = (key) => {
    const s = settings[key]
    return s?.value ?? s ?? ''
  }

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API}/settings`, { headers: orgHeaders(orgId) })
      if (!res.ok) return
      const data = await res.json()
      setSettings(data)

      setName(data.onboard_company_name?.value || '')
      setDomain(data.onboard_domain?.value || '')
      setIndustry(data.onboard_industry?.value || '')

      try { setTopics(JSON.parse(data.onboard_topics?.value || '[]')) } catch { setTopics([]) }
      try { setCompetitors(JSON.parse(data.onboard_competitors?.value || '[]')) } catch { setCompetitors([]) }
      try { setGhOrgs(JSON.parse(data.scout_github_orgs?.value || '[]')) } catch { setGhOrgs([]) }

      try {
        const sp = JSON.parse(data.social_profiles?.value || '{}')
        setSocials({
          linkedin: sp.linkedin || '',
          x: sp.x || sp.twitter || '',
          github: sp.github || '',
          facebook: sp.facebook || '',
          instagram: sp.instagram || '',
          youtube: sp.youtube || '',
        })
      } catch { /* keep defaults */ }
    } catch { /* ignore */ }
  }, [orgId])

  useEffect(() => { load() }, [load])

  const saveSection = async (section, payload) => {
    setSaving(section)
    try {
      await fetch(`${API}/settings`, {
        method: 'PUT', headers,
        body: JSON.stringify({ settings: payload }),
      })
      onLog?.(`Company ${section} saved`, 'success')
      await load()
    } catch (e) {
      onLog?.(`Save failed: ${e.message}`, 'error')
    }
    setSaving(null)
  }

  const saveIdentity = () => saveSection('identity', {
    onboard_company_name: name,
    onboard_domain: domain,
    onboard_industry: industry,
  })

  const saveTopics = () => saveSection('topics', {
    onboard_topics: JSON.stringify(topics),
    onboard_competitors: JSON.stringify(competitors),
  })

  const saveSocials = () => saveSection('socials', {
    social_profiles: JSON.stringify(socials),
  })

  const saveOrgs = () => saveSection('orgs', {
    scout_github_orgs: JSON.stringify(ghOrgs),
  })

  const syncRepos = async () => {
    // Save orgs first, then sync
    await saveOrgs()
    setSyncing(true)
    setSyncResult(null)
    onLog?.('GITHUB SYNC — discovering repos from configured orgs...', 'action')
    try {
      const res = await fetch(`${API}/assets/github/sync-orgs`, {
        method: 'POST', headers,
      })
      const data = await res.json()
      if (data.error) {
        setSyncResult(data.error)
        onLog?.(`GITHUB SYNC FAILED — ${data.error}`, 'error')
      } else {
        const parts = Object.entries(data.orgs || {}).map(([org, info]) =>
          info.error ? `${org}: error` : `${org}: ${info.found} found, ${info.added} new`
        )
        const msg = `Synced ${data.synced} new repos. ${parts.join('. ')}`
        setSyncResult(msg)
        onLog?.(`GITHUB SYNC — ${msg}`, 'success')
      }
    } catch (e) {
      setSyncResult(`Error: ${e.message}`)
      onLog?.(`GITHUB SYNC ERROR — ${e.message}`, 'error')
    }
    setSyncing(false)
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">Company</h2>
        <p className="settings-description">Company identity, social profiles, and GitHub organizations.</p>
      </div>

      {/* IDENTITY */}
      <div className="settings-section">
        <div className="section-label">Identity</div>
        <div className="company-field-grid">
          <div className="company-field">
            <label className="company-field-label">Company Name</label>
            <input className="setting-input" value={name} onChange={e => setName(e.target.value)} placeholder="Acme Corp" />
          </div>
          <div className="company-field">
            <label className="company-field-label">Domain</label>
            <input className="setting-input" value={domain} onChange={e => setDomain(e.target.value)} placeholder="acme.com" />
          </div>
          <div className="company-field">
            <label className="company-field-label">Industry</label>
            <input className="setting-input" value={industry} onChange={e => setIndustry(e.target.value)} placeholder="Enterprise Software" />
          </div>
        </div>
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <button className={`btn btn-approve ${saving === 'identity' ? 'loading' : ''}`} onClick={saveIdentity} disabled={!!saving}>
            {saving === 'identity' ? 'Saving...' : 'Save Identity'}
          </button>
        </div>
      </div>

      {/* TOPICS & COMPETITORS */}
      <div className="settings-section">
        <div className="section-label">Topics <span className="section-count">{topics.length}</span></div>
        <TagEditor tags={topics} onUpdate={setTopics} placeholder="add topic..." />

        <div className="section-label" style={{ marginTop: 16 }}>Competitors <span className="section-count">{competitors.length}</span></div>
        <TagEditor tags={competitors} onUpdate={setCompetitors} placeholder="add competitor..." />

        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <button className={`btn btn-approve ${saving === 'topics' ? 'loading' : ''}`} onClick={saveTopics} disabled={!!saving}>
            {saving === 'topics' ? 'Saving...' : 'Save Topics'}
          </button>
        </div>
      </div>

      {/* SOCIAL PROFILES */}
      <div className="settings-section">
        <div className="section-label">Social Profiles</div>
        <div className="company-field-grid">
          {[
            { key: 'linkedin', label: 'LinkedIn', ph: 'https://linkedin.com/company/...' },
            { key: 'x', label: 'Twitter / X', ph: 'https://x.com/...' },
            { key: 'github', label: 'GitHub', ph: 'https://github.com/...' },
            { key: 'facebook', label: 'Facebook', ph: 'https://facebook.com/...' },
            { key: 'instagram', label: 'Instagram', ph: 'https://instagram.com/...' },
            { key: 'youtube', label: 'YouTube', ph: 'https://youtube.com/@...' },
          ].map(s => (
            <div key={s.key} className="company-field">
              <label className="company-field-label">{s.label}</label>
              <input
                className="setting-input"
                value={socials[s.key]}
                onChange={e => setSocials(prev => ({ ...prev, [s.key]: e.target.value }))}
                placeholder={s.ph}
              />
            </div>
          ))}
        </div>
        <div style={{ marginTop: 12, textAlign: 'right' }}>
          <button className={`btn btn-approve ${saving === 'socials' ? 'loading' : ''}`} onClick={saveSocials} disabled={!!saving}>
            {saving === 'socials' ? 'Saving...' : 'Save Socials'}
          </button>
        </div>
      </div>

      {/* GITHUB ORGANIZATIONS */}
      <div className="settings-section">
        <div className="section-label">GitHub Organizations <span className="section-count">{ghOrgs.length}</span></div>
        <p style={{ color: 'var(--text-dim)', fontSize: 12, margin: '0 0 8px' }}>
          Add org names to discover all repos. Synced repos appear in your asset map and are monitored by the scout.
        </p>
        <TagEditor tags={ghOrgs} onUpdate={setGhOrgs} placeholder="add org name (e.g. treehouse)..." />

        <div style={{ marginTop: 12, display: 'flex', gap: 8, alignItems: 'center' }}>
          <button className={`btn btn-approve ${saving === 'orgs' ? 'loading' : ''}`} onClick={saveOrgs} disabled={!!saving}>
            {saving === 'orgs' ? 'Saving...' : 'Save Orgs'}
          </button>
          <button
            className={`btn btn-run ${syncing ? 'loading' : ''}`}
            onClick={syncRepos}
            disabled={syncing || ghOrgs.length === 0}
          >
            {syncing ? 'Syncing...' : 'Sync Repos'}
          </button>
        </div>

        {syncResult && (
          <p style={{ color: syncResult.startsWith('Error') ? 'var(--red, #c44)' : 'var(--green)', fontSize: 12, marginTop: 8 }}>
            {syncResult}
          </p>
        )}
      </div>
    </div>
  )
}
