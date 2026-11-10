"""Plain Markdown files are the source of truth; JSON stores IDs, never document bodies."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
import json
import os
import re
import shutil
import sqlite3
import tempfile
import unicodedata
import uuid

from .seed import NOTEBOOKS, NOTES


class StorageError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def valid_name(value: str, *, folder=False):
    name = unicodedata.normalize("NFC", value.strip())
    if not name or name.startswith(".") or name.endswith("."):
        raise StorageError(422, "名称不能为空、以点开头或以点结尾")
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise StorageError(422, '名称不能包含 /、\\、:、*、?、"、<、>、| 或控制字符')
    if name.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
        raise StorageError(422, "请更换这个保留文件名")
    if len(name) > (40 if folder else 200) or len(name.encode("utf-8")) > 230:
        raise StorageError(422, "名称过长，请缩短后重试")
    return name


def migration_name(value, fallback):
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", unicodedata.normalize("NFC", value)).strip(" .") or fallback
    while len(name.encode("utf-8")) > 200:
        name = name[:-1]
    try:
        return valid_name(name)
    except StorageError:
        return fallback


def atomic_write(path: Path, data: bytes):
    descriptor, temporary = tempfile.mkstemp(prefix=".agenttestguide-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class MarkdownStore:
    def __init__(self, root: Path, *, legacy_db: Path | None = None, backup_dir: Path | None = None):
        self.root = Path(root).expanduser().resolve()
        self.legacy_db = Path(legacy_db) if legacy_db else None
        self.backup_dir = Path(backup_dir) if backup_dir else self.root.parent / "backups"
        self.lock = RLock()
        self.index = {"version": 1, "notebooks": {}, "notes": {}}

    def path(self, relative: str):
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise StorageError(422, "文件路径无效")
        path = self.root
        for component in candidate.parts:
            path = path / component
            if path.is_symlink():
                raise StorageError(409, "不支持符号链接，请使用内容目录内的普通文件和文件夹")
        if not path.resolve().is_relative_to(self.root):
            raise StorageError(422, "文件路径超出内容目录")
        return path

    @property
    def index_path(self):
        return self.path(".agenttestguide/index.json")

    def write_index(self):
        atomic_write(self.index_path, json.dumps(self.index, ensure_ascii=False, indent=2).encode("utf-8"))

    @staticmethod
    def identity(path):
        stat = path.stat()
        return [stat.st_dev, stat.st_ino]

    def initialize(self):
        with self.lock:
            if self.index_path.is_file():
                self.read_index()
                self.reconcile()
                return
            if self.root.exists() and any(self.root.iterdir()):
                self.path(".agenttestguide").mkdir(exist_ok=True)
                self.reconcile()
                return
            self.root.parent.mkdir(parents=True, exist_ok=True)
            stage = Path(tempfile.mkdtemp(prefix=f".{self.root.name}-import-", dir=self.root.parent))
            try:
                migration = None
                if self.legacy_db and self.legacy_db.is_file():
                    books, notes, migration = self.read_legacy_snapshot()
                else:
                    books = [{**book, "created_at": now()} for book in NOTEBOOKS]
                    notes = [{**note, "created_at": now(), "updated_at": now(), "deleted_at": None} for note in NOTES]
                staged = MarkdownStore(stage)
                staged.path(".agenttestguide/trash").mkdir(parents=True)
                for book in books:
                    folder = self.unused_path(stage, migration_name(book["name"], "未命名文件夹"), folder=True)
                    folder.mkdir()
                    staged.index["notebooks"][book["id"]] = {
                        "path": folder.name, "color": book.get("color", "blue"),
                        "description": book.get("description", ""), "created_at": book.get("created_at", now()),
                        "identity": self.identity(folder),
                    }
                for note in notes:
                    book = staged.index["notebooks"][note["notebook_id"]]
                    name = migration_name(note["title"], "未命名文件")
                    folder = staged.path(book["path"])
                    destination = self.unused_path(folder, name)
                    metadata = {
                        "notebook_id": note["notebook_id"], "created_at": note.get("created_at", now()),
                        "tags": note.get("tags", []), "is_favorite": bool(note.get("is_favorite", False)),
                        "deleted_at": note.get("deleted_at"), "title": destination.stem,
                    }
                    if metadata["deleted_at"]:
                        metadata["original_path"] = destination.relative_to(stage).as_posix()
                        destination = staged.path(f".agenttestguide/trash/{note['id']}.md")
                    destination.write_bytes(note["content"].encode("utf-8"))
                    modified = datetime.fromisoformat(note.get("updated_at", now())).timestamp()
                    os.utime(destination, (modified, modified))
                    metadata.update(path=destination.relative_to(stage).as_posix(), identity=self.identity(destination))
                    staged.index["notes"][note["id"]] = metadata
                staged.write_index()
                if migration:
                    staged.path(".agenttestguide/migration.json").write_text(json.dumps(migration, ensure_ascii=False, indent=2), encoding="utf-8")
                if self.root.exists():
                    self.root.rmdir()  # Only an empty destination may be replaced.
                stage.rename(self.root)  # Publish the complete migration in one directory rename.
                self.read_index()
            finally:
                if stage.exists():
                    shutil.rmtree(stage)

    def read_legacy_snapshot(self):
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        filename = "evalnote-before-markdown-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{uuid.uuid4().hex[:6]}.db"
        backup = self.backup_dir / filename
        with sqlite3.connect(self.legacy_db.resolve().as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(backup) as target:
                source.backup(target)
        with sqlite3.connect(backup.resolve().as_uri() + "?mode=ro", uri=True) as snapshot:
            snapshot.row_factory = sqlite3.Row
            books = [dict(row) for row in snapshot.execute("SELECT * FROM notebooks ORDER BY created_at, rowid")]
            notes = [dict(row) for row in snapshot.execute("SELECT * FROM notes ORDER BY created_at, rowid")]
        for note in notes:
            note["tags"] = json.loads(note["tags"])
        return books, notes, {"completed_at": now(), "source": str(self.legacy_db.resolve()),
                              "backup": str(backup.resolve()), "folders": len(books), "files": len(notes)}

    def read_index(self):
        self.index = json.loads(self.index_path.read_text(encoding="utf-8"))
        if self.index.get("version") != 1:
            raise StorageError(409, "不支持这个版本的文件索引")

    @staticmethod
    def unused_path(parent: Path, name: str, *, folder=False):
        if not folder and name.lower().endswith(".md"):
            name = name[:-3] or "未命名文件"
        suffix = "" if folder else ".md"
        candidate = parent / (name + suffix)
        count = 2
        while candidate.exists() or candidate.is_symlink():
            candidate = parent / f"{name} ({count}){suffix}"
            count += 1
        return candidate

    HIDDEN_DIR_NAMES = {"_assets", "images", "image"}

    def iter_notebook_dirs(self):
        """Yield content folders depth-first; skip hidden dirs and media folders."""
        directories = []
        stack = [self.root]
        while stack:
            current = stack.pop()
            children = []
            for child in current.iterdir():
                if (
                    child.name.startswith(".")
                    or child.name in self.HIDDEN_DIR_NAMES
                    or child.is_symlink()
                    or not child.is_dir()
                ):
                    continue
                children.append(child)
            children.sort(key=lambda path: path.name.casefold())
            for child in children:
                directories.append(child)
                stack.append(child)
        directories.sort(key=lambda path: (len(path.relative_to(self.root).parts), path.as_posix().casefold()))
        return directories

    def reconcile(self):
        """Observe native editor changes without copying bodies to the metadata index."""
        before = json.dumps(self.index, sort_keys=True, ensure_ascii=False)
        old_books, old_notes = self.index["notebooks"], self.index["notes"]
        books, notes = {}, {}
        for directory in self.iter_notebook_dirs():
            relative = directory.relative_to(self.root).as_posix()
            identity = self.identity(directory)
            match = next(((key, value) for key, value in old_books.items() if value["path"] == relative), None)
            if not match:
                match = next(((key, value) for key, value in old_books.items() if value.get("identity") == identity and not self.path(value["path"]).exists()), None)
            book_id, metadata = match if match else (str(uuid.uuid4()), {"color": "blue", "description": "", "created_at": timestamp(directory.stat().st_ctime)})
            books[book_id] = {**metadata, "path": relative, "identity": identity}
            for file in sorted(directory.iterdir(), key=lambda path: path.name.casefold()):
                if file.name.startswith(".") or file.is_symlink() or not file.is_file() or file.suffix.lower() != ".md":
                    continue
                note_relative, file_identity = file.relative_to(self.root).as_posix(), self.identity(file)
                match = next(((key, value) for key, value in old_notes.items() if not value.get("deleted_at") and value["path"] == note_relative), None)
                if not match:
                    match = next(((key, value) for key, value in old_notes.items() if not value.get("deleted_at") and value.get("identity") == file_identity and not self.path(value["path"]).exists()), None)
                note_id, metadata = match if match else (str(uuid.uuid4()), {"created_at": timestamp(file.stat().st_ctime), "tags": [], "is_favorite": False, "deleted_at": None})
                notes[note_id] = {**metadata, "path": note_relative, "notebook_id": book_id, "title": file.stem, "identity": file_identity}
        for note_id, metadata in old_notes.items():
            if metadata.get("deleted_at") and self.path(metadata["path"]).is_file():
                notes[note_id] = metadata
                book_id = metadata["notebook_id"]
                if book_id not in books and book_id in old_books:
                    books[book_id] = old_books[book_id]
        for book_id, metadata in old_books.items():
            if metadata.get("deleted_at") and self.path(metadata["path"]).is_dir():
                books[book_id] = metadata
        self.index.update(notebooks=books, notes=notes)
        if before != json.dumps(self.index, sort_keys=True, ensure_ascii=False) or not self.index_path.exists():
            self.write_index()

    @contextmanager
    def transaction(self):
        with self.lock:
            self.read_index()
            self.reconcile()
            yield

    def folder(self, folder_id, *, include_deleted=False):
        item = self.index["notebooks"].get(folder_id)
        if item is None or (item.get("deleted_at") and not include_deleted):
            raise StorageError(404, "文件夹不存在")
        return item

    def note(self, note_id):
        item = self.index["notes"].get(note_id)
        if item is None:
            raise StorageError(404, "文件不存在")
        return item

    def parent_id_for(self, folder_id, *, include_deleted=False):
        item = self.folder(folder_id, include_deleted=include_deleted)
        parent_path = Path(item["path"]).parent.as_posix()
        if parent_path in {".", ""}:
            return None
        for key, book in self.index["notebooks"].items():
            if book.get("deleted_at") and not include_deleted:
                continue
            if book["path"] == parent_path:
                return key
        return None

    def descendant_folder_ids(self, folder_id, *, include_self=True):
        root = self.folder(folder_id, include_deleted=True)["path"]
        ids = []
        for key, book in self.index["notebooks"].items():
            path = book["path"]
            if path == root or path.startswith(root + "/"):
                if include_self or path != root:
                    ids.append(key)
        return ids

    def folder_data(self, folder_id):
        item = self.folder(folder_id)
        return {"id": folder_id, "name": Path(item["path"]).name, "color": item["color"],
                "description": item["description"], "created_at": item["created_at"], "path": item["path"],
                "parent_id": self.parent_id_for(folder_id)}

    def note_data(self, note_id):
        item = self.note(note_id)
        path = self.path(item["path"])
        return {"id": note_id, "notebook_id": item["notebook_id"], "title": item["title"],
                "content": path.read_bytes().decode("utf-8-sig"), "tags": item["tags"],
                "is_favorite": item["is_favorite"], "deleted_at": item.get("deleted_at"),
                "created_at": item["created_at"], "updated_at": timestamp(path.stat().st_mtime), "path": item["path"],
                **({"imported_from": item["imported_from"]} if item.get("imported_from") else {})}

    def bootstrap(self):
        with self.transaction():
            return {"notebooks": [self.folder_data(key) for key, book in self.index["notebooks"].items() if not book.get("deleted_at") and self.path(book["path"]).is_dir()],
                    "notes": sorted([self.note_data(key) for key in self.index["notes"]], key=lambda note: note["updated_at"], reverse=True),
                    "storage": {"type": "markdown", "directory": str(self.root)}}

    def create_folder(self, payload):
        with self.transaction():
            name = valid_name(payload["name"], folder=True)
            if name in self.HIDDEN_DIR_NAMES:
                raise StorageError(422, "images、image、_assets 为资源目录，不能作为普通文件夹")
            parent_id = payload.get("parent_id") or None
            if parent_id:
                parent = self.folder(parent_id)
                relative = f"{parent['path']}/{name}"
            else:
                relative = name
            destination = self.path(relative)
            if destination.exists():
                raise StorageError(409, "同名文件夹已存在")
            destination.mkdir(parents=False)
            folder_id = str(uuid.uuid4())
            self.index["notebooks"][folder_id] = {
                "path": relative,
                "color": payload.get("color", "blue"),
                "description": payload.get("description", ""),
                "created_at": now(),
                "identity": self.identity(destination),
            }
            self.write_index()
            return self.folder_data(folder_id)

    def rewrite_prefix(self, value, old_prefix, new_prefix):
        if value == old_prefix:
            return new_prefix
        if value.startswith(old_prefix + "/"):
            return new_prefix + value[len(old_prefix):]
        return value

    def update_folder(self, folder_id, payload):
        with self.transaction():
            item = self.folder(folder_id)
            old_path = item["path"]
            leaf = valid_name(payload.get("name", Path(old_path).name), folder=True)
            if leaf in self.HIDDEN_DIR_NAMES:
                raise StorageError(422, "images、image、_assets 为资源目录，不能作为普通文件夹")
            if "parent_id" in payload:
                parent_id = payload.get("parent_id") or None
                if parent_id == folder_id:
                    raise StorageError(409, "不能移动到自身")
                if parent_id:
                    parent = self.folder(parent_id)
                    if parent["path"] == old_path or parent["path"].startswith(old_path + "/"):
                        raise StorageError(409, "不能移动到自己的子文件夹中")
                    new_path = f"{parent['path']}/{leaf}"
                else:
                    new_path = leaf
            else:
                parent = Path(old_path).parent
                new_path = leaf if parent.as_posix() in {".", ""} else f"{parent.as_posix()}/{leaf}"
            if new_path != old_path:
                source, destination = self.path(old_path), self.path(new_path)
                if destination.exists() and not destination.samefile(source):
                    raise StorageError(409, "同名文件夹已存在")
                source.rename(destination)
                affected = set(self.descendant_folder_ids(folder_id))
                for book in self.index["notebooks"].values():
                    book["path"] = self.rewrite_prefix(book["path"], old_path, new_path)
                    if book.get("original_path"):
                        book["original_path"] = self.rewrite_prefix(book["original_path"], old_path, new_path)
                for note in self.index["notes"].values():
                    if note["notebook_id"] not in affected and not (
                        note.get("path", "").startswith(old_path + "/")
                        or note.get("original_path", "").startswith(old_path + "/")
                    ):
                        continue
                    for field in ("path", "original_path", "asset_dir"):
                        if note.get(field):
                            note[field] = self.rewrite_prefix(note[field], old_path, new_path)
            item.update(color=payload.get("color", item.get("color", "blue")),
                        description=payload.get("description", item.get("description", "")))
            self.write_index()
            return self.folder_data(folder_id)

    def delete_folder(self, folder_id, *, recursive=False):
        with self.transaction():
            item = self.folder(folder_id)
            if recursive:
                old_path = item["path"]
                archive_path = f".agenttestguide/trash/folders/{folder_id}"
                source, destination = self.path(old_path), self.path(archive_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.rename(destination)
                deleted_at = now()
                affected = set(self.descendant_folder_ids(folder_id))
                for book_id in affected:
                    book = self.index["notebooks"][book_id]
                    book_old = book["path"]
                    book.update(
                        path=self.rewrite_prefix(book_old, old_path, archive_path),
                        original_path=book_old,
                        deleted_at=deleted_at,
                    )
                    if book_id != folder_id:
                        book["deleted_with_folder"] = folder_id
                for note in self.index["notes"].values():
                    if note["notebook_id"] not in affected:
                        continue
                    if not note.get("deleted_at"):
                        note.update(
                            original_path=note["path"],
                            path=self.rewrite_prefix(note["path"], old_path, archive_path),
                            deleted_at=deleted_at,
                            deleted_with_folder=True,
                        )
                    elif note.get("path"):
                        note["path"] = self.rewrite_prefix(note["path"], old_path, archive_path)
                    if note.get("asset_dir"):
                        note["asset_dir"] = self.rewrite_prefix(note["asset_dir"], old_path, archive_path)
                try:
                    self.write_index()
                except Exception:
                    destination.rename(source)
                    self.read_index()
                    raise
                return
            if any(note["notebook_id"] == folder_id for note in self.index["notes"].values()):
                raise StorageError(409, "请先移动该文件夹中的文件，并清理对应回收站文件")
            if any(
                book["path"].startswith(item["path"] + "/")
                for book in self.index["notebooks"].values()
                if not book.get("deleted_at")
            ):
                raise StorageError(409, "请先删除或移出子文件夹")
            active_roots = [
                book for book in self.index["notebooks"].values()
                if not book.get("deleted_at") and Path(book["path"]).parent.as_posix() in {".", ""}
            ]
            if len(active_roots) <= 1 and Path(item["path"]).parent.as_posix() in {".", ""}:
                raise StorageError(409, "至少需要保留一个文件夹")
            directory = self.path(item["path"])
            if any(directory.iterdir()):
                raise StorageError(409, "文件夹中还有其他文件，无法删除")
            directory.rmdir()
            del self.index["notebooks"][folder_id]
            self.write_index()

    def restore_folder(self, folder_id):
        with self.transaction():
            item = self.folder(folder_id, include_deleted=True)
            if item.get("deleted_at"):
                archive_path, original_path = item["path"], item["original_path"]
                source, destination = self.path(archive_path), self.path(original_path)
                if destination.exists():
                    raise StorageError(409, "原位置已有同名文件夹，请先重命名该文件夹后重试")
                parent = destination.parent
                if parent != self.root and not parent.exists():
                    raise StorageError(409, "请先恢复上级文件夹")
                source.rename(destination)
                affected = [
                    key for key, book in self.index["notebooks"].items()
                    if key == folder_id or book.get("deleted_with_folder") == folder_id
                ]
                for book_id in affected:
                    book = self.index["notebooks"][book_id]
                    book_archive = book["path"]
                    book_original = book.pop("original_path")
                    book.update(path=book_original)
                    book.pop("deleted_at", None)
                    book.pop("deleted_with_folder", None)
                    for note in self.index["notes"].values():
                        if note["notebook_id"] != book_id:
                            continue
                        if note.pop("deleted_with_folder", False):
                            note.update(path=note.pop("original_path"), deleted_at=None)
                        if note.get("asset_dir"):
                            note["asset_dir"] = self.rewrite_prefix(
                                note["asset_dir"], book_archive, book_original
                            )
                try:
                    self.write_index()
                except Exception:
                    destination.rename(source)
                    self.read_index()
                    raise
            root_path = self.index["notebooks"][folder_id]["path"]
            restored_ids = [
                key for key, book in self.index["notebooks"].items()
                if not book.get("deleted_at")
                and (book["path"] == root_path or book["path"].startswith(root_path + "/"))
            ]
            return {
                "notebook": self.folder_data(folder_id),
                "notebooks": [self.folder_data(key) for key in restored_ids],
                "notes": [
                    self.note_data(key)
                    for key, note in self.index["notes"].items()
                    if note["notebook_id"] in restored_ids and not note.get("deleted_at")
                ],
            }

    def create_note(self, payload):
        with self.transaction():
            book = self.folder(payload["notebook_id"])
            title = valid_name(payload["title"].strip() or "未命名文件")
            filename = title if title.lower().endswith(".md") else title + ".md"
            path = self.path(book["path"] + "/" + filename)
            if path.exists():
                raise StorageError(409, "同名文件已存在，请更换名称")
            with path.open("xb") as stream:
                stream.write(payload["content"].encode("utf-8"))
            note_id = str(uuid.uuid4())
            self.index["notes"][note_id] = {"path": path.relative_to(self.root).as_posix(), "notebook_id": payload["notebook_id"],
                "title": path.stem, "created_at": now(), "deleted_at": None, "tags": [], "is_favorite": False, "identity": self.identity(path)}
            self.write_index()
            return self.note_data(note_id)

    def read_note(self, note_id):
        with self.transaction():
            return self.note_data(note_id)

    def update_note(self, note_id, updates):
        with self.transaction():
            item = self.note(note_id)
            if item.get("deleted_at"):
                raise StorageError(409, "请先恢复文件再编辑")
            book_id = updates.get("notebook_id", item["notebook_id"])
            book = self.folder(book_id)
            title = valid_name(updates.get("title", item["title"]).strip() or "未命名笔记")
            filename = title if title.lower().endswith(".md") else title + ".md"
            source = self.path(item["path"])
            destination = self.path(book["path"] + "/" + filename)
            if destination != source:
                if destination.exists() and not destination.samefile(source):
                    raise StorageError(409, "同名文件已存在，请更换名称")
                source.rename(destination)
                if book_id != item["notebook_id"] and item.get("asset_dir"):
                    previous_assets = self.path(item["asset_dir"])
                    next_assets = self.path(book["path"] + f"/_assets/{note_id}")
                    try:
                        next_assets.parent.mkdir(exist_ok=True)
                        if next_assets.exists():
                            raise StorageError(409, "目标位置已有该文档的资源目录")
                        previous_assets.rename(next_assets)
                    except Exception:
                        destination.rename(source)
                        raise
                    item["asset_dir"] = next_assets.relative_to(self.root).as_posix()
                    try:
                        previous_assets.parent.rmdir()
                    except OSError:
                        pass
            if "content" in updates:
                atomic_write(destination, updates["content"].encode("utf-8"))
            elif updates:
                os.utime(destination, None)
            item.update(path=destination.relative_to(self.root).as_posix(), title=destination.stem,
                        notebook_id=book_id, identity=self.identity(destination))
            for key in ("tags", "is_favorite"):
                if key in updates:
                    item[key] = updates[key]
            self.write_index()
            return self.note_data(note_id)

    def delete_note(self, note_id, *, permanent=False):
        with self.transaction():
            item = self.note(note_id)
            source = self.path(item["path"])
            if permanent:
                if not item.get("deleted_at"):
                    raise StorageError(409, "仅可永久删除回收站中的文件")
                source.unlink()
                self.comment_path(note_id).unlink(missing_ok=True)
                self.bookmark_path(note_id).unlink(missing_ok=True)
                if item.get("asset_dir"):
                    assets = self.path(item["asset_dir"])
                    if assets.name == note_id and assets.parent.name == "_assets" and assets.is_dir():
                        shutil.rmtree(assets)
                        try:
                            assets.parent.rmdir()
                        except OSError:
                            pass
                original = self.path(f".agenttestguide/imports/{note_id}")
                if original.is_dir():
                    shutil.rmtree(original)
                del self.index["notes"][note_id]
            elif not item.get("deleted_at"):
                trash = self.path(".agenttestguide/trash")
                trash.mkdir(exist_ok=True)
                destination = self.path(f".agenttestguide/trash/{note_id}.md")
                source.rename(destination)
                item.update(original_path=item["path"], path=destination.relative_to(self.root).as_posix(), deleted_at=now())
            self.write_index()

    def restore_note(self, note_id):
        with self.transaction():
            item = self.note(note_id)
            if item.get("deleted_at"):
                if self.folder(item["notebook_id"], include_deleted=True).get("deleted_at"):
                    raise StorageError(409, "请先恢复该文件所在的文件夹")
                destination = self.path(item["original_path"])
                if destination.exists():
                    raise StorageError(409, "原位置已有同名文件，请先重命名该文件")
                destination.parent.mkdir(exist_ok=True)
                self.path(item["path"]).rename(destination)
                item.update(path=item.pop("original_path"), deleted_at=None, identity=self.identity(destination))
                self.write_index()
            return self.note_data(note_id)

    def comment_path(self, note_id):
        return self.path(f".agenttestguide/comments/{note_id}.json")

    def bookmark_path(self, note_id):
        return self.path(f".agenttestguide/bookmarks/{note_id}.json")

    def import_document(self, notebook_id, title, content, *, job_id, assets=None, source=None, filename="", url=""):
        from .mineru import IMAGES, rewrite_links
        assets = assets or {}
        if len(content) > 500_000:
            raise StorageError(422, "转换后的文档超过 50 万字符，请拆分后导入")
        with self.transaction():
            for identifier, metadata in self.index["notes"].items():
                if metadata.get("imported_from", {}).get("job_id") == job_id:
                    return self.note_data(identifier)
            book = self.folder(notebook_id)
            path = self.unused_path(self.path(book["path"]), migration_name(title, "导入文档"))
            identifier = str(uuid.uuid4())
            asset_dir = self.path(book["path"] + f"/_assets/{identifier}")
            original_dir = self.path(f".agenttestguide/imports/{identifier}")
            wrote_file = False
            try:
                mapping = {}
                for relative, body in assets.items():
                    candidate = Path(relative)
                    if candidate.is_absolute() or ".." in candidate.parts or candidate.suffix.lower() not in IMAGES:
                        raise StorageError(422, "解析结果包含不支持的资源路径")
                    target = self.path(asset_dir.relative_to(self.root).as_posix() + "/" + candidate.as_posix())
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(body)
                    mapping[relative] = f"_assets/{identifier}/{candidate.as_posix()}"
                markdown = rewrite_links(content, mapping)
                imported = {"filename": filename, "format": Path(filename).suffix.lower().lstrip(".") or "url", "imported_at": now(), "job_id": job_id, "has_original": bool(source)}
                if url:
                    imported["url"] = url
                if source:
                    original_dir.mkdir(parents=True)
                    original_path = original_dir / migration_name(filename, "原文件")
                    shutil.copyfile(source, original_path)
                    imported["source_path"] = original_path.relative_to(self.root).as_posix()
                with path.open("xb") as stream:
                    wrote_file = True
                    stream.write(markdown.encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                metadata = {"path": path.relative_to(self.root).as_posix(), "notebook_id": notebook_id, "title": path.stem,
                            "created_at": now(), "deleted_at": None, "tags": [], "is_favorite": False,
                            "identity": self.identity(path), "imported_from": imported}
                if assets:
                    metadata["asset_dir"] = asset_dir.relative_to(self.root).as_posix()
                self.index["notes"][identifier] = metadata
                self.write_index()
                return self.note_data(identifier)
            except Exception:
                if wrote_file:
                    path.unlink(missing_ok=True)
                for directory in (asset_dir, original_dir):
                    if directory.exists():
                        shutil.rmtree(directory)
                if asset_dir.parent.is_dir() and not any(asset_dir.parent.iterdir()):
                    asset_dir.parent.rmdir()
                self.index["notes"].pop(identifier, None)
                raise

    def imported_file(self, note_id, asset=None):
        with self.transaction():
            item = self.note(note_id)
            if asset is not None:
                if not item.get("asset_dir"):
                    raise StorageError(404, "资源不存在")
                root = self.path(item["asset_dir"])
                path = self.path(item["asset_dir"] + "/" + asset)
                if not path.is_relative_to(root):
                    raise StorageError(422, "资源路径无效")
                from .mineru import IMAGES
                if path.suffix.lower() not in IMAGES:
                    raise StorageError(404, "资源不存在")
                name = path.name
            else:
                original = item.get("imported_from", {})
                if not original.get("source_path"):
                    raise StorageError(404, "该文档没有本地原文件")
                path, name = self.path(original["source_path"]), original["filename"]
            if not path.is_file():
                raise StorageError(404, "文件不存在")
            return path, name

    def add_image(self, note_id, data: bytes, *, filename='图片'):
        from .images import MAX_IMAGE_BYTES, image_extension
        if not data:
            raise StorageError(422, "图片内容为空，请重新选择")
        if len(data) > MAX_IMAGE_BYTES:
            raise StorageError(413, "单张图片不能超过 10 MB")
        extension = image_extension(data)
        if not extension:
            raise StorageError(422, "请选择 PNG、JPEG、GIF 或 WebP 图片")
        with self.transaction():
            item = self.note(note_id)
            if item.get("deleted_at"):
                raise StorageError(409, "请先恢复文件再插入图片")
            book = self.folder(item["notebook_id"])
            relative_dir = book["path"] + f"/_assets/{note_id}"
            directory = self.path(relative_dir)
            directory.mkdir(parents=True, exist_ok=True)
            name = uuid.uuid4().hex + extension
            target = self.path(relative_dir + '/' + name)
            previous = item.get('asset_dir')
            created = False
            try:
                with target.open('xb') as stream:
                    created = True
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                item['asset_dir'] = relative_dir
                self.write_index()
            except Exception:
                if created:
                    target.unlink(missing_ok=True)
                if previous is None:
                    item.pop('asset_dir', None)
                else:
                    item['asset_dir'] = previous
                raise
            return {"path": f"_assets/{note_id}/{name}",
                    "name": Path(filename.replace('\\', '/')).stem or '图片'}

    def relative_image(self, note_id, source: str):
        """Resolve Markdown paths relative to the note, confined to visible content files."""
        from urllib.parse import unquote, urlsplit
        with self.transaction():
            item = self.note(note_id)
            if item.get('deleted_at'):
                raise StorageError(409, "请先恢复文件再查看相对路径图片")
            try:
                url = urlsplit(source.strip())
            except ValueError:
                raise StorageError(422, "图片路径无效")
            if url.scheme or url.netloc:
                raise StorageError(422, "请使用内容目录内的图片路径")
            relative = unquote(url.path).replace('\\', '/')
            if not relative or '\x00' in relative or relative.startswith('//'):
                raise StorageError(422, "图片路径无效")
            # A leading slash refers to the content root, never the system filesystem.
            candidate = Path(relative.lstrip('/')) if relative.startswith('/') else Path(item['path']).parent / relative
            normalized = Path(os.path.normpath(candidate.as_posix()))
            if any(part.startswith('.') for part in normalized.parts):
                raise StorageError(422, "图片路径不能超出内容目录或访问隐藏目录")
            path = self.path(normalized.as_posix())
            from .mineru import IMAGES
            if path.suffix.lower() not in IMAGES or not path.is_file():
                raise StorageError(404, "图片未找到，请检查路径是否相对于当前 Markdown 文件，并确认图片已放入 content 目录")
            return path

    def read_comments(self, note_id):
        path = self.comment_path(note_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("comments"), list):
                raise ValueError("invalid comment data")
            if any(not isinstance(item, dict) or not isinstance(item.get("id"), str)
                   or not isinstance(item.get("body"), str) or not isinstance(item.get("anchor"), dict)
                   for item in data["comments"]):
                raise ValueError("invalid comment record")
            return data["comments"]
        except (ValueError, TypeError):
            raise StorageError(409, "评论文件无法读取，请检查文件内容，原文件未被覆盖")

    def write_comments(self, note_id, comments):
        path = self.comment_path(note_id)
        path.parent.mkdir(exist_ok=True)
        atomic_write(path, json.dumps({"version": 1, "note_id": note_id, "comments": comments}, ensure_ascii=False, indent=2).encode("utf-8"))

    def require_editable_note(self, note_id):
        item = self.note(note_id)
        if item.get("deleted_at"):
            raise StorageError(409, "请先恢复文件再修改")

    def list_comments(self, note_id):
        with self.transaction():
            self.note(note_id)
            return self.read_comments(note_id)

    def create_comment(self, note_id, payload):
        with self.transaction():
            self.require_editable_note(note_id)
            comments = self.read_comments(note_id)
            if len(comments) >= 500:
                raise StorageError(409, "单篇文档最多保存 500 条评论")
            comment = {"id": str(uuid.uuid4()), "note_id": note_id, "body": payload["body"],
                       "anchor": payload["anchor"], "created_at": now(), "updated_at": now()}
            comments.append(comment)
            self.write_comments(note_id, comments)
            return comment

    def update_comment(self, note_id, comment_id, body):
        with self.transaction():
            self.require_editable_note(note_id)
            comments = self.read_comments(note_id)
            comment = next((item for item in comments if item["id"] == comment_id), None)
            if comment is None:
                raise StorageError(404, "评论不存在")
            comment.update(body=body, updated_at=now())
            self.write_comments(note_id, comments)
            return comment

    def delete_comment(self, note_id, comment_id):
        with self.transaction():
            self.require_editable_note(note_id)
            comments = self.read_comments(note_id)
            remaining = [item for item in comments if item["id"] != comment_id]
            if len(remaining) == len(comments):
                raise StorageError(404, "评论不存在")
            self.write_comments(note_id, remaining)

    def read_bookmarks(self, note_id):
        path = self.bookmark_path(note_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("bookmarks"), list):
                raise ValueError("invalid bookmark data")
            if any(not isinstance(item, dict) or not isinstance(item.get("id"), str)
                   or not isinstance(item.get("anchor"), dict)
                   for item in data["bookmarks"]):
                raise ValueError("invalid bookmark record")
            return data["bookmarks"]
        except (ValueError, TypeError):
            raise StorageError(409, "书签文件无法读取，请检查文件内容，原文件未被覆盖")

    def write_bookmarks(self, note_id, bookmarks):
        path = self.bookmark_path(note_id)
        path.parent.mkdir(exist_ok=True)
        atomic_write(path, json.dumps({"version": 1, "note_id": note_id, "bookmarks": bookmarks}, ensure_ascii=False, indent=2).encode("utf-8"))

    def list_bookmarks(self, note_id):
        with self.transaction():
            self.note(note_id)
            return self.read_bookmarks(note_id)

    def create_bookmark(self, note_id, payload):
        with self.transaction():
            self.require_editable_note(note_id)
            bookmarks = self.read_bookmarks(note_id)
            if len(bookmarks) >= 500:
                raise StorageError(409, "单篇文档最多保存 500 个书签")
            quote = payload["anchor"]["quote"].strip()
            title = (payload.get("title") or quote[:40]).strip() or quote[:40]
            bookmark = {"id": str(uuid.uuid4()), "note_id": note_id, "title": title,
                        "anchor": payload["anchor"], "created_at": now(), "updated_at": now()}
            bookmarks.append(bookmark)
            self.write_bookmarks(note_id, bookmarks)
            return bookmark

    def update_bookmark(self, note_id, bookmark_id, title):
        with self.transaction():
            self.require_editable_note(note_id)
            bookmarks = self.read_bookmarks(note_id)
            bookmark = next((item for item in bookmarks if item["id"] == bookmark_id), None)
            if bookmark is None:
                raise StorageError(404, "书签不存在")
            bookmark.update(title=title, updated_at=now())
            self.write_bookmarks(note_id, bookmarks)
            return bookmark

    def delete_bookmark(self, note_id, bookmark_id):
        with self.transaction():
            self.require_editable_note(note_id)
            bookmarks = self.read_bookmarks(note_id)
            remaining = [item for item in bookmarks if item["id"] != bookmark_id]
            if len(remaining) == len(bookmarks):
                raise StorageError(404, "书签不存在")
            self.write_bookmarks(note_id, remaining)
