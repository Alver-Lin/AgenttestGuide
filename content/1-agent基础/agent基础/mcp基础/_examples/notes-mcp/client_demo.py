"""启动真实 MCP 子进程，验证发现、调用、资源、模板和错误处理。"""

import asyncio
import shutil
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent
from pydantic import AnyUrl

BASE = Path(__file__).resolve().parent


def structured(result: CallToolResult) -> dict[str, Any]:
    if result.isError:
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent))
        raise RuntimeError(text)
    if result.structuredContent is None:
        raise RuntimeError("服务没有返回预期的结构化数据")
    return result.structuredContent


async def verify(root: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(BASE / "server.py")],
        env={"NOTES_ROOT": str(root)},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as session:
            initialized = await session.initialize()
            print("服务:", initialized.serverInfo.name)
            print("协议:", initialized.protocolVersion)
            tools = await session.list_tools()
            print("工具:", ", ".join(sorted(tool.name for tool in tools.tools)))

            result = structured(await session.call_tool("search_notes", {"query": "生成器"}))
            assert result["matches"][0]["filename"] == "python.md"
            print("搜索命中:", result["matches"][0]["filename"])
            note = structured(await session.call_tool("read_note", {"filename": "python.md"}))
            assert "yield" in note["content"]
            print("读取正文包含 yield:", "yield" in note["content"])

            content = "# MCP 实践记录\n\n已完成搜索、读取和新建笔记。\n"
            saved = structured(
                await session.call_tool("create_note", {"filename": "practice.md", "content": content})
            )
            assert (root / "practice.md").read_text(encoding="utf-8") == content
            assert saved["bytes_written"] == len(content.encode("utf-8"))
            print("实际写入:", saved["filename"])
            reread = structured(await session.call_tool("read_note", {"filename": "practice.md"}))
            assert reread["content"] == content

            resource = await session.read_resource(AnyUrl("notes://guide"))
            assert resource.contents and "笔记库" in resource.contents[0].text
            print("资源读取成功:", True)
            prompt = await session.get_prompt("summarize_note", {"filename": "python.md"})
            assert prompt.messages and "read_note" in prompt.messages[0].content.text
            print("提示模板包含 read_note:", True)

            rejected = [
                ("read_note", {"filename": "../secret.md"}),
                ("read_note", {"filename": "missing.md"}),
                ("create_note", {"filename": "practice.md", "content": "覆盖旧内容"}),
                ("create_note", {"filename": "empty.md", "content": "  "}),
                ("create_note", {"filename": "huge.md", "content": "字" * 14000}),
                ("search_notes", {"query": "  "}),
                ("search_notes", {"query": "Python", "limit": 0}),
            ]
            for name, arguments in rejected:
                failed = await session.call_tool(name, arguments)
                assert failed.isError, (name, arguments)
            assert (root / "practice.md").read_text(encoding="utf-8") == content
            empty = structured(await session.call_tool("search_notes", {"query": "没有这种关键词987"}))
            assert empty["matches"] == []
            print("预期错误检查:", len(rejected), "项通过")
            print("全部验证通过；测试笔记将在退出后清理。")


async def main() -> None:
    with TemporaryDirectory(prefix="mcp-notes-demo-") as directory:
        root = Path(directory)
        for source in (BASE / "notes").glob("*.md"):
            shutil.copy2(source, root / source.name)
        await verify(root)


if __name__ == "__main__":
    asyncio.run(main())
