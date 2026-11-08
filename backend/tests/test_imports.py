from io import BytesIO
from pathlib import Path
import base64
import json
import time
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.imports import ImportManager
from backend.mineru import Config, MinerUClient, MinerUError, public_url, trusted_result_url, unpack_archive
from backend.storage import MarkdownStore

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aFOsAAAAASUVORK5CYII=')


class FakeMinerU:
    def __init__(self, config):
        self.config = config
    def submit(self, filename, **kwargs):
        return {'kind': 'agent', 'id': 'remote-task', 'upload_url': 'https://oss-mineru.openxlab.org.cn/test'}
    def upload(self, url, source):
        assert source.read_bytes()
    def poll(self, remote):
        return {'state': 'done', 'markdown_url': 'https://cdn-mineru.openxlab.org.cn/test.md'}
    def result(self, data):
        return '# MinerU 转换结果\n\n可编辑的正文。\n\n![](images/figure.png)', {'images/figure.png': PNG}, []
    def close(self):
        pass


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'store', MarkdownStore(tmp_path / 'content'))
    monkeypatch.delenv('MINERU_API_TOKEN', raising=False)
    monkeypatch.delenv('MINERU_TOKEN', raising=False)
    with TestClient(main.app) as client:
        client.app.state.imports.client_factory = FakeMinerU
        yield client


def completed(client, identifier):
    for _ in range(300):
        result = client.get('/api/import/jobs/' + identifier).json()
        if result.get('state') in ('done', 'failed'):
            return result
        time.sleep(.01)
    pytest.fail('Import did not finish')


def test_markdown_upload_is_real_file_with_encoding_and_collision_protection(client):
    content = '# 中文导入\n\n**原样保留**，可以编辑。'
    ids = []
    for _ in range(2):
        response = client.post('/api/import/file', data={'notebook_id': 'ideas'}, files={'file': ('导入样例.md', content.encode('gb18030'), 'text/markdown')})
        assert response.status_code == 202
        result = completed(client, response.json()['id'])
        assert result['state'] == 'done', result
        note = result['note']
        ids.append(note['id'])
        assert (main.store.root / note['path']).read_text() == content
        assert client.get('/api/notes/' + note['id'] + '/original').content == content.encode('gb18030')
        assert '原样保留' not in client.app.state.imports.read(response.json()['id']).__repr__()
    assert ids[0] != ids[1]
    assert (main.store.root / '灵感与思考/导入样例 (2).md').exists()


def test_document_upload_retains_assets_original_and_rename_links(client):
    result = completed(client, client.post('/api/import/file', data={'notebook_id': 'ideas'}, files={'file': ('研究资料.pdf', b'%PDF test', 'application/pdf')}).json()['id'])
    assert result['state'] == 'done', result
    note = result['note']
    assert f'_assets/{note["id"]}/images/figure.png' in note['content']
    assert client.get('/api/notes/' + note['id'] + '/assets/images/figure.png').content == PNG
    assert client.get('/api/notes/' + note['id'] + '/original').content == b'%PDF test'
    assert client.patch('/api/notes/' + note['id'], json={'notebook_id': 'practice', 'title': '移动并改名'}).status_code == 200
    assert client.put('/api/notebooks/practice', json={'name': '实践资料'}).status_code == 200
    assert client.get('/api/notes/' + note['id'] + '/assets/images/figure.png').content == PNG
    assert (main.store.root / ('实践资料/_assets/' + note['id'] + '/images/figure.png')).is_file()
    assert client.get('/api/notes/' + note['id'] + '/assets/%2e%2e/%2e%2e/secret.png').status_code in (404, 422)
    assert client.delete('/api/notes/' + note['id']).status_code == 204
    assert client.delete('/api/notes/' + note['id'] + '?permanent=true').status_code == 204
    assert not (main.store.root / ('实践资料/_assets/' + note['id'])).exists()


def test_folder_delete_and_undo_preserve_import_assets_and_original(client):
    job = client.post('/api/import/file', data={'notebook_id': 'ideas'},
                      files={'file': ('资料.pdf', b'%PDF test', 'application/pdf')}).json()
    note = completed(client, job['id'])['note']
    url = '/api/notes/' + note['id']
    assert client.delete('/api/notebooks/ideas?recursive=true').status_code == 204
    assert client.post('/api/notebooks/ideas/restore').status_code == 200
    assert client.get(url + '/assets/images/figure.png').content == PNG
    assert client.get(url + '/original').content == b'%PDF test'
    assert client.get(url).json()['content'] == note['content']


def test_url_import_and_missing_folder(client):
    response = client.post('/api/import/url', json={'notebook_id': 'ideas', 'url': 'https://example.org/paper.pdf', 'filename': '论文.pdf'})
    assert response.status_code == 202
    result = completed(client, response.json()['id'])
    assert result['state'] == 'done'
    assert result['note']['imported_from']['url'] == 'https://example.org/paper.pdf'
    assert not result['note']['imported_from']['has_original']
    assert client.post('/api/import/url', json={'notebook_id': 'missing', 'url': 'https://example.org/a.pdf'}).status_code == 404
    assert client.post('/api/import/url', json={'notebook_id': 'ideas', 'url': 'http://127.0.0.1/secrets'}).status_code == 422


def test_unsupported_and_oversized_uploads_create_no_documents(client):
    before = len(client.get('/api/bootstrap').json()['notes'])
    assert client.post('/api/import/file', data={'notebook_id': 'ideas'}, files={'file': ('bad.exe', b'bad')}).status_code == 422
    result = client.post('/api/import/file', data={'notebook_id': 'ideas'}, files={'file': ('large.pdf', b'x' * (10 * 1024 * 1024 + 1))})
    assert result.status_code == 413
    assert len(client.get('/api/bootstrap').json()['notes']) == before


