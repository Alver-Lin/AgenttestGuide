import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.storage import MarkdownStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", MarkdownStore(tmp_path / "content"))
    with TestClient(main.app) as client:
        yield client


def test_create_nested_folder_under_selected_parent(client):
    parent = client.post("/api/notebooks", json={"name": "一级目录"}).json()
    child = client.post(
        "/api/notebooks", json={"name": "二级目录", "parent_id": parent["id"]}
    ).json()
    assert child["parent_id"] == parent["id"]
    assert child["path"] == "一级目录/二级目录"
    assert child["name"] == "二级目录"
    assert (main.store.root / "一级目录" / "二级目录").is_dir()
    note = client.post(
        "/api/notes", json={"notebook_id": child["id"], "title": "子文件夹笔记"}
    ).json()
    assert note["path"] == "一级目录/二级目录/子文件夹笔记.md"
    books = client.get("/api/bootstrap").json()["notebooks"]
    nested = next(book for book in books if book["id"] == child["id"])
    assert nested["parent_id"] == parent["id"]


def test_rename_parent_rewrites_child_paths(client):
    parent = client.post("/api/notebooks", json={"name": "课程"}).json()
    child = client.post(
        "/api/notebooks", json={"name": "章节", "parent_id": parent["id"]}
    ).json()
    note = client.post(
        "/api/notes", json={"notebook_id": child["id"], "title": "笔记"}
    ).json()
    renamed = client.put(
        f"/api/notebooks/{parent['id']}", json={"name": "新课程", "color": "blue"}
    ).json()
    assert renamed["path"] == "新课程"
    books = {book["id"]: book for book in client.get("/api/bootstrap").json()["notebooks"]}
    assert books[child["id"]]["path"] == "新课程/章节"
    assert books[child["id"]]["parent_id"] == parent["id"]
    assert client.get(f"/api/notes/{note['id']}").json()["path"] == "新课程/章节/笔记.md"


def test_recursive_delete_and_restore_keeps_nested_tree(client):
    parent = client.post("/api/notebooks", json={"name": "归档根"}).json()
    child = client.post(
        "/api/notebooks", json={"name": "子目录", "parent_id": parent["id"]}
    ).json()
    note = client.post(
        "/api/notes", json={"notebook_id": child["id"], "title": "保留内容"}
    ).json()
    assert client.delete(f"/api/notebooks/{parent['id']}?recursive=true").status_code == 204
    assert client.get("/api/bootstrap").json()["notebooks"]
    assert all(
        book["id"] not in {parent["id"], child["id"]}
        for book in client.get("/api/bootstrap").json()["notebooks"]
    )
    restored = client.post(f"/api/notebooks/{parent['id']}/restore").json()
    ids = {book["id"] for book in restored["notebooks"]}
    assert parent["id"] in ids and child["id"] in ids
    assert any(item["id"] == note["id"] for item in restored["notes"])
    assert (main.store.root / "归档根" / "子目录" / "保留内容.md").is_file()


def test_reconcile_discovers_manually_created_nested_folder(client):
    parent = client.post("/api/notebooks", json={"name": "手工根"}).json()
    nested = main.store.root / "手工根" / "磁盘新建"
    nested.mkdir()
    (nested / "本地笔记.md").write_text("# hi", encoding="utf-8")
    main.initialize()
    books = {book["path"]: book for book in client.get("/api/bootstrap").json()["notebooks"]}
    assert "手工根/磁盘新建" in books
    assert books["手工根/磁盘新建"]["parent_id"] == parent["id"]
    notes = client.get("/api/bootstrap").json()["notes"]
    assert any(note["title"] == "本地笔记" for note in notes)


def test_images_and_assets_folders_are_hidden_from_tree(client):
    parent = client.post("/api/notebooks", json={"name": "图文课程"}).json()
    for name in ("images", "image", "_assets"):
        (main.store.root / "图文课程" / name).mkdir()
        (main.store.root / "图文课程" / name / "忽略.md").write_text("x", encoding="utf-8")
    visible = main.store.root / "图文课程" / "可见子目录"
    visible.mkdir()
    (visible / "正文.md").write_text("# ok", encoding="utf-8")
    main.initialize()
    paths = {book["path"] for book in client.get("/api/bootstrap").json()["notebooks"]}
    assert "图文课程/可见子目录" in paths
    assert "图文课程/images" not in paths
    assert "图文课程/image" not in paths
    assert "图文课程/_assets" not in paths
    titles = {note["title"] for note in client.get("/api/bootstrap").json()["notes"]}
    assert "正文" in titles
    assert "忽略" not in titles
    assert parent["id"] in {book["id"] for book in client.get("/api/bootstrap").json()["notebooks"]}
