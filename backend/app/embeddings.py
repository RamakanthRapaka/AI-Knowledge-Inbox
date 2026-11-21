import json
import math
import os
import urllib.error
import urllib.request

OLLAMA_URL = os.environ.get('OLLAMA_URL', 'http://127.0.0.1:11434')
MODEL = os.environ.get('EMBEDDING_MODEL', 'embeddinggemma')

class EmbeddingError(Exception):
    pass

def configured():
    return bool(os.environ.get('OLLAMA_ENABLED', 'true').lower() == 'true')

def normalize(vector):
    if not vector or any(not isinstance(x, (int, float)) or not math.isfinite(x) for x in vector):
        raise EmbeddingError('Provider returned an invalid embedding.')
    magnitude = math.sqrt(sum(x * x for x in vector))
    if magnitude == 0:
        raise EmbeddingError('Provider returned an empty embedding.')
    return [x / magnitude for x in vector]

def embed(texts):
    if not configured():
        raise EmbeddingError('Enable Ollama in backend/.env and restart the backend to enable indexing.')
    vectors = []
    for start in range(0, len(texts), 32):
        batch = texts[start:start + 32]
        request = urllib.request.Request(OLLAMA_URL.rstrip('/') + '/api/embed',
            data=json.dumps({'model': MODEL, 'input': batch}).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.load(response)
            records = payload.get('embeddings') or []
            if len(records) != len(batch):
                raise EmbeddingError('Ollama returned an incomplete embedding batch.')
            vectors.extend(normalize(vector) for vector in records)
        except urllib.error.HTTPError as error:
            raise EmbeddingError('Ollama rejected the embedding request. Confirm the model is installed.') from None
        except (OSError, ValueError, KeyError, TypeError):
            raise EmbeddingError('Embedding service unavailable or returned invalid data. Please retry.') from None
    if vectors and any(len(v) != len(vectors[0]) for v in vectors):
        raise EmbeddingError('Provider returned inconsistent vector dimensions.')
    return vectors
