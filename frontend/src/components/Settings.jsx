import { useState, useEffect, useCallback } from 'react'

const API = '/api'

// Account settings don't send X-Org-Id — they're shared across all companies
function accountHeaders() {
  return { 'Content-Type': 'application/json' }
}

function orgHeaders(orgId) {
  const h = { 'Content-Type': 'application/json' }
  if (orgId) h['X-Org-Id'] = String(orgId)
  return h
}

function StatusDot({ connected, configured }) {
  if (!configured) return <span className="dot dot-off" title="Not configured" />
  if (connected) return <span className="dot dot-on" title="Connected" />
  return <span className="dot dot-warn" title="Configured but not connected" />
}

export default function Settings({ onLog, orgId }) {
  const [settings, setSettings] = useState({})
  const [status, setStatus] = useState({})
  const [dfServices, setDfServices] = useState(null)
  const [saving, setSaving] = useState(false)
  const [edits, setEdits] = useState({})
  const [checking, setChecking] = useState(false)

  const load = useCallback(async () => {
    try {
      const [setRes, statRes] = await Promise.all([
        fetch(`${API}/settings`, { headers: orgHeaders(orgId) }),
        fetch(`${API}/settings/status`, { headers: orgHeaders(orgId) }),
      ])
      setSettings(await setRes.json())
      setStatus(await statRes.json())
    } catch (e) {
      onLog?.('Failed to load settings', 'error')
    }
  }, [onLog, orgId])

  const loadDfServices = useCallback(async () => {
    try {
      const res = await fetch(`${API}/settings/df-services`, { headers: orgHeaders(orgId) })
      setDfServices(await res.json())
    } catch (e) {
      setDfServices({ available: false })
    }
  }, [orgId])

  useEffect(() => { load(); loadDfServices() }, [load, loadDfServices])
  useEffect(() => { setEdits({}) }, [orgId])

  const edit = (key, val) => setEdits(prev => ({ ...prev, [key]: val }))

  const save = async () => {
    if (Object.keys(edits).length === 0) return
    setSaving(true)
    onLog?.('Saving account settings...', 'action')
    try {
      // Account keys go without org header, ensuring they save to org_id=NULL
      await fetch(`${API}/settings`, {
        method: 'PUT',
        headers: accountHeaders(),
        body: JSON.stringify({ settings: edits }),
      })
      setEdits({})
      onLog?.(`Account settings saved: ${Object.keys(edits).join(', ')}`, 'success')
      await load()
      await loadDfServices()
    } catch (e) {
      onLog?.(`Save failed: ${e.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  const checkConnections = async () => {
    setChecking(true)
    onLog?.('Checking connections...', 'action')
    try {
      const [statRes, dfRes] = await Promise.all([
        fetch(`${API}/settings/status`, { headers: orgHeaders(orgId) }),
        fetch(`${API}/settings/df-services`, { headers: orgHeaders(orgId) }),
      ])
      const data = await statRes.json()
      const dfData = await dfRes.json()
      setStatus(data)
      setDfServices(dfData)

      if (data.github?.connected) onLog?.(`GitHub: connected as ${data.github.user}`, 'success')
      else if (data.github?.configured) onLog?.(`GitHub: ${data.github.error || 'not connected'}`, 'error')
      if (data.dreamfactory?.connected) onLog?.(`DreamFactory: connected at ${data.dreamfactory.url}`, 'success')
      else if (data.dreamfactory?.configured) onLog?.(`DreamFactory: ${data.dreamfactory.error || 'not connected'}`, 'error')
      if (data.anthropic?.configured) onLog?.(`Anthropic: configured (${data.anthropic.model})`, 'success')

      if (dfData.available) {
        onLog?.(`DF Services: ${dfData.services?.length || 0} total, ${dfData.social?.length || 0} social, ${dfData.databases?.length || 0} databases`, 'success')
        dfData.social?.forEach(s => {
          const auth = s.auth_status?.connected ? 'authenticated' : 'not authenticated'
          onLog?.(`  [${s.type?.toUpperCase()}] ${s.name} — ${auth}`, 'detail')
        })
      }
    } catch (e) {
      onLog?.(`Connection check failed: ${e.message}`, 'error')
    } finally {
      setChecking(false)
    }
  }

  const getVal = (key) => edits[key] ?? settings[key]?.value ?? ''
  const isDirty = Object.keys(edits).length > 0

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">Account Settings</h2>
        <div className="settings-subtitle">Shared across all companies</div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className={`btn btn-run ${checking ? 'loading' : ''}`} onClick={checkConnections} disabled={checking}>
            {checking ? 'Checking...' : 'Test Connections'}
          </button>
          <button className={`btn btn-approve ${saving ? 'loading' : ''}`} onClick={save} disabled={!isDirty || saving}>
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      {/* CONNECTION STATUS */}
      <div className="settings-section">
        <div className="section-label">Connection Status</div>
        <div className="status-grid">
          <div className="status-item">
            <StatusDot configured={status.anthropic?.configured} connected={status.anthropic?.configured} />
            <span>Anthropic</span>
            <span className="status-detail">{status.anthropic?.configured ? status.anthropic.model : 'No API key'}</span>
          </div>
          <div className="status-item">
            <StatusDot configured={status.github?.configured} connected={status.github?.connected} />
            <span>GitHub</span>
            <span className="status-detail">{status.github?.connected ? `@${status.github.user}` : status.github?.configured ? 'Not connected' : 'No token'}</span>
          </div>
          <div className="status-item">
            <StatusDot configured={status.dreamfactory?.configured} connected={status.dreamfactory?.connected} />
            <span>DreamFactory</span>
            <span className="status-detail">{status.dreamfactory?.connected ? status.dreamfactory.url : status.dreamfactory?.configured ? 'Not connected' : 'No API key'}</span>
          </div>
        </div>
      </div>

      {/* DF SERVICES — discovered from DreamFactory */}
      {dfServices?.available && (
        <div className="settings-section">
          <div className="section-label">DreamFactory Services</div>
          <div className="status-grid">
            {dfServices.databases?.map(db => (
              <div key={db.name} className="status-item">
                <span className="dot dot-on" />
                <span>{db.label || db.name}</span>
                <span className="status-detail">{db.type} database</span>
              </div>
            ))}
            {dfServices.social?.map(svc => (
              <div key={svc.name} className="status-item">
                <StatusDot configured={true} connected={svc.auth_status?.connected} />
                <span>{svc.label || svc.name}</span>
                <span className="status-detail">
                  {svc.auth_status?.connected ? 'Authenticated' : 'Needs OAuth'}
                </span>
              </div>
            ))}
            {(!dfServices.databases?.length && !dfServices.social?.length) && (
              <div className="status-item">
                <span className="dot dot-warn" />
                <span>No services found</span>
                <span className="status-detail">Add database + social services in DF admin</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* API KEYS */}
      <div className="settings-section">
        <div className="section-label">API Keys</div>
        <SettingField label="Anthropic API Key" k="anthropic_api_key" type="password" getVal={getVal} edit={edit} settings={settings} />
        <SettingField label="GitHub Token" k="github_token" type="password" getVal={getVal} edit={edit} settings={settings} />
      </div>

      {/* DREAMFACTORY */}
      <div className="settings-section">
        <div className="section-label">DreamFactory</div>
        <SettingField label="DF Base URL" k="df_base_url" getVal={getVal} edit={edit} settings={settings} placeholder="http://localhost:8080" />
        <SettingField label="DF API Key" k="df_api_key" type="password" getVal={getVal} edit={edit} settings={settings} />
      </div>

      {/* ENGINE */}
      <div className="settings-section">
        <div className="section-label">Engine</div>
        <SettingField label="Claude Model (content)" k="claude_model" getVal={getVal} edit={edit} settings={settings} placeholder="claude-sonnet-4-6" />
        <SettingField label="Claude Model (fast/analysis)" k="claude_model_fast" getVal={getVal} edit={edit} settings={settings} placeholder="claude-haiku-4-5-20251001" />
        <SettingField label="GitHub Webhook Secret" k="github_webhook_secret" type="password" getVal={getVal} edit={edit} settings={settings} />
      </div>

      {/* OAUTH APP CREDENTIALS */}
      <div className="settings-section">
        <div className="section-label">OAuth App Credentials</div>
        <SettingField label="LinkedIn Client ID" k="linkedin_client_id" getVal={getVal} edit={edit} settings={settings} />
        <SettingField label="LinkedIn Client Secret" k="linkedin_client_secret" type="password" getVal={getVal} edit={edit} settings={settings} />
        <SettingField label="Facebook App ID" k="facebook_app_id" getVal={getVal} edit={edit} settings={settings} />
        <SettingField label="Facebook App Secret" k="facebook_app_secret" type="password" getVal={getVal} edit={edit} settings={settings} />
      </div>
    </div>
  )
}

function SettingField({ label, k, type = 'text', getVal, edit, settings, placeholder }) {
  const val = getVal(k)
  const isSet = settings[k]?.is_set
  return (
    <div className="setting-field">
      <label className="setting-label">
        {label}
        {isSet && <span className="setting-badge">SET</span>}
      </label>
      <input
        className="setting-input"
        type={type}
        value={val}
        onChange={e => edit(k, e.target.value)}
        placeholder={placeholder || ''}
        spellCheck={false}
      />
    </div>
  )
}
