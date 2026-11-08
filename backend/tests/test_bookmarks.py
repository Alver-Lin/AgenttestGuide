import hashlib
import json

import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.storage import MarkdownStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", MarkdownStore(tmp_path / "content"))
    with TestClient(main.app) as client:
        yield client


def payload(title=""):
    return {
        "title": title,
        "anchor": {
            "quote": "任务完成度",
            "start": 50,
            "end": 55,
            "prefix": "除了结果是否正确",
            "suffix": "它真正解决",
        },
    }


def test_bookmark_lifecycle_persists_without_changing_markdown(client):
    note = client.get("/api/notes/welcome").json()
    file = main.store.root / note["path"]
    before = hashlib.sha256(file.read_bytes()).hexdigest()
    assert client.get("/api/notes/welcome/bookmarks").json() == []
    response = client.post("/api/notes/welcome/bookmarks", json=payload("重点段落"))
    assert response.status_code == 201
    bookmark = response.json()
    assert bookmark["title"] == "重点段落" and bookmark["note_id"] == "welcome"
    stored = json.loads(main.store.bookmark_path("welcome").read_text())
    assert stored["bookmarks"][0]["anchor"] == bookmark["anchor"]
    main.initialize()
    assert client.get("/api/notes/welcome/bookmarks").json() == [bookmark]
    url = "/api/notes/welcome/bookmarks/" + bookmark["id"]
    updated = client.patch(url, json={"title": "改名后的书签"}).json()
    assert updated["title"] == "改名后的书签" and updated["anchor"] == bookmark["anchor"]
    assert client.delete(url).status_code == 204
    assert client.get("/api/notes/welcome/bookmarks").json() == []
    assert hashlib.sha256(file.read_bytes()).hexdigest() == before


def test_bookmark_defaults_title_from_quote(client):
    bookmark = client.post("/api/notes/welcome/bookmarks", json=payload()).json()
    assert bookmark["title"] == "任务完成度"


def test_bookmarks_follow_file_and_folder_renames_and_restore(client):
    bookmark = client.post("/api/notes/welcome/bookmarks", json=payload()).json()
    assert (
        client.patch(
            "/api/notes/welcome", json={"title": "改名后的文档", "notebook_id": "ideas"}
        ).status_code
        == 200
    )
    assert client.put("/api/notebooks/ideas", json={"name": "改名后的文件夹"}).status_code == 200
    assert client.get("/api/notes/welcome/bookmarks").json()[0]["id"] == bookmark["id"]
    assert client.delete("/api/notes/welcome").status_code == 204
    assert client.post("/api/notes/welcome/bookmarks", json=payload()).status_code == 409
    assert client.get("/api/notes/welcome/bookmarks").json()[0]["id"] == bookmark["id"]
    assert client.post("/api/notes/welcome/restore").status_code == 200
    assert client.get("/api/notes/welcome/bookmarks").json()[0]["id"] == bookmark["id"]
    assert client.delete("/api/notes/welcome").status_code == 204
    assert client.delete("/api/notes/welcome?permanent=true").status_code == 204
    assert not main.store.bookmark_path("welcome").exists()


def test_bookmark_validation_and_document_isolation(client):
    bookmark = client.post("/api/notes/welcome/bookmarks", json=payload()).json()
    assert client.get("/api/notes/metrics/bookmarks").json() == []
    assert client.delete("/api/notes/metrics/bookmarks/" + bookmark["id"]).status_code == 404
    for invalid in [
        {"anchor": {"quote": " ", "start": 0, "end": 1}},
        {"anchor": {"quote": "文字", "start": 4, "end": 2}},
        {"anchor": {"quote": "文字", "start": -1, "end": 2}},
    ]:
        assert client.post("/api/notes/welcome/bookmarks", json=invalid).status_code == 422
    assert client.get("/api/notes/missing/bookmarks").status_code == 404
    assert client.post("/api/notes/missing/bookmarks", json=payload()).status_code == 404


def test_corrupt_bookmark_file_is_not_overwritten(client):
    client.post("/api/notes/welcome/bookmarks", json=payload())
    path = main.store.bookmark_path("welcome")
    path.write_text("broken json", encoding="utf-8")
    assert client.get("/api/notes/welcome/bookmarks").status_code == 409
    assert client.post("/api/notes/welcome/bookmarks", json=payload()).status_code == 409
    assert path.read_text() == "broken json"
