import React, { useState } from 'react';

export default function SearchPanel() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError(''); setResult(null);
    try {
      const response = await fetch('/api/query', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({question}) });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Please enter a valid question.');
      setResult(data);
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }
  return <section style={{display: 'block'}}><h2>Search your knowledge</h2>
    <p>Ask a question about your indexed notes and imported pages.</p>
    <form onSubmit={submit}><label htmlFor="question">What are you looking for?</label>
      <input id="question" value={question} onChange={event => setQuestion(event.target.value)} maxLength={2000} required/>
      <button disabled={busy || !question.trim()}>{busy ? 'Searching…' : 'Search'}</button></form>
    {error && <p role="alert">{error}</p>}
    {result && <><div className="answer"><h2>Answer</h2><p className="note-text">{result.answer}</p></div>{result.citations?.length > 0 && <><h2>Sources</h2>{result.citations.map((source, index) => <article key={source.chunk_id}><p className="metadata">[{index + 1}] SOURCE · {source.title || 'Saved note'} · relevance {source.score}</p><p className="note-text">{source.snippet}</p>{source.source_url && <a href={source.source_url} target="_blank" rel="noopener noreferrer">View source</a>}</article>)}</>}</>}
  </section>;
}
