"""AgenttestGuide: real folders and Markdown files with a FastAPI editing API."""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
import os

from fastapi import FastAPI, Response, Request, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator, model_validator
from dotenv import load_dotenv

from .storage import MarkdownStore, StorageError
from .imports import ImportManager
from .mineru import MinerUError
from .images import MAX_IMAGE_BYTES

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env")
CONTENT_DIR = Path(os.getenv("AGENTTESTGUIDE_CONTENT_DIR", str(ROOT.parent / "content")))
LEGACY_DB_PATH = Path(os.getenv("EVALNOTE_DB_PATH", str(ROOT / "data" / "evalnote.db")))
store = MarkdownStore(CONTENT_DIR, legacy_db=LEGACY_DB_PATH, backup_dir=ROOT / "data" / "backups")


def initialize():
    store.initialize()


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    manager = ImportManager(lambda: store, store.root / ".agenttestguide/import-jobs")
    manager.start()
    app.state.imports = manager
    try:
        yield
    finally:
        manager.shutdown()


app = FastAPI(title="AgenttestGuide API", version="2.0.0", lifespan=lifespan,
              description="直接使用文件夹和独立 Markdown 文件保存 Agent 评测入门知识。")


@app.exception_handler(StorageError)
async def storage_error(request: Request, error: StorageError):
    return JSONResponse(status_code=error.status, content={"detail": error.detail})


@app.exception_handler(MinerUError)
async def mineru_error(request: Request, error: MinerUError):
    return JSONResponse(status_code=422, content={"detail": str(error)})


class ImportURL(BaseModel):
    notebook_id: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=4096)
    filename: str = Field(default="", max_length=200)
    is_ocr: bool = False


@app.get("/api/import/config")
def import_config(request: Request):
    return request.app.state.imports.config.public()


@app.post("/api/import/file", status_code=202)
def import_file(request: Request, notebook_id: str = Form(...), file: UploadFile = File(...), is_ocr: bool = Form(False)):
    try:
        return request.app.state.imports.create(notebook_id, file.filename or "导入文档", upload=file.file, is_ocr=is_ocr)
    finally:
        file.file.close()


@app.post("/api/import/url", status_code=202)
def import_url(request: Request, payload: ImportURL):
    return request.app.state.imports.create(payload.notebook_id, payload.filename, url=payload.url, is_ocr=payload.is_ocr)


@app.get("/api/import/jobs/{job_id}")
def import_status(request: Request, job_id: str):
    return request.app.state.imports.public(job_id)


class NotebookInput(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: Literal["green", "orange", "blue", "purple"] = "blue"
    description: str = Field(default="", max_length=200)
    parent_id: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("文件夹名称不能为空")
        return value.strip()

    @field_validator("parent_id")
    @classmethod
    def clean_parent(cls, value):
        if value is None:
            return None
        value = value.strip()
        return value or None


class NoteCreate(BaseModel):
    notebook_id: str
    title: str = Field(default="未命名文件", max_length=200)
    content: str = Field(default="", max_length=500_000)


class NotePatch(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    content: str | None = Field(default=None, max_length=500_000)
    notebook_id: str | None = None
    tags: list[str] | None = Field(default=None, max_length=8)
    is_favorite: bool | None = None

    @field_validator("tags")
    @classmethod
    def clean_tags(cls, tags):
        if tags is None:
            return tags
        cleaned = list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))
        if any(len(tag) > 24 for tag in cleaned):
            raise ValueError("标签最多 24 个字符")
        return cleaned


class CommentAnchor(BaseModel):
    quote: str = Field(min_length=1, max_length=5000)
    start: int = Field(ge=0, le=1_000_000)
    end: int = Field(ge=1, le=1_000_000)
    prefix: str = Field(default="", max_length=64)
    suffix: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def valid_selection(self):
        if not self.quote.strip() or self.end <= self.start:
            raise ValueError("请选择有效的正文内容")
        return self


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("body")
    @classmethod
    def clean_body(cls, value):
        if not value.strip():
            raise ValueError("评论不能为空")
        return value.strip()


class CommentCreate(CommentBody):
    anchor: CommentAnchor


class BookmarkCreate(BaseModel):
    anchor: CommentAnchor
    title: str = Field(default="", max_length=80)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        return value.strip()


class BookmarkBody(BaseModel):
    title: str = Field(min_length=1, max_length=80)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError("书签名称不能为空")
        return value.strip()


@app.get("/api/health")
def health():
    return {"status": "ok", "storage": "markdown"}


@app.get("/api/bootstrap")
def bootstrap():
    return store.bootstrap()


