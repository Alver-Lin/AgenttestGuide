import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.storage import MarkdownStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', MarkdownStore(tmp_path / 'content'))
    with TestClient(main.app) as client:
        yield client


def test_recursive_folder_delete_preserves_contents_comments_and_undo(client):
    root = main.store.root
    note = client.get('/api/notes/welcome').json()
    comment = client.post('/api/notes/welcome/comments', json={
        'body': '保留评论', 'anchor': {'quote': 'Agent', 'start': 0, 'end': 5, 'prefix': '', 'suffix': ''},
    }).json()
    folder = root / note['path'].split('/')[0]
    # Preserve files the web tree does not display as well.
    (folder / 'extras').mkdir()
    (folder / 'extras/附件.txt').write_text('不可丢失')
    assert client.delete('/api/notebooks/getting-started?recursive=true').status_code == 204
    assert not folder.exists()
    data = client.get('/api/bootstrap').json()
    assert not any(book['id'] == 'getting-started' for book in data['notebooks'])
    assert all(item['deleted_at'] for item in data['notes'] if item['notebook_id'] == 'getting-started')
    assert client.post('/api/notes', json={'notebook_id': 'getting-started'}).status_code == 404
    assert client.post('/api/notes/welcome/restore').status_code == 409
    main.initialize()
    restored = client.post('/api/notebooks/getting-started/restore')
    assert restored.status_code == 200
    assert len(restored.json()['notes']) == 3
    assert client.get('/api/notes/welcome').json()['content'] == note['content']
    assert client.get('/api/notes/welcome/comments').json()[0]['id'] == comment['id']
    assert (folder / 'extras/附件.txt').read_text() == '不可丢失'


def test_restore_keeps_previously_trashed_notes_deleted_and_checks_collisions(client):
    assert client.delete('/api/notes/welcome').status_code == 204
    assert client.delete('/api/notebooks/getting-started?recursive=true').status_code == 204
    original_path = main.store.index['notebooks']['getting-started']['original_path']
    collision = client.post('/api/notebooks', json={'name': original_path}).json()
    assert client.post('/api/notebooks/getting-started/restore').status_code == 409
    assert client.delete('/api/notebooks/' + collision['id']).status_code == 204
    assert client.post('/api/notebooks/getting-started/restore').status_code == 200
    assert client.get('/api/notes/welcome').json()['deleted_at']
    assert client.post('/api/notes/welcome/restore').status_code == 200


def test_all_folders_can_be_archived_without_reseeding_and_empty_folder_restored(client):
    books = client.get('/api/bootstrap').json()['notebooks']
    for book in books:
        assert client.delete('/api/notebooks/' + book['id'] + '?recursive=true').status_code == 204
    main.initialize()
    assert client.get('/api/bootstrap').json()['notebooks'] == []
    assert client.post('/api/notebooks/ideas/restore').status_code == 200
    assert [book['id'] for book in client.get('/api/bootstrap').json()['notebooks']] == ['ideas']


def test_folder_archive_rolls_back_when_index_write_fails(client, monkeypatch):
    before = client.get('/api/notes/welcome').json()
    original_write = main.store.write_index

    def fail_write():
        raise OSError('模拟索引写入失败')

    monkeypatch.setattr(main.store, 'write_index', fail_write)
    with pytest.raises(OSError):
        main.store.delete_folder('getting-started', recursive=True)
    monkeypatch.setattr(main.store, 'write_index', original_write)
    assert client.get('/api/notes/welcome').json()['content'] == before['content']
    assert client.delete('/api/notebooks/getting-started?recursive=true').status_code == 204
    monkeypatch.setattr(main.store, 'write_index', fail_write)
    with pytest.raises(OSError):
        main.store.restore_folder('getting-started')
    monkeypatch.setattr(main.store, 'write_index', original_write)
    assert client.get('/api/notes/welcome').json()['deleted_at']
    assert client.post('/api/notebooks/getting-started/restore').status_code == 200
