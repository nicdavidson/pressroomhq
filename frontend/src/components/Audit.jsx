import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function orgHeaders(orgId) {
  const h = { 'Content-Type': 'application/json' }
  if (orgId) h['X-Org-Id'] = String(orgId)
  return h
}

function ScoreRing({ score, label }) {
  const color = score >= 80 ? 'var(--green)' : score >= 50 ? 'var(--amber)' : 'var(--red)'
  return (
    <div className="audit-score-ring" style={{ borderColor: color }}>
      <span className="audit-score-number" style={{ color }}>{score}</span>
      <span className="audit-score-label">{label || 'SCORE'}</span>
    </div>
  )
}

function IssueBadge({ count }) {
  const color = count === 0 ? 'var(--green)' : count <= 2 ? 'var(--amber)' : 'var(--red)'
  return <span className="audit-issue-count" style={{ background: color }}>{count}</span>
}

function SectionCheck({ label, found }) {
  return (
    <span className={`audit-section-check ${found ? 'found' : 'missing'}`}>
      {found ? '\u2713' : '\u2717'} {label}
    </span>
  )
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' ' +
    d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
}

// ────────────────────────────────────────
// SEO Results Display (shared by live + saved)
// ────────────────────────────────────────
function SeoResults({ result }) {
  const [expandedPage, setExpandedPage] = useState(null)

  return (
    <>
      <div className="settings-section">
        <div className="audit-summary">
          <ScoreRing score={result.recommendations?.score || 0} label="SEO" />
          <div className="audit-summary-stats">
            <div className="audit-stat">
              <span className="audit-stat-num">{result.pages_audited}</span>
              <span className="audit-stat-label">pages</span>
            </div>
            <div className="audit-stat">
              <span className="audit-stat-num">{result.recommendations?.total_issues || 0}</span>
              <span className="audit-stat-label">issues</span>
            </div>
            <div className="audit-stat">
              <span className="audit-stat-num">{result.domain}</span>
              <span className="audit-stat-label">domain</span>
            </div>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <div className="section-label">Analysis & Recommendations</div>
        <div className="audit-analysis">
          {result.recommendations?.analysis?.split('\n').map((line, i) => {
            if (!line.trim()) return <br key={i} />
            if (/^[0-9]+\.|^[A-Z]{3,}|^\*\*/.test(line.trim())) {
              return <div key={i} className="audit-section-header">{line.replace(/\*\*/g, '')}</div>
            }
            return <div key={i} className="audit-line">{line}</div>
          })}
        </div>
      </div>

      <div className="settings-section">
        <div className="section-label">Page Details</div>
        {result.pages?.map((p, i) => (
          <div key={i} className="audit-page">
            <div
              className="audit-page-header"
              onClick={() => setExpandedPage(expandedPage === i ? null : i)}
            >
              <div className="audit-page-url">
                <span className="audit-page-toggle">{expandedPage === i ? '\u25BC' : '\u25B6'}</span>
                {p.url.replace(result.domain, '')}
              </div>
              <IssueBadge count={p.issue_count || 0} />
            </div>
            {expandedPage === i && (
              <div className="audit-page-details">
                <div className="audit-detail-row">
                  <span className="audit-detail-label">Title</span>
                  <span className={`audit-detail-value ${!p.title ? 'missing' : p.title_length > 60 ? 'warn' : ''}`}>
                    {p.title || 'MISSING'} ({p.title_length} chars)
                  </span>
                </div>
                <div className="audit-detail-row">
                  <span className="audit-detail-label">Meta Desc</span>
                  <span className={`audit-detail-value ${!p.meta_description ? 'missing' : p.meta_description_length > 160 ? 'warn' : ''}`}>
                    {p.meta_description?.slice(0, 100) || 'MISSING'} ({p.meta_description_length} chars)
                  </span>
                </div>
                <div className="audit-detail-row">
                  <span className="audit-detail-label">H1</span>
                  <span className={`audit-detail-value ${p.h1_count !== 1 ? 'warn' : ''}`}>
                    {p.h1_texts?.join(', ') || 'MISSING'} ({p.h1_count} found)
                  </span>
                </div>
                <div className="audit-detail-row">
                  <span className="audit-detail-label">Content</span>
                  <span className="audit-detail-value">{p.word_count} words | {p.h2_count} H2s</span>
                </div>
                <div className="audit-detail-row">
                  <span className="audit-detail-label">Images</span>
                  <span className={`audit-detail-value ${p.images_missing_alt > 0 ? 'warn' : ''}`}>
                    {p.total_images} total, {p.images_missing_alt} missing alt
                  </span>
                </div>
                <div className="audit-detail-row">
                  <span className="audit-detail-label">Links</span>
                  <span className="audit-detail-value">{p.internal_links} internal, {p.external_links} external</span>
                </div>
                <div className="audit-detail-row">
                  <span className="audit-detail-label">Technical</span>
                  <span className="audit-detail-value">
                    Canonical: {p.canonical ? 'Yes' : 'No'} | Schema: {p.has_schema ? 'Yes' : 'No'} | OG: {p.og_title ? 'Yes' : 'No'}
                  </span>
                </div>
                {p.issues?.length > 0 && (
                  <div className="audit-issues">
                    {p.issues.map((issue, j) => (
                      <div key={j} className="audit-issue">{issue}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </>
  )
}

// ────────────────────────────────────────
// README Results Display (shared by live + saved)
// ────────────────────────────────────────
function ReadmeResults({ result }) {
  return (
    <>
      <div className="settings-section">
        <div className="audit-summary">
          <ScoreRing score={result.recommendations?.score || 0} label="README" />
          <div className="audit-summary-stats">
            <div className="audit-stat">
              <span className="audit-stat-num">{result.repo}</span>
              <span className="audit-stat-label">repo</span>
            </div>
            <div className="audit-stat">
              <span className="audit-stat-num">{result.word_count}</span>
              <span className="audit-stat-label">words</span>
            </div>
            <div className="audit-stat">
              <span className="audit-stat-num">{result.recommendations?.total_issues || 0}</span>
              <span className="audit-stat-label">missing sections</span>
            </div>
          </div>
        </div>
      </div>

      <div className="settings-section">
        <div className="section-label">Structure</div>
        <div className="audit-structure-grid">
          <SectionCheck label="Installation" found={result.structure?.sections_found?.installation} />
          <SectionCheck label="Usage / Examples" found={result.structure?.sections_found?.usage} />
          <SectionCheck label="API Reference" found={result.structure?.sections_found?.api_reference} />
          <SectionCheck label="Contributing" found={result.structure?.sections_found?.contributing} />
          <SectionCheck label="License" found={result.structure?.sections_found?.license} />
          <SectionCheck label="Badges" found={result.structure?.sections_found?.badges} />
          <SectionCheck label="Screenshots / Images" found={result.structure?.sections_found?.images} />
          <SectionCheck label="Code Blocks" found={result.structure?.sections_found?.code_blocks} />
        </div>
        <div className="audit-structure-counts">
          {result.structure?.heading_count || 0} headings &middot; {result.structure?.code_block_count || 0} code blocks &middot; {result.structure?.link_count || 0} links &middot; {result.structure?.badge_count || 0} badges
        </div>
      </div>

      <div className="settings-section">
        <div className="section-label">Analysis & Recommendations</div>
        <div className="audit-analysis">
          {result.recommendations?.analysis?.split('\n').map((line, i) => {
            if (!line.trim()) return <br key={i} />
            if (/^[0-9]+\.|^[A-Z]{3,}|^\*\*/.test(line.trim())) {
              return <div key={i} className="audit-section-header">{line.replace(/\*\*/g, '')}</div>
            }
            return <div key={i} className="audit-line">{line}</div>
          })}
        </div>
      </div>
    </>
  )
}

// ────────────────────────────────────────
// SEO Audit Sub-Tab
// ────────────────────────────────────────
function SeoAudit({ onLog, orgId, assets, history, onRefreshHistory }) {
  const [domain, setDomain] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [viewingSaved, setViewingSaved] = useState(null)

  const domainAssets = assets.filter(a =>
    ['subdomain', 'blog', 'docs', 'product', 'page'].includes(a.asset_type) && a.url
  )

  const runAudit = async (targetDomain) => {
    const d = targetDomain || domain
    setRunning(true)
    setResult(null)
    setViewingSaved(null)
    onLog?.(`SEO AUDIT — scanning ${d || 'org domain'}...`, 'action')
    try {
      const res = await fetch(`${API}/audit/seo`, {
        method: 'POST',
        headers: orgHeaders(orgId),
        body: JSON.stringify({ domain: d, max_pages: 15 }),
      })
      const data = await res.json()
      if (data.error) {
        onLog?.(`AUDIT FAILED — ${data.error}`, 'error')
        setResult({ error: data.error })
      } else {
        setResult(data)
        const score = data.recommendations?.score || 0
        onLog?.(`AUDIT COMPLETE — Score: ${score}/100, ${data.pages_audited} pages, ${data.recommendations?.total_issues || 0} issues`, 'success')
        onRefreshHistory?.()
      }
    } catch (e) {
      onLog?.(`AUDIT ERROR — ${e.message}`, 'error')
      setResult({ error: e.message })
    } finally {
      setRunning(false)
    }
  }

  const viewSaved = async (audit) => {
    try {
      const res = await fetch(`${API}/audit/history/${audit.id}`, { headers: orgHeaders(orgId) })
      const data = await res.json()
      if (data.result) {
        setViewingSaved(data)
        setResult(null)
      }
    } catch { /* ignore */ }
  }

  const deleteSaved = async (id, e) => {
    e.stopPropagation()
    try {
      await fetch(`${API}/audit/history/${id}`, { method: 'DELETE', headers: orgHeaders(orgId) })
      onRefreshHistory?.()
      if (viewingSaved?.id === id) setViewingSaved(null)
    } catch { /* ignore */ }
  }

  const seoHistory = history.filter(h => h.audit_type === 'seo')
  const activeResult = viewingSaved?.result || result
  const isViewingSaved = !!viewingSaved

  return (
    <>
      {/* RUN NEW */}
      <div className="settings-section">
        <div className="section-label">Target</div>
        <p className="voice-hint">
          Crawl a site's pages, check SEO elements (titles, meta, headings, images, schema),
          and get AI-powered recommendations. Results are saved automatically.
        </p>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {domainAssets.length > 0 && (
            <select
              className="setting-input"
              style={{ width: 260 }}
              value={domain}
              onChange={e => setDomain(e.target.value)}
            >
              <option value="">Org domain (default)</option>
              {domainAssets.map(a => (
                <option key={a.id} value={a.url}>
                  {a.label || a.asset_type} — {a.url.replace(/^https?:\/\//, '').slice(0, 40)}
                </option>
              ))}
            </select>
          )}
          <input
            className="setting-input"
            style={{ flex: 1, minWidth: 200 }}
            value={domain}
            onChange={e => setDomain(e.target.value)}
            placeholder={domainAssets.length > 0 ? 'or type a custom URL' : 'https://example.com (or leave blank for org domain)'}
            onKeyDown={e => { if (e.key === 'Enter') runAudit() }}
            spellCheck={false}
          />
          <button
            className={`btn btn-run ${running ? 'loading' : ''}`}
            onClick={() => runAudit()}
            disabled={running}
          >
            {running ? 'Auditing...' : 'Run SEO Audit'}
          </button>
        </div>
      </div>

      {/* SAVED HISTORY */}
      {seoHistory.length > 0 && (
        <div className="settings-section">
          <div className="section-label">History</div>
          <div className="audit-history-list">
            {seoHistory.map(h => (
              <div
                key={h.id}
                className={`audit-history-item ${viewingSaved?.id === h.id ? 'active' : ''}`}
                onClick={() => viewSaved(h)}
              >
                <ScoreBadge score={h.score} />
                <div className="audit-history-detail">
                  <span className="audit-history-target">{h.target.replace(/^https?:\/\//, '')}</span>
                  <span className="audit-history-date">{formatDate(h.created_at)}</span>
                </div>
                <span className="audit-history-issues">{h.total_issues} issues</span>
                <button
                  className="btn btn-run"
                  style={{ fontSize: 11, padding: '3px 8px' }}
                  onClick={(e) => { e.stopPropagation(); runAudit(h.target) }}
                  disabled={running}
                  title="Re-run this audit"
                >
                  Refresh
                </button>
                <button
                  className="btn-icon"
                  onClick={(e) => deleteSaved(h.id, e)}
                  title="Delete"
                >&times;</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ERROR */}
      {result?.error && (
        <div className="settings-section">
          <div style={{ color: 'var(--red)', fontSize: 13 }}>{result.error}</div>
        </div>
      )}

      {/* RESULTS — live or saved */}
      {isViewingSaved && (
        <div className="audit-saved-banner">
          Viewing saved audit from {formatDate(viewingSaved.created_at)}
          <button className="btn btn-run" style={{ fontSize: 11, padding: '3px 10px', marginLeft: 12 }}
            onClick={() => runAudit(viewingSaved.target)} disabled={running}>
            {running ? 'Refreshing...' : 'Refresh'}
          </button>
          <button className="btn" style={{ fontSize: 11, padding: '3px 10px', marginLeft: 4, color: 'var(--text-dim)', borderColor: 'var(--border)' }}
            onClick={() => setViewingSaved(null)}>
            Close
          </button>
        </div>
      )}

      {activeResult && !activeResult.error && <SeoResults result={activeResult} />}
    </>
  )
}

// ────────────────────────────────────────
// README Audit Sub-Tab
// ────────────────────────────────────────
function ReadmeAudit({ onLog, orgId, assets, history, onRefreshHistory }) {
  const [repo, setRepo] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [viewingSaved, setViewingSaved] = useState(null)

  const repoAssets = assets.filter(a => a.asset_type === 'repo' && a.url)

  const runAudit = async (targetRepo) => {
    const r = targetRepo || repo
    if (!r.trim()) {
      onLog?.('README AUDIT — no repo specified', 'error')
      return
    }
    setRunning(true)
    setResult(null)
    setViewingSaved(null)
    onLog?.(`README AUDIT — analyzing ${r}...`, 'action')
    try {
      const res = await fetch(`${API}/audit/readme`, {
        method: 'POST',
        headers: orgHeaders(orgId),
        body: JSON.stringify({ repo: r }),
      })
      const data = await res.json()
      if (data.error) {
        onLog?.(`README AUDIT FAILED — ${data.error}`, 'error')
        setResult({ error: data.error })
      } else {
        setResult(data)
        const score = data.recommendations?.score || 0
        onLog?.(`README AUDIT COMPLETE — Score: ${score}/100 for ${data.repo}`, 'success')
        onRefreshHistory?.()
      }
    } catch (e) {
      onLog?.(`README AUDIT ERROR — ${e.message}`, 'error')
      setResult({ error: e.message })
    } finally {
      setRunning(false)
    }
  }

  const viewSaved = async (audit) => {
    try {
      const res = await fetch(`${API}/audit/history/${audit.id}`, { headers: orgHeaders(orgId) })
      const data = await res.json()
      if (data.result) {
        setViewingSaved(data)
        setResult(null)
      }
    } catch { /* ignore */ }
  }

  const deleteSaved = async (id, e) => {
    e.stopPropagation()
    try {
      await fetch(`${API}/audit/history/${id}`, { method: 'DELETE', headers: orgHeaders(orgId) })
      onRefreshHistory?.()
      if (viewingSaved?.id === id) setViewingSaved(null)
    } catch { /* ignore */ }
  }

  const readmeHistory = history.filter(h => h.audit_type === 'readme')
  const activeResult = viewingSaved?.result || result
  const isViewingSaved = !!viewingSaved

  return (
    <>
      <div className="settings-section">
        <div className="section-label">Target Repository</div>
        <p className="voice-hint">
          Analyze a GitHub repo's README for quality, structure, and completeness.
          Results are saved automatically.
        </p>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          {repoAssets.length > 0 && (
            <select
              className="setting-input"
              style={{ width: 280 }}
              value={repo}
              onChange={e => setRepo(e.target.value)}
            >
              <option value="">Select a repo...</option>
              {repoAssets.map(a => {
                const match = a.url.match(/github\.com\/([^/]+\/[^/]+)/)
                const repoName = match ? match[1] : a.label || a.url
                return (
                  <option key={a.id} value={repoName}>
                    {repoName}
                  </option>
                )
              })}
            </select>
          )}
          <input
            className="setting-input"
            style={{ flex: 1, minWidth: 200 }}
            value={repo}
            onChange={e => setRepo(e.target.value)}
            placeholder={repoAssets.length > 0 ? 'or type owner/repo' : 'owner/repo or GitHub URL'}
            onKeyDown={e => { if (e.key === 'Enter') runAudit() }}
            spellCheck={false}
          />
          <button
            className={`btn btn-run ${running ? 'loading' : ''}`}
            onClick={() => runAudit()}
            disabled={running || !repo.trim()}
          >
            {running ? 'Auditing...' : 'Run README Audit'}
          </button>
        </div>
      </div>

      {/* SAVED HISTORY */}
      {readmeHistory.length > 0 && (
        <div className="settings-section">
          <div className="section-label">History</div>
          <div className="audit-history-list">
            {readmeHistory.map(h => (
              <div
                key={h.id}
                className={`audit-history-item ${viewingSaved?.id === h.id ? 'active' : ''}`}
                onClick={() => viewSaved(h)}
              >
                <ScoreBadge score={h.score} />
                <div className="audit-history-detail">
                  <span className="audit-history-target">{h.target}</span>
                  <span className="audit-history-date">{formatDate(h.created_at)}</span>
                </div>
                <span className="audit-history-issues">{h.total_issues} missing</span>
                <button
                  className="btn btn-run"
                  style={{ fontSize: 11, padding: '3px 8px' }}
                  onClick={(e) => { e.stopPropagation(); runAudit(h.target) }}
                  disabled={running}
                  title="Re-run this audit"
                >
                  Refresh
                </button>
                <button
                  className="btn-icon"
                  onClick={(e) => deleteSaved(h.id, e)}
                  title="Delete"
                >&times;</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {result?.error && (
        <div className="settings-section">
          <div style={{ color: 'var(--red)', fontSize: 13 }}>{result.error}</div>
        </div>
      )}

      {isViewingSaved && (
        <div className="audit-saved-banner">
          Viewing saved audit from {formatDate(viewingSaved.created_at)}
          <button className="btn btn-run" style={{ fontSize: 11, padding: '3px 10px', marginLeft: 12 }}
            onClick={() => runAudit(viewingSaved.target)} disabled={running}>
            {running ? 'Refreshing...' : 'Refresh'}
          </button>
          <button className="btn" style={{ fontSize: 11, padding: '3px 10px', marginLeft: 4, color: 'var(--text-dim)', borderColor: 'var(--border)' }}
            onClick={() => setViewingSaved(null)}>
            Close
          </button>
        </div>
      )}

      {activeResult && !activeResult.error && <ReadmeResults result={activeResult} />}
    </>
  )
}

// ────────────────────────────────────────
// Small score badge for history list
// ────────────────────────────────────────
function ScoreBadge({ score }) {
  const color = score >= 80 ? 'var(--green)' : score >= 50 ? 'var(--amber)' : 'var(--red)'
  return (
    <span className="audit-score-badge" style={{ background: color }}>
      {score}
    </span>
  )
}

// ────────────────────────────────────────
// Main Audit Component — Tabbed
// ────────────────────────────────────────
export default function Audit({ onLog, orgId }) {
  const [tab, setTab] = useState('seo')
  const [assets, setAssets] = useState([])
  const [history, setHistory] = useState([])

  const loadAssets = useCallback(async () => {
    try {
      const res = await fetch(`${API}/assets`, { headers: orgHeaders(orgId) })
      const data = await res.json()
      setAssets(Array.isArray(data) ? data : [])
    } catch { /* ignore */ }
  }, [orgId])

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(`${API}/audit/history`, { headers: orgHeaders(orgId) })
      const data = await res.json()
      setHistory(Array.isArray(data) ? data : [])
    } catch { /* ignore */ }
  }, [orgId])

  useEffect(() => { loadAssets(); loadHistory() }, [loadAssets, loadHistory])

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">Audit</h2>
        <div className="audit-tabs">
          <button
            className={`audit-tab ${tab === 'seo' ? 'active' : ''}`}
            onClick={() => setTab('seo')}
          >
            SEO Audit
          </button>
          <button
            className={`audit-tab ${tab === 'readme' ? 'active' : ''}`}
            onClick={() => setTab('readme')}
          >
            README Audit
          </button>
        </div>
      </div>

      {tab === 'seo' && <SeoAudit onLog={onLog} orgId={orgId} assets={assets} history={history} onRefreshHistory={loadHistory} />}
      {tab === 'readme' && <ReadmeAudit onLog={onLog} orgId={orgId} assets={assets} history={history} onRefreshHistory={loadHistory} />}
    </div>
  )
}
