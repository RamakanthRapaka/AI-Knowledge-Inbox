import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get('INBOX_DB_PATH', Path(__file__).resolve().parents[1] / 'data' / 'inbox.db'))

@contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()

def initialize():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, source_type TEXT NOT NULL, raw_content TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL)')
        columns = {row['name'] for row in connection.execute('PRAGMA table_info(items)')}
        for column in ('source_url', 'final_url', 'title', 'extracted_text'):
            if column not in columns:
                connection.execute(f'ALTER TABLE items ADD COLUMN {column} TEXT')
        connection.execute('UPDATE items SET extracted_text = raw_content WHERE extracted_text IS NULL')
        if 'error' not in columns:
            connection.execute('ALTER TABLE items ADD COLUMN error TEXT')
        connection.execute('CREATE TABLE IF NOT EXISTS chunks (id TEXT PRIMARY KEY, item_id TEXT NOT NULL, position INTEGER NOT NULL, text TEXT NOT NULL, embedding TEXT NOT NULL, model TEXT NOT NULL, UNIQUE(item_id, position))')
        connection.execute("UPDATE items SET status='failed', error='Indexing interrupted by restart. Please retry.' WHERE status='indexing'")

def insert_item(item):
    with connect() as connection:
        connection.execute('INSERT INTO items (id, source_type, raw_content, created_at, status, source_url, final_url, title, extracted_text) VALUES (:id, :source_type, :raw_content, :created_at, :status, :source_url, :final_url, :title, :extracted_text)', item)
    return item

def list_items(limit, offset):
    with connect() as connection:
        rows = connection.execute('SELECT * FROM items ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?', (limit, offset)).fetchall()
        total = connection.execute('SELECT COUNT(*) FROM items').fetchone()[0]
    return {'items': [dict(row) for row in rows], 'total': total}