def test_webpage_requires_precision_mode_without_network_request():
    gateway = MinerUClient(Config())
    try:
        with pytest.raises(MinerUError, match='Token'):
            gateway.submit('article', url='https://example.org/article')
    finally:
        gateway.close()


def test_precision_api_keeps_authorization_off_signed_uploads_and_downloads(tmp_path):
    archive = BytesIO()
    with zipfile.ZipFile(archive, 'w') as zip:
        zip.writestr('result/full.md', '# 标题\n![](images/a.png)')
        zip.writestr('result/images/a.png', PNG)
    calls = []
    def handler(request):
        calls.append(request)
        if request.url.host == 'mineru.net':
            assert request.headers['authorization'] == 'Bearer test-secret'
            if request.method == 'POST':
                assert json.loads(request.content)['model_version'] == 'vlm'
                return httpx.Response(200, json={'code': 0, 'data': {'batch_id': 'batch-task', 'file_urls': ['https://oss-mineru.openxlab.org.cn/upload']}})
            return httpx.Response(200, json={'code': 0, 'data': {'extract_result': [{'state': 'done', 'full_zip_url': 'https://cdn-mineru.openxlab.org.cn/result.zip'}]}})
        assert 'authorization' not in request.headers
        return httpx.Response(200, content=archive.getvalue() if request.method == 'GET' else b'')
    gateway = MinerUClient(Config('test-secret'), transport=httpx.MockTransport(handler))
    source = tmp_path / 'input.pdf'
    source.write_bytes(b'%PDF')
    remote = gateway.submit('input.pdf')
    gateway.upload(remote['upload_url'], source)
    markdown, assets, _ = gateway.result(gateway.poll(remote))
    assert markdown.startswith('# 标题') and assets['images/a.png'] == PNG
    assert len(calls) == 4
    gateway.close()


def test_signed_agent_upload_and_result_protocol(tmp_path):
    def handler(request):
        assert 'authorization' not in request.headers
        if request.url.path == '/api/v1/agent/parse/file':
            assert json.loads(request.content)['file_name'] == 'sample.docx'
            return httpx.Response(200, json={'code': 0, 'data': {'task_id': 'agent-task', 'file_url': 'https://oss-mineru.openxlab.org.cn/upload'}})
        if request.url.path.endswith('/agent-task'):
            return httpx.Response(200, json={'code': 0, 'data': {'state': 'done', 'markdown_url': 'https://cdn-mineru.openxlab.org.cn/full.md'}})
        return httpx.Response(200, content='# MinerU\n正文'.encode() if request.method == 'GET' else b'')
    gateway = MinerUClient(Config(), transport=httpx.MockTransport(handler))
    source = tmp_path / 'file'; source.write_bytes(b'docx')
    remote = gateway.submit('sample.docx')
    gateway.upload(remote['upload_url'], source)
    assert gateway.result(gateway.poll(remote))[0] == '# MinerU\n正文'
    gateway.close()


def test_network_interruption_retries_without_resubmitting_document(tmp_path, monkeypatch):
    class InterruptedMinerU(FakeMinerU):
        submitted = 0
        polls = 0
        downloads = 0
        def submit(self, filename, **kwargs):
            type(self).submitted += 1
            return super().submit(filename, **kwargs)
        def poll(self, remote):
            type(self).polls += 1
            if self.polls == 1:
                raise httpx.ReadTimeout('temporary interruption')
            return super().poll(remote)
        def result(self, data):
            type(self).downloads += 1
            if self.downloads == 1:
                raise httpx.ConnectError('temporary interruption')
            return super().result(data)
    store = MarkdownStore(tmp_path / 'content'); store.initialize()
    manager = ImportManager(lambda: store, tmp_path / 'jobs', config=Config(), client_factory=InterruptedMinerU)
    monkeypatch.setattr(manager.stop, 'wait', lambda seconds: False)
    job = manager.create('ideas', '网络中断.pdf', upload=BytesIO(b'%PDF'))
    manager.run(job['id'])
    assert manager.public(job['id'])['state'] == 'done'
    assert InterruptedMinerU.submitted == 1
    assert InterruptedMinerU.polls == InterruptedMinerU.downloads == 2


def test_job_resume_and_commit_are_idempotent(tmp_path):
    store = MarkdownStore(tmp_path / 'content'); store.initialize()
    manager = ImportManager(lambda: store, tmp_path / 'jobs', config=Config(), client_factory=FakeMinerU)
    job = manager.create('ideas', '复原.pdf', upload=BytesIO(b'%PDF'))
    manager.update(job['id'], remote={'kind': 'agent', 'id': 'existing-task'}, uploaded=True)
    manager.run(job['id'])
    first = manager.public(job['id'])
    assert first['state'] == 'done'
    manager.run(job['id'])
    assert manager.public(job['id'])['note']['id'] == first['note']['id']
    repeat = store.import_document('ideas', '不应重复', '不应创建', job_id=job['id'])
    assert repeat['id'] == first['note']['id']


@pytest.mark.parametrize('value', ['file:///etc/passwd', 'http://localhost/a', 'http://10.0.0.1/a', 'https://user:password@example.com/a', 'http://[::1]/a'])
def test_private_or_credential_urls_rejected(value):
    with pytest.raises(MinerUError):
        public_url(value)


def test_archives_and_result_urls_cannot_escape_storage():
    output = BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('full.md', '正文')
        archive.writestr('../escape.png', PNG)
    with pytest.raises(MinerUError):
        unpack_archive(output.getvalue())
    with pytest.raises(MinerUError):
        trusted_result_url('http://127.0.0.1/secret')
    with pytest.raises(MinerUError):
        trusted_result_url('https://untrusted.example/download')
