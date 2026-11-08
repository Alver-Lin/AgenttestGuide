import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.storage import MarkdownStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", MarkdownStore(tmp_path / "content"))
    with TestClient(main.app) as test_client:
        yield test_client


def test_initial_material_is_seeded_once(client):
    data = client.get("/api/bootstrap").json()
    assert len(data["notes"]) == 9
    assert len(data["notebooks"]) == 4
    main.initialize()
    assert len(client.get("/api/bootstrap").json()["notes"]) == 9


def test_note_lifecycle_and_persistence(client):
    response = client.post("/api/notes", json={"notebook_id": "ideas", "title": "我的第一条理解"})
    assert response.status_code == 201
    note_id = response.json()["id"]
    changed = client.patch(f"/api/notes/{note_id}", json={
        "title": "评测实验", "content": "## 实验目标\n验证任务成功率。", "tags": [" 学习 ", "学习", "实践"], "is_favorite": True,
    }).json()
    assert changed["tags"] == ["学习", "实践"]
    assert changed["is_favorite"] is True
    assert (main.store.root / changed["path"]).read_text() == changed["content"]
    # A new application lifespan reads the same Markdown file rather than resetting it.
    with TestClient(main.app) as reopened:
        assert reopened.get(f"/api/notes/{note_id}").json()["content"] == changed["content"]
    assert client.delete(f"/api/notes/{note_id}?permanent=true").status_code == 409
    assert client.delete(f"/api/notes/{note_id}").status_code == 204
    assert client.get(f"/api/notes/{note_id}").json()["deleted_at"]
    assert client.patch(f"/api/notes/{note_id}", json={"title": "不能编辑"}).status_code == 409
    assert client.post(f"/api/notes/{note_id}/restore").json()["deleted_at"] is None
    assert client.delete(f"/api/notes/{note_id}").status_code == 204
    assert client.delete(f"/api/notes/{note_id}?permanent=true").status_code == 204
    assert client.get(f"/api/notes/{note_id}").status_code == 404


def test_notebook_management_and_foreign_keys(client):
    book = client.post("/api/notebooks", json={"name": " 我的实验 ", "color": "blue"}).json()
    assert book["name"] == "我的实验"
    assert client.put(f"/api/notebooks/{book['id']}", json={"name": "实验记录", "color": "orange"}).json()["color"] == "orange"
    note = client.post("/api/notes", json={"notebook_id": book["id"]}).json()
    assert client.delete(f"/api/notebooks/{book['id']}").status_code == 409
    assert client.patch(f"/api/notes/{note['id']}", json={"notebook_id": "missing"}).status_code == 404
    assert client.patch(f"/api/notes/{note['id']}", json={"notebook_id": "ideas"}).status_code == 200
    assert client.delete(f"/api/notebooks/{book['id']}").status_code == 204


def test_validation_and_unknown_records(client):
    assert client.post("/api/notebooks", json={"name": "   "}).status_code == 422
    assert client.post("/api/notes", json={"notebook_id": "missing"}).status_code == 404
    assert client.patch("/api/notes/welcome", json={"tags": ["a" * 25]}).status_code == 422
    assert client.patch("/api/notes/welcome", json={"tags": [str(i) for i in range(9)]}).status_code == 422
    assert client.patch("/api/notes/missing", json={"title": "test"}).status_code == 404
    assert client.patch("/api/notes/welcome", json={"title": "   "}).json()["title"] == "未命名笔记"


def test_removed_seed_does_not_return_after_restart(client):
    assert client.delete("/api/notes/welcome").status_code == 204
    assert client.delete("/api/notes/welcome?permanent=true").status_code == 204
    main.initialize()
    assert client.get("/api/notes/welcome").status_code == 404
    assert len(client.get("/api/bootstrap").json()["notes"]) == 8
