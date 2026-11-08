#!/bin/zsh
cd -- "${0:A:h}"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python scripts/dev.py
else
  printf '请先按照 README.md 安装依赖。\n'
  read -k 1 '?按任意键退出…'
fi
