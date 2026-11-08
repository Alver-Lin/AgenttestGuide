from pathlib import Path
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend import main, storage
from backend.storage import MarkdownStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", MarkdownStore(tmp_path / "content"))
    with TestClient(main.app) as client:
        yield client


def legacy_database(path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE notebooks (id TEXT PRIMARY KEY, name TEXT, color TEXT, description TEXT, created_at TEXT);
            CREATE TABLE notes (id TEXT PRIMARY KEY, notebook_id TEXT, title TEXT, content TEXT, tags TEXT,
                is_favorite INTEGER, deleted_at TEXT, created_at TEXT, updated_at TEXT);
        """)
        db.execute("INSERT INTO notebooks VALUES ('legacy', '课程资料', 'blue', '原始描述', '2026-01-01T00:00:00+00:00')")
        db.execute("INSERT INTO notebooks VALUES ('empty', '空目录', 'green', '', '2026-01-01T00:00:00+00:00')")
        for identifier, content, deleted in [('first', '## 第一篇\r\n正文一。', None), ('second', '# 第二篇\n不同内容。', None), ('trashed', '需要保留的旧回收站内容', '2026-01-02T00:00:00+00:00')]:
            db.execute("INSERT INTO notes VALUES (?, 'legacy', '同名文档', ?, '[\"保留标签\"]', 1, ?, '2026-01-01T00:00:00+00:00', '2026-01-01T01:00:00+00:00')", (identifier, content, deleted))


def test_migration_preserves_bodies_ids_empty_folders_and_duplicates(tmp_path):
    legacy = tmp_path / "old.db"
    legacy_database(legacy)
    old_bytes = legacy.read_bytes()
    store = MarkdownStore(tmp_path / "content", legacy_db=legacy, backup_dir=tmp_path / "backups")
    store.initialize()
    data = store.bootstrap()
    assert {book['id'] for book in data['notebooks']} == {'legacy', 'empty'}
    assert (store.root / '空目录').is_dir()
    assert (store.root / '课程资料/同名文档.md').read_bytes() == '## 第一篇\r\n正文一。'.encode()
    assert (store.root / '课程资料/同名文档 (2).md').read_text() == '# 第二篇\n不同内容。'
    assert store.read_note('first')['content'] == '## 第一篇\r\n正文一。'
    assert store.read_note('first')['tags'] == ['保留标签']
    assert store.read_note('first')['is_favorite'] is True
    assert store.read_note('trashed')['deleted_at']
    assert store.read_note('trashed')['content'] == '需要保留的旧回收站内容'
    index = store.index_path.read_text()
    assert '正文一' not in index and '不同内容' not in index
    assert legacy.read_bytes() == old_bytes
    assert len(list((tmp_path / 'backups').glob('*.db'))) == 1
    store.initialize()
    assert len(store.bootstrap()['notes']) == 3
    assert len(list((tmp_path / 'backups').glob('*.db'))) == 1


def test_existing_markdown_directory_is_used_without_database_import(tmp_path):
    root = tmp_path / 'content'
    folder = root / '自己整理的知识'
    folder.mkdir(parents=True)
    (folder / '独立文档.md').write_text('外部编辑器写入的内容', encoding='utf-8')
    legacy = tmp_path / 'old.db'
    legacy_database(legacy)
    store = MarkdownStore(root, legacy_db=legacy)
    store.initialize()
    data = store.bootstrap()
    assert len(data['notes']) == 1 and data['notes'][0]['content'] == '外部编辑器写入的内容'
    assert not (root / '课程资料').exists()


def test_folder_rename_and_move_change_real_paths_without_losing_ids(client):
    book = client.post('/api/notebooks', json={'name': '新课程'}).json()
    note = client.post('/api/notes', json={'notebook_id': book['id'], 'title': '实验.md', 'content': '实验记录'}).json()
    root = main.store.root
    assert (root / '新课程/实验.md').read_text() == '实验记录'
    assert not (root / '新课程/实验.md.md').exists()
    renamed = client.put('/api/notebooks/' + book['id'], json={'name': '新课程名称'}).json()
    assert renamed['id'] == book['id'] and not (root / '新课程').exists()
    assert (root / '新课程名称/实验.md').is_file()
    saved = client.patch('/api/notes/' + note['id'], json={'title': '正式实验', 'notebook_id': 'ideas', 'content': '更新后的记录'}).json()
    assert saved['id'] == note['id']
    assert (root / '灵感与思考/正式实验.md').read_text() == '更新后的记录'
    assert not (root / '新课程名称/实验.md').exists()
    main.initialize()
    assert client.get('/api/notes/' + note['id']).json()['content'] == '更新后的记录'


def test_external_edits_renames_additions_and_deletions_are_observed(client):
    root = main.store.root
    original = client.get('/api/notes/welcome').json()
    path = root / original['path']
    path.write_text('## 直接从磁盘编辑\n新的内容', encoding='utf-8')
    assert client.get('/api/notes/welcome').json()['content'] == '## 直接从磁盘编辑\n新的内容'
    renamed = path.with_name('外部重命名.md')
    path.rename(renamed)
    assert client.get('/api/notes/welcome').json()['title'] == '外部重命名'
    parent = renamed.parent
    parent.rename(parent.with_name('外部文件夹名称'))
    note = client.get('/api/notes/welcome').json()
    assert note['notebook_id'] == 'getting-started' and note['path'].startswith('外部文件夹名称/')
    added = root / '外部文件夹名称/手工添加.md'
    added.write_text('手工添加的正文', encoding='utf-8')
    assert any(n['content'] == '手工添加的正文' for n in client.get('/api/bootstrap').json()['notes'])
    (root / note['path']).unlink()
    assert client.get('/api/notes/welcome').status_code == 404
    main.initialize()
    assert client.get('/api/notes/welcome').status_code == 404


def test_duplicate_names_cannot_overwrite_files(client):
    payload = {'notebook_id': 'ideas', 'title': '第一份', 'content': '必须保留的正文'}
    first = client.post('/api/notes', json=payload).json()
    assert client.post('/api/notes', json=payload).status_code == 409
    second = client.post('/api/notes', json={**payload, 'title': '第二份', 'content': '第二份原文'}).json()
    assert client.patch('/api/notes/' + second['id'], json={'title': '第一份', 'content': '不能覆盖'}).status_code == 409
    assert client.get('/api/notes/' + first['id']).json()['content'] == '必须保留的正文'
    assert client.get('/api/notes/' + second['id']).json()['content'] == '第二份原文'
    assert client.post('/api/notebooks', json={'name': '灵感与思考'}).status_code == 409


@pytest.mark.parametrize('name', ['../escape', 'a/b', 'a\\b', '.agenttestguide', 'CON', 'bad:name', 'a' * 231])
def test_unsafe_names_are_rejected(client, name):
    assert client.post('/api/notes', json={'notebook_id': 'ideas', 'title': name}).status_code == 422
    assert client.post('/api/notebooks', json={'name': name}).status_code == 422


def test_symlinks_are_not_followed(client, tmp_path):
    outside = tmp_path / 'private.txt'
    outside.write_text('目录外的内容', encoding='utf-8')
    folder = main.store.root / '灵感与思考'
    (folder / 'linked.md').symlink_to(outside)
    data = client.get('/api/bootstrap').json()
    assert not any(note['title'] == 'linked' for note in data['notes'])
    assert client.post('/api/notes', json={'notebook_id': 'ideas', 'title': 'linked'}).status_code == 409
    assert outside.read_text() == '目录外的内容'


def test_failed_atomic_save_keeps_previous_body_and_cleans_temporary_file(client, monkeypatch):
    note = client.get('/api/notes/welcome').json()
    path = main.store.root / note['path']
    previous = path.read_bytes()
    replace = storage.os.replace
    def fail_markdown(source, target):
        if Path(target).suffix == '.md':
            raise OSError('simulated full disk')
        return replace(source, target)
    monkeypatch.setattr(storage.os, 'replace', fail_markdown)
    with pytest.raises(OSError, match='full disk'):
        main.store.update_note('welcome', {'content': '保存失败时不应覆盖旧文档'})
    assert path.read_bytes() == previous
    assert not list(path.parent.glob('.agenttestguide-*.tmp'))


def test_failed_import_is_not_published_and_can_be_retried(tmp_path, monkeypatch):
    legacy = tmp_path / 'old.db'
    legacy_database(legacy)
    root = tmp_path / 'content'
    store = MarkdownStore(root, legacy_db=legacy, backup_dir=tmp_path / 'backups')
    write = Path.write_bytes
    def fail_second(path, data):
        if '第二篇' in data.decode('utf-8'):
            raise OSError('simulated import failure')
        return write(path, data)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'write_bytes', fail_second)
        with pytest.raises(OSError, match='import failure'):
            store.initialize()
    assert not root.exists()
    assert not list(tmp_path.glob('.content-import-*'))
    store.initialize()
    assert len(store.bootstrap()['notes']) == 3
