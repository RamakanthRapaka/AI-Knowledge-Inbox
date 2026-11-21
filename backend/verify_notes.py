"""Integration checks using an isolated database and a real API process."""
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request('http://127.0.0.1:18001' + path, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=3) as response:
            return response.status, json.load(response), response.headers
    except urllib.error.HTTPError as error:
        return error.code, json.load(error), error.headers

def start(env):
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--port', '18001'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        if process.poll() is not None:
            raise RuntimeError('Test server failed to start')
        try:
            if request('/health')[0] == 200:
                return process
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(.1)
    process.terminate()
    process.wait()
    raise RuntimeError('Server startup timed out')

with tempfile.TemporaryDirectory() as directory:
    env = dict(os.environ, INBOX_DB_PATH=str(Path(directory) / 'test.db'))
    process = start(env)
    try:
        assert request('/items')[1] == {'items': [], 'total': 0}
        text = '  Support hours: 9 AM–6 PM.\nUnicode: नमस्ते  '
        status, item, headers = request('/ingest', {'type': 'note', 'content': text})
        assert status == 201 and item['raw_content'] == text and item['status'] == 'saved'
        assert headers['X-Request-ID']
        for payload in ({'type': 'note', 'content': ''}, {'type': 'note', 'content': '   '}, {'type': 'note', 'content': 'x' * 20001}, {'type': 'url', 'content': 'x'}, {'type': 'note', 'content': 123}):
            assert request('/ingest', payload)[0] == 422
        assert request('/items?limit=0')[0] == 422
        assert request('/items?offset=-1')[0] == 422
        assert request('/items')[1]['total'] == 1
        assert request('/items?offset=1')[1]['items'] == []
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=True, stdout=subprocess.DEVNULL)
        process.wait()
        process = start(env)
        assert request('/items')[1]['items'][0] == item
        print('PASS: ingestion, raw text, metadata, validation, pagination, request ID, and persistence after server restart')
    finally:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=True, stdout=subprocess.DEVNULL)
        process.wait()
