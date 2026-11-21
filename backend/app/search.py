import json
import logging
from uuid import uuid4
from . import db, embeddings

logger = logging.getLogger('inbox')

def chunk_text(text, size=1200, overlap=200):
    if not 0 <= overlap < size:
        raise ValueError('Overlap must be smaller than chunk size')
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = text.rfind('\n', start + size // 2, end)
            if boundary < 0:
                boundary = text.rfind(' ', start + size // 2, end)
            if boundary >= 0:
                end = boundary + 1
        value = text[start:end].strip()
        if value:
            chunks.append(value)
        if end == len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks

def index_item(item_id):
    try:
        with db.connect() as connection:
            row = connection.execute('SELECT * FROM items WHERE id=?', (item_id,)).fetchone()
        chunks = chunk_text(row['extracted_text'] or row['raw_content'])
        if not chunks:
            raise embeddings.EmbeddingError('No searchable text was found.')
        if len(chunks) > 500:
            raise embeddings.EmbeddingError('Content exceeds the 500-chunk indexing limit.')
        vectors = embeddings.embed(chunks)
        with db.connect() as connection:
            connection.execute('DELETE FROM chunks WHERE item_id=?', (item_id,))
            connection.executemany('INSERT INTO chunks VALUES (?, ?, ?, ?, ?, ?)',
                [(str(uuid4()), item_id, i, text, json.dumps(vector), embeddings.MODEL) for i, (text, vector) in enumerate(zip(chunks, vectors))])
            connection.execute("UPDATE items SET status='ready', error=NULL WHERE id=?", (item_id,))
        logger.info(json.dumps({'event': 'indexed', 'item_id': item_id, 'chunks': len(chunks)}))
    except Exception as error:
        message = str(error) if isinstance(error, embeddings.EmbeddingError) else 'Indexing failed. Please retry.'
        with db.connect() as connection:
            connection.execute("UPDATE items SET status='failed', error=? WHERE id=?", (message, item_id))
        logger.error(json.dumps({'event': 'index_failed', 'item_id': item_id, 'error_type': type(error).__name__}))

def retrieve(question, top_k):
    with db.connect() as connection:
        rows = connection.execute("SELECT c.*, i.title, i.source_url FROM chunks c JOIN items i ON c.item_id=i.id WHERE i.status='ready' AND c.model=?", (embeddings.MODEL,)).fetchall()
    if not rows:
        return []
    query = embeddings.embed([question])[0]
    results = []
    for row in rows:
        vector = json.loads(row['embedding'])
        if len(vector) != len(query):
            raise embeddings.EmbeddingError('Stored vectors have incompatible dimensions. Reindex saved content.')
        score = sum(a * b for a, b in zip(query, vector))
        results.append({'chunk_id': row['id'], 'item_id': row['item_id'], 'snippet': row['text'],
            'title': row['title'], 'source_url': row['source_url'], 'score': round(score, 6)})
    return sorted(results, key=lambda row: row['score'], reverse=True)[:top_k]
