import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.storage import MarkdownStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", MarkdownStore(tmp_path / 'content'))
    with TestClient(main.app) as client:
        yield client


def payload(body='值得进一步解释'):
    return {'body': body, 'anchor': {'quote': '任务完成度', 'start': 50, 'end': 55, 'prefix': '除了结果是否正确', 'suffix': '它真正解决'}}


def test_comment_lifecycle_persists_without_changing_markdown(client):
    note = client.get('/api/notes/welcome').json()
    file = main.store.root / note['path']
    before = hashlib.sha256(file.read_bytes()).hexdigest()
    assert client.get('/api/notes/welcome/comments').json() == []
    response = client.post('/api/notes/welcome/comments', json=payload('  补充一个例子  '))
    assert response.status_code == 201
    comment = response.json()
    assert comment['body'] == '补充一个例子' and comment['note_id'] == 'welcome'
    stored = json.loads(main.store.comment_path('welcome').read_text())
    assert stored['comments'][0]['anchor'] == comment['anchor']
    main.initialize()
    assert client.get('/api/notes/welcome/comments').json() == [comment]
    url = '/api/notes/welcome/comments/' + comment['id']
    updated = client.patch(url, json={'body': '修改后的评论'}).json()
    assert updated['body'] == '修改后的评论' and updated['anchor'] == comment['anchor']
    assert client.delete(url).status_code == 204
    assert client.get('/api/notes/welcome/comments').json() == []
    assert hashlib.sha256(file.read_bytes()).hexdigest() == before


def test_comments_follow_file_and_folder_renames_and_restore(client):
    comment = client.post('/api/notes/welcome/comments', json=payload()).json()
    assert client.patch('/api/notes/welcome', json={'title': '改名后的文档', 'notebook_id': 'ideas'}).status_code == 200
    assert client.put('/api/notebooks/ideas', json={'name': '改名后的文件夹'}).status_code == 200
    assert client.get('/api/notes/welcome/comments').json()[0]['id'] == comment['id']
    assert client.delete('/api/notes/welcome').status_code == 204
    assert client.post('/api/notes/welcome/comments', json=payload()).status_code == 409
    assert client.get('/api/notes/welcome/comments').json()[0]['id'] == comment['id']
    assert client.post('/api/notes/welcome/restore').status_code == 200
    assert client.get('/api/notes/welcome/comments').json()[0]['id'] == comment['id']
    assert client.delete('/api/notes/welcome').status_code == 204
    assert client.delete('/api/notes/welcome?permanent=true').status_code == 204
    assert not main.store.comment_path('welcome').exists()


def test_comment_validation_and_document_isolation(client):
    comment = client.post('/api/notes/welcome/comments', json=payload()).json()
    assert client.get('/api/notes/metrics/comments').json() == []
    assert client.delete('/api/notes/metrics/comments/' + comment['id']).status_code == 404
    for invalid in [payload('   '), {'body': '文字', 'anchor': {'quote': ' ', 'start': 0, 'end': 1}},
                    {'body': '文字', 'anchor': {'quote': '文字', 'start': 4, 'end': 2}},
                    {'body': '文字', 'anchor': {'quote': '文字', 'start': -1, 'end': 2}}]:
        assert client.post('/api/notes/welcome/comments', json=invalid).status_code == 422
    assert client.get('/api/notes/missing/comments').status_code == 404
    assert client.post('/api/notes/missing/comments', json=payload()).status_code == 404


def test_corrupt_comment_file_is_not_overwritten(client):
    client.post('/api/notes/welcome/comments', json=payload())
    path = main.store.comment_path('welcome')
    path.write_text('broken json', encoding='utf-8')
    assert client.get('/api/notes/welcome/comments').status_code == 409
    assert client.post('/api/notes/welcome/comments', json=payload()).status_code == 409
    assert path.read_text() == 'broken json'
