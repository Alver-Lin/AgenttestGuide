#!/usr/bin/env python3
"""Start both local servers and stop both cleanly on Ctrl+C."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies"
processes = []


def main():
    python = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    if not python.exists():
        sys.exit("请先按 README 创建 .venv 并安装后端依赖。")
    node = shutil.which("node") or str(RUNTIME / "node/bin/node")
    if not Path(node).is_file():
        sys.exit("未找到 Node.js，请先安装 Node.js 20.19+ 或 22.12+。")
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not vite.exists():
        sys.exit("请先进入 frontend 并运行 npm install 或 pnpm install。")
    env = {**os.environ, "PATH": str(Path(node).parent) + os.pathsep + os.environ.get("PATH", "")}
    print("\n  AgenttestGuide · Agent 评测知识笔记\n  界面：http://127.0.0.1:5317\n  API 文档：http://127.0.0.1:8317/docs\n  文档目录：content/\n  按 Ctrl+C 同时停止两个服务。\n", flush=True)
    try:
        processes.append(subprocess.Popen([str(python), "-m", "uvicorn", "backend.main:app", "--reload", "--host", "127.0.0.1", "--port", "8317"], cwd=ROOT, env=env))
        processes.append(subprocess.Popen([node, str(vite), "--host", "127.0.0.1", "--port", "5317"], cwd=ROOT / "frontend", env=env))
        while all(p.poll() is None for p in processes):
            time.sleep(.4)
        failed = next(p.returncode for p in processes if p.poll() is not None)
        if failed:
            print("服务启动失败，请查看上方错误（常见原因：端口已占用）。", file=sys.stderr)
            return failed
    except KeyboardInterrupt:
        print("\n正在停止 AgenttestGuide…", flush=True)
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return 0


if __name__ == "__main__":
    sys.exit(main())
