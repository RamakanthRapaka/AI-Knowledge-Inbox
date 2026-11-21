import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import db, search, embeddings

class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / 'test.db'
        db.initialize()
        for item_id, text in [('a', 'Support is open Monday.'), ('b', 'Python database tutorial.')]:
            db.insert_item(dict(id=item_id, source_type='note', raw_content=text, extracted_text=text, created_at='2026-01-01', status='indexing', source_url=None, final_url=None, title=None))

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.temp.cleanup()

    def test_chunk_boundaries(self):
        text = 'a' * 3000
        chunks = search.chunk_text(text)
        self.assertEqual([len(chunk) for chunk in chunks], [1200, 1200, 1000])
        self.assertEqual(search.chunk_text('  '), [])
        self.assertTrue(all(len(chunk) <= 1200 for chunk in search.chunk_text('word ' * 1000)))

    def test_ranking_persistence_and_reindex(self):
        with patch.object(embeddings, 'embed', side_effect=[[[1, 0]], [[0, 1]], [[1, 0]]]):
            search.index_item('a')
            search.index_item('b')
            db.initialize()
            results = search.retrieve('support', 1)
        self.assertEqual(results[0]['item_id'], 'a')
        self.assertEqual(results[0]['score'], 1)
        with patch.object(embeddings, 'embed', return_value=[[1, 0]]):
            search.index_item('a')
        with db.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM chunks WHERE item_id=?', ('a',)).fetchone()[0], 1)

    def test_failure_and_retry(self):
        with patch.object(embeddings, 'embed', side_effect=embeddings.EmbeddingError('Provider unavailable')):
            search.index_item('a')
        with db.connect() as connection:
            self.assertEqual(connection.execute("SELECT status FROM items WHERE id='a'").fetchone()[0], 'failed')
        with patch.object(embeddings, 'embed', return_value=[[1, 0]]):
            search.index_item('a')
        self.assertEqual(db.list_items(10, 0)['items'][1]['status'], 'ready')

    def test_empty_index_does_not_call_provider(self):
        with patch.object(embeddings, 'embed') as mock:
            self.assertEqual(search.retrieve('test', 5), [])
            mock.assert_not_called()

    def test_invalid_vector(self):
        for vector in ([0, 0], [float('nan')], []):
            with self.assertRaises(embeddings.EmbeddingError):
                embeddings.normalize(vector)

if __name__ == '__main__':
    unittest.main()
