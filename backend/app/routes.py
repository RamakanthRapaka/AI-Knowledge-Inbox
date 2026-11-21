from datetime import datetime, timezone
from typing import Annotated, Literal, Union
from uuid import uuid4
from fastapi import APIRouter, Query, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from . import db
from .url_ingestion import fetch_page
from . import embeddings, search
from . import llm

class NoteInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['note']
    content: str = Field(min_length=1, max_length=20000)

    @field_validator('content')
    @classmethod
    def require_text(cls, value):
        if not value.strip():
            raise ValueError('Note must contain non-whitespace text')
        return value

class URLInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['url']
    url: str = Field(min_length=1, max_length=2048)

class Item(BaseModel):
    id: str
    source_type: Literal['note', 'url']
    raw_content: str
    created_at: str
    status: Literal['saved', 'indexing', 'ready', 'failed']
    error: str | None = None
    source_url: str | None = None
    final_url: str | None = None
    title: str | None = None
    extracted_text: str | None = None

class ItemList(BaseModel):
    items: list[Item]
    total: int

router = APIRouter()

@router.post('/ingest', response_model=Item, status_code=201)
def ingest(note: Annotated[Union[NoteInput, URLInput], Field(discriminator='type')], background_tasks: BackgroundTasks):
    item = {'id': str(uuid4()), 'source_type': note.type,
        'created_at': datetime.now(timezone.utc).isoformat(), 'status': 'saved',
        'source_url': None, 'final_url': None, 'title': None}
    if note.type == 'url':
        item.update(fetch_page(note.url))
        item['source_url'] = note.url
    else:
        item.update(raw_content=note.content, extracted_text=note.content)
    if embeddings.configured():
        item['status'] = 'indexing'
    db.insert_item(item)
    if item['status'] == 'indexing':
        background_tasks.add_task(search.index_item, item['id'])
    return item

@router.get('/items', response_model=ItemList)
def items(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return db.list_items(limit, offset)

@router.get('/indexing-status')
def indexing_status():
    return {'configured': embeddings.configured(), 'model': embeddings.MODEL}

@router.post('/items/{item_id}/index', status_code=202)
def index(item_id: str, background_tasks: BackgroundTasks):
    if not embeddings.configured():
        raise HTTPException(503, 'Ollama is not enabled. Start Ollama and restart the backend.')
    with db.connect() as connection:
        row = connection.execute('SELECT status FROM items WHERE id=?', (item_id,)).fetchone()
        if row is None:
            raise HTTPException(404, 'Saved item not found.')
        claimed = connection.execute("UPDATE items SET status='indexing', error=NULL WHERE id=? AND status!='indexing'", (item_id,)).rowcount
        if not claimed:
            raise HTTPException(409, 'This item is already being indexed.')
    background_tasks.add_task(search.index_item, item_id)
    return {'id': item_id, 'status': 'indexing'}

class SearchInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator('question')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('Enter a question')
        return value.strip()

@router.post('/search')
def semantic_search(body: SearchInput):
    try:
        return {'results': search.retrieve(body.question, body.top_k)}
    except embeddings.EmbeddingError as error:
        raise HTTPException(503, str(error))

class QueryInput(SearchInput):
    pass

@router.post('/query')
def query(body: QueryInput):
    try:
        sources = search.retrieve(body.question, body.top_k)
        result = llm.answer(body.question, sources)
        return {'question': body.question, **result}
    except (embeddings.EmbeddingError, llm.LLMError) as error:
        raise HTTPException(503, str(error))
