"""MinerU official cloud API adapter. Credentials are sent only to the API host."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit, urljoin, unquote
import ipaddress
import os
import re
import stat
import zipfile

import httpx

API = "https://mineru.net"
IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".jp2"}
LIGHT_TYPES = {".pdf", ".docx", ".pptx", ".xlsx", *IMAGES}
PRECISION_TYPES = LIGHT_TYPES | {".doc", ".ppt", ".xls", ".html", ".htm"}
DIRECT_TYPES = {".md", ".markdown", ".txt"}
IMAGE_PATTERN = re.compile(r'(!\[[^\]]*\]\(\s*<?)([^\s)>]+)(>?(?:\s+["\'][^\n]*?["\'])?\s*\))')
HTML_IMAGE = re.compile(r'(\bsrc\s*=\s*["\'])([^"\']+)(["\'])', re.I)


class MinerUError(Exception):
    pass


@dataclass
class Config:
    token: str = ""

    @classmethod
    def environment(cls):
        return cls((os.getenv("MINERU_API_TOKEN") or os.getenv("MINERU_TOKEN") or "").strip())

    @property
    def mode(self):
        return "precision" if self.token else "agent"

    @property
    def max_bytes(self):
        return (200 if self.token else 10) * 1024 * 1024

    @property
    def accepts(self):
        return sorted((PRECISION_TYPES if self.token else LIGHT_TYPES) | DIRECT_TYPES)

    def public(self):
        return {"mode": self.mode, "max_bytes": self.max_bytes, "accepts": self.accepts, "supports_webpage": bool(self.token)}


def public_url(value):
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            raise ValueError()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise ValueError()
        try:
            if not ipaddress.ip_address(host).is_global:
                raise ValueError()
        except ValueError as error:
            # Domain names are fetched by MinerU, never by this application.
            if ":" in host or re.fullmatch(r"[\d.]+", host):
                raise ValueError() from error
        return parsed._replace(fragment="").geturl()
    except ValueError:
        raise MinerUError("请输入不含账号密码的公开 HTTP 或 HTTPS 文档链接")


def trusted_result_url(value):
    value = public_url(value)
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    if parsed.scheme != "https" or not any(host == domain or host.endswith("." + domain) for domain in ("mineru.net", "openxlab.org.cn", "aliyuncs.com", "shlab.tech", "mineru.org.cn")):
        raise MinerUError("MinerU 返回了不受信任的文件地址")
    return value


def leaf_name(value):
    return unquote(value.replace("\\", "/").split("/")[-1]) or "导入文档"


def rewrite_links(markdown, mapping):
    def replace(match):
        original = match.group(2)
        key = unquote(original).removeprefix("./")
        return match.group(1) + mapping.get(key, mapping.get(original, original)) + match.group(3)
    return HTML_IMAGE.sub(replace, IMAGE_PATTERN.sub(replace, markdown))


def read_markdown(data):
    for encoding in (["utf-16"] if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ["utf-8-sig", "gb18030"]):
        try:
            text = data.decode(encoding)
            if "\x00" in text:
                break
            if len(text) > 500_000:
                raise MinerUError("文档超过 50 万字符，请拆分后导入")
            return text
        except UnicodeDecodeError:
            continue
    raise MinerUError("文本编码无法识别，请另存为 UTF-8 后导入")


class MinerUClient:
    def __init__(self, config, *, transport=None):
        self.config = config
        self.http = httpx.Client(timeout=httpx.Timeout(60, connect=15), transport=transport, follow_redirects=False)

    def close(self):
        self.http.close()

    def request(self, method, path, data=None):
        headers = {"Authorization": f"Bearer {self.config.token}"} if path.startswith("/api/v4/") else {}
        response = self.http.request(method, API + path, json=data, headers=headers)
        if response.status_code == 429:
            raise MinerUError("MinerU 当前请求较多，请稍后重试")
        if response.status_code in (401, 403):
            raise MinerUError("MinerU 访问被拒绝，请检查 Token 或网络连接")
        if response.is_error:
            raise MinerUError(f"MinerU 请求失败（HTTP {response.status_code}）")
        try:
            result = response.json()
        except ValueError:
            raise MinerUError("MinerU 返回了无法识别的响应")
        if result.get("code") != 0:
            raise MinerUError("MinerU：" + str(result.get("msg") or "任务提交失败")[:300])
        return result.get("data") or {}

    def submit(self, filename, *, url=None, is_ocr=False):
        extension = Path(filename).suffix.lower()
        webpage = extension not in (PRECISION_TYPES - {".html", ".htm"})
        if webpage and not self.config.token:
            raise MinerUError("网页 URL 需要配置 MinerU Token 启用精准解析；当前可导入公开 PDF、Word 等文档链接")
        if self.config.token:
            model = "MinerU-HTML" if webpage else "vlm"
            if url:
                data = self.request("POST", "/api/v4/extract/task", {"url": url, "model_version": model, "is_ocr": is_ocr})
                return {"kind": "task", "id": data["task_id"]}
            data = self.request("POST", "/api/v4/file-urls/batch", {"files": [{"name": filename, "is_ocr": is_ocr}], "model_version": model})
            return {"kind": "batch", "id": data["batch_id"], "upload_url": data["file_urls"][0]}
        payload = {"file_name": filename, "language": "ch", "is_ocr": is_ocr, "enable_table": True, "enable_formula": True}
        if url:
            payload["url"] = url
        data = self.request("POST", "/api/v1/agent/parse/" + ("url" if url else "file"), payload)
        result = {"kind": "agent", "id": data["task_id"]}
        if not url:
            result["upload_url"] = data["file_url"]
        return result

    def upload(self, url, path):
        url = trusted_result_url(url)
        with path.open("rb") as stream:
            chunks = iter(lambda: stream.read(1024 * 1024), b"")
            response = self.http.put(url, content=chunks, headers={"Content-Length": str(path.stat().st_size)}, timeout=180)
        if response.status_code not in (200, 201, 204):
            raise MinerUError(f"文件上传至 MinerU 失败（HTTP {response.status_code}）")

    def poll(self, remote):
        kind, identifier = remote["kind"], remote["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier):
            raise MinerUError("MinerU 返回的任务编号无效")
        path = f"/api/v1/agent/parse/{identifier}" if kind == "agent" else (f"/api/v4/extract/task/{identifier}" if kind == "task" else f"/api/v4/extract-results/batch/{identifier}")
        data = self.request("GET", path)
        if kind == "batch":
            results = data.get("extract_result") or []
            return results[0] if results else {"state": "pending"}
        return data

    def download(self, url, *, limit=100 * 1024 * 1024):
        for _ in range(5):
            url = trusted_result_url(url)
            with self.http.stream("GET", url) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["location"])
                    continue
                if response.is_error:
                    raise MinerUError(f"下载 MinerU 解析结果失败（HTTP {response.status_code}）")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise MinerUError("解析结果过大，请拆分文档后重试")
                    chunks.append(chunk)
                return b"".join(chunks), url
        raise MinerUError("解析结果的跳转次数过多")

    def result(self, data):
        if data.get("full_zip_url"):
            archive, _ = self.download(data["full_zip_url"])
            return unpack_archive(archive)
        if not data.get("markdown_url"):
            raise MinerUError("MinerU 未返回 Markdown 结果")
        content, base = self.download(data["markdown_url"], limit=4 * 1024 * 1024)
        markdown = read_markdown(content)
        assets, mapping, warnings = {}, {}, []
        targets = list(dict.fromkeys(match.group(2) for pattern in (IMAGE_PATTERN, HTML_IMAGE) for match in pattern.finditer(markdown)))
        for number, target in enumerate(targets):
            if number >= 100:
                warnings.append("部分图片超过本地保存上限，已保留原始链接")
                break
            absolute = urljoin(base, target)
            extension = Path(urlsplit(absolute).path).suffix.lower()
            if extension not in IMAGES:
                continue
            try:
                body, _ = self.download(absolute, limit=10 * 1024 * 1024)
                if sum(map(len, assets.values())) + len(body) > 80 * 1024 * 1024:
                    raise MinerUError("图片总大小超过限制")
                key = f"images/{number + 1}{extension}"
                assets[key], mapping[target] = body, key
            except MinerUError:
                mapping[target] = absolute
                warnings.append("部分图片无法保存到本地，已保留 MinerU 原始链接")
        return rewrite_links(markdown, mapping), assets, list(dict.fromkeys(warnings))


def unpack_archive(data):
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            files = archive.infolist()
            if len(files) > 2000 or sum(file.file_size for file in files) > 200 * 1024 * 1024:
                raise MinerUError("解析结果包含过多文件或内容过大")
            for file in files:
                path = PurePosixPath(file.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in file.filename or stat.S_ISLNK(file.external_attr >> 16):
                    raise MinerUError("解析结果包含无效文件路径")
            candidates = [file for file in files if file.filename.lower().endswith(".md")]
            if not candidates:
                raise MinerUError("解析结果中没有 Markdown 文件")
            chosen = min(candidates, key=lambda file: (PurePosixPath(file.filename).name != "full.md", len(file.filename)))
            base = PurePosixPath(chosen.filename).parent
            markdown = read_markdown(archive.read(chosen))
            assets = {}
            for file in files:
                path = PurePosixPath(file.filename)
                if path.suffix.lower() in IMAGES and path.is_relative_to(base):
                    if file.file_size > 10 * 1024 * 1024:
                        raise MinerUError("解析结果的单张图片过大")
                    assets[path.relative_to(base).as_posix()] = archive.read(file)
            return markdown, assets, []
    except (zipfile.BadZipFile, RuntimeError, UnicodeError):
        raise MinerUError("MinerU 返回的压缩结果无法读取")
