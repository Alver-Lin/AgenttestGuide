import pytest
from fastapi.testclient import TestClient
from backend import main
from backend.storage import MarkdownStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "store", MarkdownStore(tmp_path / "content"))
    with TestClient(main.app) as client:
        yield client


def test_move_folder_under_another_folder(client):
    parent = client.post("/api/notebooks", json={"name": "目标父级"}).json()
    moving = client.post("/api/notebooks", json={"name": "待移动"}).json()
    note = client.post(
        "/api/notes", json={"notebook_id": moving["id"], "title": "随文件夹走"}
    ).json()
    moved = client.put(
        f"/api/notebooks/{moving['id']}",
        json={"name": "待移动", "parent_id": parent["id"]},
    ).json()
    assert moved["parent_id"] == parent["id"]
    assert moved["path"] == "目标父级/待移动"
    assert (main.store.root / "目标父级" / "待移动" / "随文件夹走.md").is_file()
    assert client.get(f"/api/notes/{note['id']}").json()["path"] == "目标父级/待移动/随文件夹走.md"


def test_move_folder_to_root(client):
    parent = client.post("/api/notebooks", json={"name": "外层"}).json()
    child = client.post(
        "/api/notebooks", json={"name": "内层", "parent_id": parent["id"]}
    ).json()
    moved = client.put(
        f"/api/notebooks/{child['id']}",
        json={"name": "内层", "parent_id": None},
    ).json()
    assert moved["parent_id"] is None
    assert moved["path"] == "内层"
    assert (main.store.root / "内层").is_dir()


def test_cannot_move_folder_into_its_descendant(client):
    parent = client.post("/api/notebooks", json={"name": "祖先"}).json()
    child = client.post(
        "/api/notebooks", json={"name": "后代", "parent_id": parent["id"]}
    ).json()
    assert (
        client.put(
            f"/api/notebooks/{parent['id']}",
            json={"name": "祖先", "parent_id": child["id"]},
        ).status_code
        == 409
    )


def test_move_file_between_folders(client):
    left = client.post("/api/notebooks", json={"name": "左侧"}).json()
    right = client.post("/api/notebooks", json={"name": "右侧"}).json()
    note = client.post("/api/notes", json={"notebook_id": left["id"], "title": "漂移"}).json()
    moved = client.patch(
        f"/api/notes/{note['id']}", json={"notebook_id": right["id"]}
    ).json()
    assert moved["notebook_id"] == right["id"]
    assert moved["path"] == "右侧/漂移.md"
    assert (main.store.root / "右侧" / "漂移.md").is_file()


def test_rename_without_parent_id_keeps_nesting(client):
    parent = client.post("/api/notebooks", json={"name": "父"}).json()
    child = client.post(
        "/api/notebooks", json={"name": "子", "parent_id": parent["id"]}
    ).json()
    renamed = client.put(
        f"/api/notebooks/{child['id']}",
        json={"name": "改名后的子", "color": "blue"},
    ).json()
    assert renamed["parent_id"] == parent["id"]
    assert renamed["path"] == "父/改名后的子"
