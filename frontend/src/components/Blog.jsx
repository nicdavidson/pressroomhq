import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export default function Blog({ orgId }) {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [scraping, setScraping] = useState(false)
  const [scrapeResult, setScrapeResult] = useState(null)
  const [blogUrl, setBlogUrl] = useState('')

  const headers = { 'Content-Type': 'application/json', ...(orgId ? { 'X-Org-Id': String(orgId) } : {}) }

  // Load blog URL from social_profiles setting
  const loadBlogUrl = useCallback(async () => {
    try {
      const res = await fetch(`${API}/settings`, { headers })
      if (!res.ok) return
      const data = await res.json()
      const sp = JSON.parse(data.social_profiles?.value || '{}')
      if (sp.blog) setBlogUrl(sp.blog)
    } catch { /* ignore */ }
  }, [orgId])

  const fetchPosts = useCallback(async () => {
    try {
      const res = await fetch(`${API}/blog/posts`, { headers })
      const data = await res.json()
      setPosts(Array.isArray(data) ? data : [])
    } catch { /* ignore */ }
    setLoading(false)
  }, [orgId])

  useEffect(() => { loadBlogUrl(); fetchPosts() }, [loadBlogUrl, fetchPosts])

  const scrapeBlog = async () => {
    setScraping(true)
    setScrapeResult(null)
    try {
      const res = await fetch(`${API}/blog/scrape`, {
        method: 'POST', headers,
        body: JSON.stringify({ blog_url: blogUrl }),
      })
      const data = await res.json()
      setScrapeResult(data)
      if (data.posts_saved > 0) {
        fetchPosts()
      }
    } catch (e) {
      setScrapeResult({ error: e.message })
    }
    setScraping(false)
  }

  const deletePost = async (id) => {
    await fetch(`${API}/blog/posts/${id}`, { method: 'DELETE', headers })
    fetchPosts()
  }

  const formatDate = (iso) => {
    if (!iso) return 'Unknown date'
    try {
      const d = new Date(iso)
      return d.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
    } catch {
      return iso
    }
  }

  if (loading) return <div className="settings-page"><p style={{ color: 'var(--text-dim)' }}>Loading blog posts...</p></div>

  return (
    <div className="settings-page">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16, flexWrap: 'wrap', gap: 8 }}>
        <h2 className="settings-title" style={{ margin: 0 }}>Blog Posts</h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            className="setting-input"
            placeholder="Blog URL (from Company settings)"
            value={blogUrl}
            onChange={e => setBlogUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && scrapeBlog()}
            style={{ width: 260, fontSize: 12 }}
          />
          <button
            className="btn btn-run"
            onClick={scrapeBlog}
            disabled={scraping}
          >
            {scraping ? 'Scraping...' : 'Scrape Blog'}
          </button>
        </div>
      </div>

      {scrapeResult && (
        <div style={{
          padding: '10px 14px', marginBottom: 16,
          border: '1px solid var(--border)',
          background: 'var(--bg-card)',
          fontSize: 12, lineHeight: 1.5,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span>
            {scrapeResult.error ? (
              <span style={{ color: 'var(--error)' }}>Scrape failed: {scrapeResult.error}</span>
            ) : scrapeResult.message ? (
              <span style={{ color: 'var(--text-dim)' }}>{scrapeResult.message}</span>
            ) : (
              <span>
                Found {scrapeResult.posts_found} posts from{' '}
                <span style={{ color: 'var(--accent)' }}>{scrapeResult.blog_url}</span>
                {' '}&mdash; saved {scrapeResult.posts_saved}, skipped {scrapeResult.posts_skipped} duplicates.
              </span>
            )}
          </span>
          <button
            style={{ marginLeft: 12, cursor: 'pointer', background: 'none', border: 'none', color: 'var(--text-dim)', fontSize: 14 }}
            onClick={() => setScrapeResult(null)}
          >&times;</button>
        </div>
      )}

      {posts.length === 0 ? (
        <div style={{ padding: 40, textAlign: 'center', color: 'var(--text-dim)' }}>
          <p style={{ fontSize: 14, marginBottom: 8 }}>No blog posts scraped yet.</p>
          <p style={{ fontSize: 12 }}>
            Set your blog URL in <strong>Config &rarr; Company &rarr; Social Profiles</strong>, then click <strong>Scrape Blog</strong>.
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--text-dim)', marginBottom: 4 }}>
            {posts.length} post{posts.length !== 1 ? 's' : ''} scraped
          </div>
          {posts.map(p => (
            <div key={p.id} style={{
              border: '1px solid var(--border)',
              background: 'var(--bg-card)',
              padding: '12px 14px',
              display: 'flex', flexDirection: 'column', gap: 4,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.3 }}>
                    {p.url ? (
                      <a
                        href={p.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ color: 'var(--accent)', textDecoration: 'none' }}
                      >
                        {p.title || 'Untitled'}
                      </a>
                    ) : (
                      p.title || 'Untitled'
                    )}
                  </div>
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 2 }}>
                    {formatDate(p.published_at)}
                    {p.scraped_at && (
                      <span style={{ marginLeft: 8 }}>scraped {formatDate(p.scraped_at)}</span>
                    )}
                  </div>
                </div>
                <button
                  style={{
                    background: 'none', border: 'none', color: 'var(--text-dim)',
                    cursor: 'pointer', fontSize: 16, lineHeight: 1, padding: 0, flexShrink: 0,
                  }}
                  onClick={() => deletePost(p.id)}
                  title="Remove post"
                >&times;</button>
              </div>
              {p.excerpt && (
                <div style={{
                  fontSize: 11, color: 'var(--text-dim)', lineHeight: 1.4,
                  overflow: 'hidden',
                  display: '-webkit-box',
                  WebkitLineClamp: 3,
                  WebkitBoxOrient: 'vertical',
                }}>
                  {p.excerpt}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