@app.post("/api/notebooks", status_code=201)
def create_notebook(payload: NotebookInput):
    return store.create_folder(payload.model_dump())


@app.put("/api/notebooks/{notebook_id}")
def update_notebook(notebook_id: str, payload: NotebookInput):
    return store.update_folder(notebook_id, payload.model_dump(exclude_unset=True))


@app.delete("/api/notebooks/{notebook_id}", status_code=204)
def delete_notebook(notebook_id: str, recursive: bool = False):
    store.delete_folder(notebook_id, recursive=recursive)
    return Response(status_code=204)


@app.post("/api/notebooks/{notebook_id}/restore")
def restore_notebook(notebook_id: str):
    return store.restore_folder(notebook_id)


@app.post("/api/notes", status_code=201)
def create_note(payload: NoteCreate):
    return store.create_note(payload.model_dump())


@app.get("/api/notes/{note_id}")
def read_note(note_id: str):
    return store.read_note(note_id)


@app.get("/api/notes/{note_id}/original")
def original_file(note_id: str):
    path, filename = store.imported_file(note_id)
    return FileResponse(path, filename=filename)


@app.get("/api/notes/{note_id}/assets/{asset_path:path}")
def document_asset(note_id: str, asset_path: str):
    path, _ = store.imported_file(note_id, asset=asset_path)
    return FileResponse(path)


@app.get("/api/notes/{note_id}/image")
def relative_document_image(note_id: str, path: str):
    return FileResponse(store.relative_image(note_id, path), headers={"X-Content-Type-Options": "nosniff"})


@app.post("/api/notes/{note_id}/images", status_code=201)
async def upload_image(note_id: str, file: UploadFile = File(...)):
    try:
        data = await file.read(MAX_IMAGE_BYTES + 1)
        return await run_in_threadpool(store.add_image, note_id, data, filename=file.filename or '图片')
    finally:
        await file.close()


@app.patch("/api/notes/{note_id}")
def update_note(note_id: str, payload: NotePatch):
    return store.update_note(note_id, payload.model_dump(exclude_none=True))


@app.delete("/api/notes/{note_id}", status_code=204)
def trash_note(note_id: str, permanent: bool = False):
    store.delete_note(note_id, permanent=permanent)
    return Response(status_code=204)


@app.post("/api/notes/{note_id}/restore")
def restore_note(note_id: str):
    return store.restore_note(note_id)


@app.get("/api/notes/{note_id}/comments")
def list_comments(note_id: str):
    return store.list_comments(note_id)


@app.post("/api/notes/{note_id}/comments", status_code=201)
def create_comment(note_id: str, payload: CommentCreate):
    return store.create_comment(note_id, payload.model_dump())


@app.patch("/api/notes/{note_id}/comments/{comment_id}")
def update_comment(note_id: str, comment_id: str, payload: CommentBody):
    return store.update_comment(note_id, comment_id, payload.body)


@app.delete("/api/notes/{note_id}/comments/{comment_id}", status_code=204)
def delete_comment(note_id: str, comment_id: str):
    store.delete_comment(note_id, comment_id)
    return Response(status_code=204)


@app.get("/api/notes/{note_id}/bookmarks")
def list_bookmarks(note_id: str):
    return store.list_bookmarks(note_id)


@app.post("/api/notes/{note_id}/bookmarks", status_code=201)
def create_bookmark(note_id: str, payload: BookmarkCreate):
    return store.create_bookmark(note_id, payload.model_dump())


@app.patch("/api/notes/{note_id}/bookmarks/{bookmark_id}")
def update_bookmark(note_id: str, bookmark_id: str, payload: BookmarkBody):
    return store.update_bookmark(note_id, bookmark_id, payload.title)


@app.delete("/api/notes/{note_id}/bookmarks/{bookmark_id}", status_code=204)
def delete_bookmark(note_id: str, bookmark_id: str):
    store.delete_bookmark(note_id, bookmark_id)
    return Response(status_code=204)


DIST = ROOT.parent / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/favicon.png", include_in_schema=False)
    def favicon():
        return FileResponse(DIST / "favicon.png")

    @app.get("/favicon-32.png", include_in_schema=False)
    def favicon_32():
        return FileResponse(DIST / "favicon-32.png")

    @app.get("/favicon-64.png", include_in_schema=False)
    def favicon_64():
        return FileResponse(DIST / "favicon-64.png")

    @app.get("/apple-touch-icon.png", include_in_schema=False)
    def apple_touch_icon():
        return FileResponse(DIST / "apple-touch-icon.png")

    @app.get("/icon.png", include_in_schema=False)
    def brand_icon():
        return FileResponse(DIST / "icon.png")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(DIST / "index.html")
