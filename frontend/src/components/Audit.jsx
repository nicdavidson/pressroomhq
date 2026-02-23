import { useState } from 'react'

const API = '/api'

function orgHeaders(orgId) {
  const h = { 'Content-Type': 'application/json' }
  if (orgId) h['X-Org-Id'] = String(orgId)
  return h
}

function ScoreRing({ score }) {
  const color = score >= 80 ? 'var(--green)' : score >= 50 ? 'var(--amber)' : 'var(--red)'
  return (
    <div className="audit-score-ring" style={{ borderColor: color }}>
      <span className="audit-score-number" style={{ color }}>{score}</span>
      <span className="audit-score-label">SEO</span>
    </div>
  )
}

function IssueBadge({ count }) {
  const color = count === 0 ? 'var(--green)' : count <= 2 ? 'var(--amber)' : 'var(--red)'
  return <span className="audit-issue-count" style={{ background: color }}>{count}</span>
}

export default function Audit({ onLog, orgId }) {
  const [domain, setDomain] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [expandedPage, setExpandedPage] = useState(null)

  const runAudit = async () => {
    setRunning(true)
    setResult(null)
    onLog?.(`SEO AUDIT — scanning ${domain || 'org domain'}...`, 'action')
    try {
      const res = await fetch(`${API}/audit/seo`, {
        method: 'POST',
        headers: orgHeaders(orgId),
        body: JSON.stringify({ domain, max_pages: 15 }),
      })
      const data = await res.json()
      if (data.error) {
        onLog?.(`AUDIT FAILED — ${data.error}`, 'error')
        setResult({ error: data.error })
      } else {
        setResult(data)
        const score = data.recommendations?.score || 0
        onLog?.(`AUDIT COMPLETE — Score: ${score}/100, ${data.pages_audited} pages, ${data.recommendations?.total_issues || 0} issues`, 'success')
      }
    } catch (e) {
      onLog?.(`AUDIT ERROR — ${e.message}`, 'error')
      setResult({ error: e.message })
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h2 className="settings-title">SEO Audit</h2>
      </div>

      {/* RUN AUDIT */}
      <div className="settings-section">
        <div className="section-label">Run Audit</div>
        <p className="voice-hint">
          Crawl your site's pages, check SEO elements (titles, meta, headings, images, schema),
          and get AI-powered recommendations. Leave domain blank to use the onboarded domain.
        </p>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            className="setting-input"
            style={{ flex: 1 }}
            value={domain}
            onChange={e => setDomain(e.target.value)}
            placeholder="https://example.com (or leave blank for org domain)"
            onKeyDown={e => { if (e.key === 'Enter') runAudit() }}
            spellCheck={false}
          />
          <button
            className={`btn btn-run ${running ? 'loading' : ''}`}
            onClick={runAudit}
            disabled={running}
          >
            {running ? 'Auditing...' : 'Run Audit'}
          </button>
        </div>
      </div>

      {/* ERROR */}
      {result?.error && (
        <div className="settings-section">
          <div style={{ color: 'var(--red)', fontSize: 13 }}>{result.error}</div>
        </div>
      )}

      {/* RESULTS */}
      {result && !result.error && (
        <>
          {/* SCORE + SUMMARY */}
          <div className="settings-section">
            <div className="audit-summary">
              <ScoreRing score={result.recommendations?.score || 0} />
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

          {/* AI ANALYSIS */}
          <div className="settings-section">
            <div className="section-label">Analysis & Recommendations</div>
            <div className="audit-analysis">
              {result.recommendations?.analysis?.split('\n').map((line, i) => {
                if (!line.trim()) return <br key={i} />
                // Bold section headers
                if (/^[0-9]+\.|^[A-Z]{3,}|^\*\*/.test(line.trim())) {
                  return <div key={i} className="audit-section-header">{line.replace(/\*\*/g, '')}</div>
                }
                return <div key={i} className="audit-line">{line}</div>
              })}
            </div>
          </div>

          {/* PAGE-BY-PAGE */}
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
      )}
    </div>
  )
}
