import base64

import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.storage import MarkdownStore
from backend.images import MAX_IMAGE_BYTES

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aFOsAAAAASUVORK5CYII=')


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', MarkdownStore(tmp_path / 'content'))
    with TestClient(main.app) as client:
        yield client


def upload(client, note_id='welcome', name='截图.png', body=PNG, mime='image/png'):
    return client.post(f'/api/notes/{note_id}/images', files={'file': (name, body, mime)})


def test_upload_to_regular_note_stores_relative_image_without_replacing_content(client):
    before = client.get('/api/notes/welcome').json()
    result = upload(client)
    assert result.status_code == 201
    image = result.json()
    assert image['name'] == '截图'
    assert image['path'].startswith('_assets/welcome/')
    asset = image['path'].removeprefix('_assets/welcome/')
    response = client.get('/api/notes/welcome/assets/' + asset)
    assert response.content == PNG
    assert response.headers['content-type'] == 'image/png'
    after = client.get('/api/notes/welcome').json()
    assert after['content'] == before['content']
    assert (main.store.root / after['path']).parent.joinpath(image['path']).read_bytes() == PNG
    # Duplicate source names never overwrite an existing image.
    assert upload(client).json()['path'] != image['path']


def test_image_survives_rename_move_folder_delete_and_restore(client):
    image = upload(client).json()
    asset_url = '/api/notes/welcome/assets/' + image['path'].split('/')[-1]
    markdown = f"![截图]({image['path']})"
    assert client.patch('/api/notes/welcome', json={'title': '配图笔记', 'content': markdown,
                                                 'notebook_id': 'ideas'}).status_code == 200
    assert client.put('/api/notebooks/ideas', json={'name': '配图课程'}).status_code == 200
    assert client.get(asset_url).content == PNG
    assert client.delete('/api/notebooks/ideas?recursive=true').status_code == 204
    assert client.post('/api/notebooks/ideas/restore').status_code == 200
    assert client.get(asset_url).content == PNG
    assert client.get('/api/notes/welcome').json()['content'] == markdown
    assert client.delete('/api/notes/welcome').status_code == 204
    assert client.post('/api/notes/welcome/restore').status_code == 200
    assert client.get(asset_url).content == PNG
    assert client.delete('/api/notes/welcome').status_code == 204
    assert client.delete('/api/notes/welcome?permanent=true').status_code == 204
    assert not (main.store.root / '配图课程/_assets/welcome').exists()


@pytest.mark.parametrize('body,status', [
    (b'', 422), (b'<svg xmlns="http://www.w3.org/2000/svg"/>', 422),
    (b'<html>not an image</html>', 422), (PNG + b'x' * MAX_IMAGE_BYTES, 413),
])
def test_invalid_and_oversized_uploads_create_no_assets(client, body, status):
    assert upload(client, body=body).status_code == status
    assert 'asset_dir' not in main.store.index['notes']['welcome']


def test_filename_cannot_escape_attachment_directory_and_type_comes_from_bytes(client):
    result = upload(client, name='../../伪装.html', mime='text/html').json()
    assert result['name'] == '伪装'
    assert result['path'].endswith('.png')
    assert '..' not in result['path']
    assert client.get('/api/notes/welcome/assets/%2e%2e/%2e%2e/secret.png').status_code in (404, 422)


def test_missing_deleted_notes_and_symlink_attachment_directory_are_rejected(client):
    assert upload(client, note_id='missing').status_code == 404
    assert client.delete('/api/notes/welcome').status_code == 204
    assert upload(client).status_code == 409
    assert client.post('/api/notes/welcome/restore').status_code == 200
    note = client.get('/api/notes/welcome').json()
    directory = (main.store.root / note['path']).parent
    (directory / '_assets').symlink_to(main.store.root, target_is_directory=True)
    assert upload(client).status_code == 409


