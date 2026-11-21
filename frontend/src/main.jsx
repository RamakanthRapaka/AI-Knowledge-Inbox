import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';
import SearchPanel from './SearchPanel';

async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, options);
  const data = await response.json();
  if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(error => error.msg).join('; ') : data.detail || 'Request failed');
  return data;
}

function App() {
  const [content, setContent] = useState('');
  const [type, setType] = useState('note');
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [providerReady, setProviderReady] = useState(false);
  useEffect(() => { api('/indexing-status').then(data => setProviderReady(data.configured)).catch(() => {}); }, []);
  useEffect(() => {
    if (!items.some(item => item.status === 'indexing')) return;
    const timer = setInterval(() => { api('/items').then(data => { setItems(data.items); setTotal(data.total); }).catch(() => {}); }, 2000);
    return () => clearInterval(timer);
  }, [items]);

  async function loadItems() {
    setLoading(true);
    try { const data = await api('/items'); setItems(data.items); setTotal(data.total); }
    finally { setLoading(false); }
  }
  useEffect(() => { loadItems().catch(() => setError('Could not load notes. Check the backend and retry.')); }, []);

  async function save(event) {
    event.preventDefault();
    if (!content.trim() || saving) return;
    setSaving(true); setError(''); setMessage('');
    try {
      await api('/ingest', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(type === 'note' ? { type, content } : { type, url: content.trim() }) });
      setContent(''); setMessage(providerReady ? 'Content saved. Indexing in progress.' : 'Content saved. Configure the embedding provider to enable indexing.');
      try { await loadItems(); } catch { setError('Your note was saved, but the list could not refresh. Retry loading the list.'); }
    } catch (err) { setError(err.message || 'Could not save the note.'); }
    finally { setSaving(false); }
  }

  return <main>
    <p className="eyebrow">AI KNOWLEDGE INBOX</p>
    <h1>A home for your knowledge.</h1>
    <p className="intro">Collect notes and public web pages in one place. Ask questions and get answers grounded in your saved content.
    </p>
    <form onSubmit={save}>
      <label htmlFor="source-type">Content type</label>
      <select id="source-type" value={type} disabled={saving} onChange={event => { setType(event.target.value); setContent(''); setError(''); setMessage(''); }}><option value="note">Text note</option><option value="url">Website URL</option></select>
      <label htmlFor="note">{type === 'note' ? 'Add a note' : 'Public website URL'}</label>
      {type === 'note' ? <textarea id="note" value={content} onChange={event => setContent(event.target.value)} maxLength={20000} required disabled={saving} placeholder="Paste an idea, meeting note, or useful information…"/> : <input id="note" type="url" value={content} onChange={event => setContent(event.target.value)} maxLength={2048} required disabled={saving} placeholder="https://example.com/article"/>}
      <p className="counter">{type === 'note' ? `${content.length.toLocaleString()} / 20,000 characters` : 'HTML or plain text, up to 2 MB. JavaScript-only pages are not supported.'}</p>
      <button disabled={saving || loading || !content.trim()}>{saving ? (type === 'url' ? 'Importing page…' : 'Saving…') : (type === 'url' ? 'Import URL' : 'Save note')}</button>
    </form>
    {error && <p role="alert" className="error-message">{error}</p>}
    <p role="status">{message}</p>
    {!providerReady && <p>Local AI is unavailable. Start Ollama, then restart the backend and refresh this page.</p>}
    <SearchPanel/>
    <div className="list-heading"><h2>Saved items ({total})</h2><button disabled={loading || saving} onClick={() => { setError(''); loadItems().catch(() => setError('Could not load items. Please retry.')); }}>Refresh</button></div>
    {loading && <p role="status">Loading notes…</p>}
    {!loading && items.length === 0 && <p>No notes yet. Add your first note above.</p>}
    {items.map(item => <article key={item.id}>
      <p className="metadata">{item.source_type.toUpperCase()} · {new Date(item.created_at).toLocaleString()} · {item.status === 'ready' ? 'Searchable' : item.status}</p>
      {item.error && <p role="alert">{item.error}</p>}
      <button disabled={!providerReady || item.status === 'indexing'} onClick={async () => {
        try { await api(`/items/${item.id}/index`, {method: 'POST'}); await loadItems(); }
        catch (error) { setError(error.message); }
      }}>{item.status === 'ready' ? 'Reindex' : item.status === 'indexing' ? 'Indexing…' : 'Index content'}</button>
      {item.source_url && <h2><a href={item.source_url} target="_blank" rel="noopener noreferrer">{item.title || item.source_url}</a></h2>}
      <p className="note-text">{(item.extracted_text || item.raw_content).slice(0, 1000)}</p>
      {(item.extracted_text || item.raw_content).length > 1000 && <details><summary>Read full content</summary><p className="note-text">{item.extracted_text || item.raw_content}</p></details>}
    </article>)}
    {items.length < total && <button disabled={loading || saving} onClick={async () => {
      setLoading(true); setError('');
      try { const data = await api(`/items?offset=${items.length}`); setItems(current => [...current, ...data.items]); setTotal(data.total); }
      catch { setError('Could not load more notes. Please retry.'); }
      finally { setLoading(false); }
    }}>Load more</button>}
  </main>;
}
createRoot(document.getElementById('root')).render(<React.StrictMode><App/></React.StrictMode>);
