"""Durable asynchronous MinerU import jobs; browser polling never owns the conversion."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock
from urllib.parse import urlsplit
import json
import logging
import re
import uuid

import httpx
from .mineru import Config, MinerUClient, MinerUError, DIRECT_TYPES, leaf_name, public_url, read_markdown
from .storage import StorageError, atomic_write, now

logger = logging.getLogger(__name__)


class ImportManager:
    def __init__(self, store_getter, root, *, config=None, client_factory=None):
        self.store_getter = store_getter
        self.root = Path(root)
        self.config = config or Config.environment()
        self.client_factory = client_factory or MinerUClient
        self.executor = None
        self.stop = Event()
        self.lock = RLock()

    def start(self):
        self.root.mkdir(parents=True, exist_ok=True)
        self.stop.clear()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mineru-import")
        for path in self.root.glob("*/job.json"):
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                if job["state"] in {"pending", "running"}:
                    self.executor.submit(self.run, job["id"])
            except (ValueError, KeyError):
                logger.warning("An import job could not be recovered")

    def shutdown(self):
        self.stop.set()
        if self.executor:
            self.executor.shutdown(wait=False, cancel_futures=True)

    def directory(self, identifier):
        if not re.fullmatch(r"[0-9a-f-]{36}", identifier):
            raise StorageError(404, "导入任务不存在")
        return self.root / identifier

    def read(self, identifier):
        with self.lock:
            path = self.directory(identifier) / "job.json"
            if not path.is_file():
                raise StorageError(404, "导入任务不存在")
            return json.loads(path.read_text(encoding="utf-8"))

    def update(self, identifier, **values):
        with self.lock:
            job = self.read(identifier)
            job.update(values, updated_at=now())
            atomic_write(self.directory(identifier) / "job.json", json.dumps(job, ensure_ascii=False, indent=2).encode("utf-8"))
            return job

    def public(self, identifier):
        job = self.read(identifier)
        result = {key: job[key] for key in ("id", "state", "stage", "message", "warnings", "created_at") if key in job}
        if job.get("note_id"):
            try:
                result["note"] = self.store_getter().read_note(job["note_id"])
            except StorageError:
                result["message"] = "导入文档已被删除"
        return result

    def validate_folder(self, identifier):
        store = self.store_getter()
        with store.transaction():
            store.folder(identifier)

    def retry_network(self, identifier, operation):
        for attempt in range(3):
            try:
                return operation()
            except httpx.HTTPError:
                if attempt == 2 or self.stop.is_set():
                    raise
                self.update(identifier, message="MinerU 连接暂时中断，正在重试")
                self.stop.wait(2)

    def create(self, notebook_id, filename, *, upload=None, url="", is_ocr=False):
        self.validate_folder(notebook_id)
        if url:
            url = public_url(url)
            filename = filename.strip() or leaf_name(urlsplit(url).path)
        else:
            filename = leaf_name(filename)
            if Path(filename).suffix.lower() not in self.config.accepts:
                raise StorageError(422, "当前 MinerU 模式不支持该格式，请使用 PDF、Word、图片或 Markdown")
        identifier = str(uuid.uuid4())
        directory = self.directory(identifier)
        directory.mkdir(parents=True)
        try:
            if upload:
                size = 0
                with (directory / "source").open("xb") as target:
                    while chunk := upload.read(1024 * 1024):
                        size += len(chunk)
                        if size > self.config.max_bytes:
                            raise StorageError(413, f"当前模式单个文件最大 {self.config.max_bytes // 1024 // 1024} MB")
                        target.write(chunk)
            job = {"id": identifier, "notebook_id": notebook_id, "filename": filename, "url": url, "is_ocr": is_ocr,
                   "state": "pending", "stage": "pending", "message": "等待导入", "created_at": now()}
            atomic_write(directory / "job.json", json.dumps(job, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception:
            import shutil
            shutil.rmtree(directory)
            raise
        if self.executor:
            self.executor.submit(self.run, identifier)
        return self.public(identifier)

    def run(self, identifier):
        client = None
        try:
            job = self.read(identifier)
            if job["state"] == "done":
                return
            source = self.directory(identifier) / "source" if not job["url"] else None
            if source and Path(job["filename"]).suffix.lower() in DIRECT_TYPES:
                self.update(identifier, state="running", stage="saving", message="正在保存 Markdown")
                markdown, assets, warnings = read_markdown(source.read_bytes()), {}, []
            else:
                client = self.client_factory(self.config)
                self.update(identifier, state="running", stage="uploading", message="正在提交至 MinerU")
                remote = job.get("remote")
                if not remote:
                    remote = client.submit(job["filename"], url=job["url"] or None, is_ocr=job["is_ocr"])
                    self.update(identifier, remote=remote)
                if source and remote.get("upload_url") and not job.get("uploaded"):
                    client.upload(remote["upload_url"], source)
                    self.update(identifier, uploaded=True)
                while not self.stop.is_set():
                    if (datetime.now(timezone.utc) - datetime.fromisoformat(job["created_at"])).total_seconds() > 1200:
                        raise MinerUError("MinerU 解析等待超过 20 分钟，请稍后重试")
                    result = self.retry_network(identifier, lambda: client.poll(remote))
                    state = result.get("state", "pending")
                    if state == "failed":
                        raise MinerUError("MinerU：" + str(result.get("err_msg") or "解析失败")[:300])
                    if state == "done":
                        break
                    progress = result.get("extract_progress") or {}
                    label = "MinerU 正在解析" if state == "running" else "MinerU 排队处理中"
                    if progress.get("total_pages"):
                        label += f"（{progress.get('extracted_pages', 0)}/{progress['total_pages']} 页）"
                    self.update(identifier, stage="parsing", message=label)
                    self.stop.wait(3)
                if self.stop.is_set():
                    self.update(identifier, state="pending", message="服务重启后继续导入")
                    return
                self.update(identifier, stage="saving", message="解析完成，正在保存 Markdown 和图片")
                markdown, assets, warnings = self.retry_network(identifier, lambda: client.result(result))
                if not markdown.strip():
                    raise MinerUError("MinerU 未解析出可保存的文本，请检查原文档")
            title = Path(job["filename"]).stem or "导入文档"
            note = self.store_getter().import_document(job["notebook_id"], title, markdown, job_id=identifier, assets=assets,
                                                     source=source, filename=job["filename"], url=job["url"])
            self.update(identifier, state="done", stage="done", message="已保存为独立 Markdown 文档", note_id=note["id"], warnings=warnings)
            if source:
                source.unlink(missing_ok=True)
        except (StorageError, MinerUError) as error:
            self.update(identifier, state="failed", stage="failed", message=str(error))
        except httpx.HTTPError:
            self.update(identifier, state="failed", stage="failed", message="无法连接 MinerU，请检查网络后重试")
        except Exception:
            logger.exception("Import job failed")
            self.update(identifier, state="failed", stage="failed", message="文档导入失败，请检查文件格式后重试")
        finally:
            if client:
                client.close()