def test_failed_index_write_removes_only_new_upload(client, monkeypatch):
    initial = upload(client).json()
    original_write = main.store.write_index

    def fail_write():
        raise OSError('模拟磁盘错误')

    monkeypatch.setattr(main.store, 'write_index', fail_write)
    with pytest.raises(OSError):
        upload(client)
    monkeypatch.setattr(main.store, 'write_index', original_write)
    directory = main.store.path(main.store.index['notes']['welcome']['asset_dir'])
    assert [path.name for path in directory.iterdir()] == [initial['path'].split('/')[-1]]


@pytest.mark.parametrize('source', [
    'images/示意 图.png', './images/示意 图.png',
    'images/%E7%A4%BA%E6%84%8F%20%E5%9B%BE.png',
    'images/示意 图.png?version=2#preview', r'.\images\示意 图.png',
])
def test_custom_relative_images_resolve_from_markdown_directory(client, source):
    note = client.get('/api/notes/welcome').json()
    image = (main.store.root / note['path']).parent / 'images/示意 图.png'
    image.parent.mkdir()
    image.write_bytes(PNG)
    response = client.get('/api/notes/welcome/image', params={'path': source})
    assert response.status_code == 200
    assert response.content == PNG
    assert response.headers['content-type'] == 'image/png'
    assert client.get('/api/notes/welcome').json()['content'] == note['content']
    # Resolving an existing file needs no upload metadata.
    assert 'asset_dir' not in main.store.index['notes']['welcome']


def test_shared_images_root_relative_names_and_encoded_punctuation(client):
    directory = main.store.root / 'shared'
    directory.mkdir()
    (directory / '图 #1.png').write_bytes(PNG)
    for source in ('../shared/图%20%231.png', '/shared/图%20%231.png'):
        response = client.get('/api/notes/welcome/image', params={'path': source})
        assert response.status_code == 200
        assert response.content == PNG


def test_custom_image_renamed_folder_and_uploaded_image_compatibility(client):
    note = client.get('/api/notes/welcome').json()
    directory = (main.store.root / note['path']).parent / 'images'
    directory.mkdir()
    (directory / 'diagram.png').write_bytes(PNG)
    uploaded = upload(client).json()['path']
    assert client.put('/api/notebooks/getting-started', json={'name': '新路径'}).status_code == 200
    for source in ('images/diagram.png', uploaded):
        assert client.get('/api/notes/welcome/image', params={'path': source}).content == PNG


@pytest.mark.parametrize('source', [
    '../../outside.png', '%2e%2e/%2e%2e/outside.png',
    '../.agenttestguide/private.png', 'images/../../.secret.png',
    'https://example.org/image.png', 'file:///etc/image.png',
    '//example.org/image.png', 'images/invalid%00.png',
])
def test_relative_image_rejects_outside_hidden_and_nonlocal_paths(client, source):
    (main.store.root.parent / 'outside.png').write_bytes(PNG)
    main.store.path('.agenttestguide/private.png').write_bytes(PNG)
    response = client.get('/api/notes/welcome/image', params={'path': source})
    assert response.status_code == 422


def test_relative_images_reject_symlinks_nonimages_missing_and_deleted_notes(client):
    note = client.get('/api/notes/welcome').json()
    directory = (main.store.root / note['path']).parent
    outside = main.store.root.parent / 'outside.png'
    outside.write_bytes(PNG)
    (directory / 'linked.png').symlink_to(outside)
    assert client.get('/api/notes/welcome/image', params={'path': 'linked.png'}).status_code == 409
    for source in ('images/missing.png', note['path'].split('/')[-1]):
        assert client.get('/api/notes/welcome/image', params={'path': source}).status_code == 404
    assert client.get('/api/notes/missing/image', params={'path': 'images/x.png'}).status_code == 404
    assert client.delete('/api/notes/welcome').status_code == 204
    assert client.get('/api/notes/welcome/image', params={'path': 'images/x.png'}).status_code == 409
