# AgenttestGuide · Agent 评测知识笔记

一个适合编写与展示 **Agent 评测入门知识** 的轻量项目。前端使用 **Vue 3 + TypeScript + Ant Design Vue**，后端使用 **FastAPI + 独立 Markdown 文件**。左侧的文件夹和文件对应磁盘上的真实目录与 `.md` 文件，右侧直接阅读或编写。

## 已有功能

- 创建文件夹、在文件夹中创建文件。
- 导入 Markdown、PDF、Word、PPT、Excel 和图片，或输入公开文档 URL，通过 MinerU 转为 Markdown。
- 文件树展开、收起和打开文件；通过名称旁的菜单重命名或删除文件、文件夹，支持撤销删除。
- Markdown 编写与阅读，文件名称和正文自动保存。
- 编辑器支持点击「图片」选择本地图片、直接粘贴截图或拖入图片，并自动插入 Markdown 图片链接。
- 阅读时选中文字，在右侧发表评论；被评论文字默认黄色高亮，支持定位原文、编辑和删除评论。
- 侧栏收起与移动端适配。
- 浏览器草稿缓存；连接恢复后可重试保存，刷新前提示未保存内容。
- 首次启动自动放入 4 个文件夹、9 个可编辑的入门示例文件。

界面以文件树和阅读、编辑区为主，右侧评论栏可以展开或收起。原有笔记本已经迁移为文件夹，笔记已经迁移为独立 `.md` 文件，并保留原来的文件 ID 和浏览器草稿兼容性。

这是知识编写与展示工具，不包含实际 Agent 执行器或自动评测引擎。示例内容适合入门学习，可根据你的课程和实验继续修改。

## 安装和启动

需要 Python **3.10+**，推荐 3.12；Node.js **20.19+ 或 22.12+**（也支持更新的 LTS 版本）。

在项目根目录安装后端依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
```

进入前端目录安装依赖：

```bash
cd frontend
npm install
cd ..
```

也可以使用 `pnpm install`；项目提供 `pnpm-lock.yaml`。`pnpm-workspace.yaml` 仅允许 esbuild 必需的安装脚本。

启动两个服务：

```bash
.venv/bin/python scripts/dev.py
```

macOS 也可以双击 **start.command**（已安装依赖后）。Windows 可使用 `.venv\Scripts\python.exe scripts\dev.py`。

- 界面：<http://127.0.0.1:5317>
- FastAPI 接口文档：<http://127.0.0.1:8317/docs>
- 健康检查：<http://127.0.0.1:8317/api/health>

项目固定使用前端 `5317`、后端 `8317`，避开医联项目使用的 `5173` 和 `8000`。前端启用严格端口检查，端口被占用时会明确报错。

在终端按 `Ctrl+C` 同时停止两个服务。前端通过 Vite 代理访问 `/api`，无需额外配置 CORS。

如果希望分别启动，后端命令为 `.venv/bin/python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8317`；前端在 `frontend` 目录运行 `npm run dev`。

## 使用建议

示例内容按三个学习阶段组织：

1. **Agent 评测入门**：学习路线、Agent 基本概念、模型与 Agent 评测的区别。
2. **评测方法与指标**：核心指标、规则/人工/模型评审、数据集准备。
3. **动手实践**：第一次实验、评测记录模板、常见误区。

「灵感与思考」留给你自由编写。在左侧「文件」标题旁，点击文件夹加号新建文件夹，点击文件加号在选中的文件夹中创建文件。创建时只需填写名称。

点击树中的文件即可阅读，点击右上角「编辑」开始修改。停笔约 700 毫秒后自动保存，切换文件不会丢失尚在保存的内容。文件和文件夹名称旁的「…」菜单支持重命名和删除；选中项会显示菜单按钮。删除前会确认，文件夹会连同内部文件和附件一起移入回收目录；删除后的提示中可在 12 秒内点击「撤销」恢复。未保存的正文会先保存，保存失败时不会执行删除。

快捷键：`⌘/Ctrl + S` 立即保存，`Esc` 关闭移动端文件栏。

在编辑器工具栏点击「图片」，或直接在正文编辑框中粘贴截图、拖入图片，即可在光标处插入。支持 PNG、JPEG、GIF、WebP，单张不超过 10 MB，一次最多 10 张。上传期间会显示进度；切换到「阅读」可查看图片。普通文字粘贴不受影响。

图片直接保存在当前文件夹的 `_assets/<文件ID>/` 目录中，正文使用相对路径引用，无需外部图床。文件移动、文件夹重命名及删除撤销都会保留图片关联。直接复制 Markdown 文件到其他位置时，请同时复制对应的 `_assets/` 目录。

也支持自行放置图片，例如文档为 `content/课程/笔记.md`，图片为 `content/课程/images/示意图.jpg`，正文可直接写 `![](images/示意图.jpg)` 或 `![](./images/示意图.jpg)`。图片路径以当前 Markdown 文件所在目录为基准；支持中文、空格和内容目录内的 `../共享图片/图.png`，以 `/` 开头的路径则以 `content/` 为基准。含 `#` 的文件名需将 `#` 写为 `%23`。图片必须存在于 `content/` 内，不能通过该功能读取目录外的本机文件、隐藏目录或符号链接。

编辑模式显示 Markdown 源码（包括图片路径），点击右上角「阅读」才会显示图片。自行放置的图片文件夹随文件夹重命名仍可使用；将单篇文档移到另一文件夹时，需要同时移动或调整自定义图片路径。图片不存在时，阅读区会显示无法加载的路径提示。

在「阅读」模式中拖动选中正文，会打开右侧评论输入区。发表评论后，相关文字以黄色标记；点击评论中的引用或「定位原文」可回到对应内容。编辑模式中也可以浏览已有评论，选取新的评论文本需要切换回阅读模式。未发表的评论草稿在切换文件时会暂时保留，关闭页面前会提醒。

原文新增内容导致位置移动时，会结合引用及上下文重新定位。原文被删除或出现无法消除的歧义时，评论仍保留，卡片提示「原文已修改」。

## 导入文档（MinerU）

点击左侧「文件」旁的导入图标，在弹窗中选择目标文件夹，再上传文件或输入 URL。支持多文件依次导入、扫描件 OCR，以及查看解析状态；完成后可以直接打开文档编辑、阅读和评论。同名文件自动添加编号，不会覆盖已有内容。

Markdown、TXT 文件直接转为 UTF-8 保存；PDF、Office 和图片使用 [MinerU 官方云接口](https://mineru.net/apiManage/docs) 解析，文件或 URL 会提交至 MinerU。默认无需 Token，使用轻量模式：单文件不超过 10 MB、20 页，支持 `.pdf`、`.docx`、`.pptx`、`.xlsx` 及常见图片。URL 必须是 MinerU 可以访问的公开文档链接；没有扩展名的下载链接可在弹窗中填写带扩展名的文件名称。

需要普通网页 URL、旧版 `.doc/.ppt/.xls` 或更大的文件时，将项目根目录的 `.env.example` 复制为 `.env`，填写 `MINERU_API_TOKEN` 并重启后端，即切换至精准模式。Token 只保存在后端，前端不会获取它。实际配额与支持范围以 MinerU 官方说明为准。

转换后正文仍是所选文件夹下的独立 `.md` 文件；图片存放在同一文件夹的 `_assets/<文件ID>/`，Markdown 中使用相对链接，复制文档时请同时复制 `_assets/`。上传的原始文件留存在 `content/.agenttestguide/imports/<文件ID>/`。URL 导入保留来源地址。

后台任务记录位于 `content/.agenttestguide/import-jobs/`，重启后继续轮询已经提交的任务；云端排队和解析速度取决于 MinerU。解析失败不会创建半份文档，弹窗会显示错误并允许重试。任务超过 20 分钟会停止等待。未完成或失败上传的暂存文件也位于该隐藏目录，确认不再需要时可在停止服务后清理相应任务目录。

## 文档存放位置

文档保存在项目根目录的 **`content/`** 中，例如：

```text
content/
  Agent 评测入门/
    从这里，开始理解 Agent 评测.md
    什么是 Agent？从一个简单例子说起.md
    模型评测与 Agent 评测，有什么不同？.md
  评测方法与指标/
    ...
  动手实践/
    ...
  灵感与思考/
```

网页中新建文件夹会创建真实目录；新建、编辑、重命名文件会直接写入或重命名 `.md` 文件。正文以 UTF-8 原文保存，可以直接用 VS Code、Typora 或其他 Markdown 编辑器打开。

也可以从磁盘直接编辑文档，或在 `content/` 的一级文件夹内添加、重命名、删除 `.md` 文件，刷新网页后即可读取。当前界面按一级文件夹组织内容，尚不展示根目录散落文件或更深层子目录。请避免同时在网页和外部编辑器修改同一篇文档。

可用环境变量 **`AGENTTESTGUIDE_CONTENT_DIR`** 指定其他内容目录。文件名不允许路径分隔符、控制字符或跨平台保留名称；同名创建和重命名会返回提示，避免覆盖已有文件。

`content/.agenttestguide/` 是隐藏的辅助目录，其中 `index.json` 只保存稳定 ID、文件路径和兼容元数据，**不保存文档正文**。删除的文件以 `.md` 文件保存在此目录的 `trash/` 下；整文件夹删除后保存在 `trash/folders/<文件夹ID>/` 中，包含原有的附件和其他文件。评论与原始导入文件会保留。撤销提示消失后仍可通过 `POST /api/notes/<文件ID>/restore` 或 `POST /api/notebooks/<文件夹ID>/restore` 恢复；同名冲突时会阻止恢复，避免覆盖。独立 Markdown 文件不依赖索引也可打开阅读。

评论单独存放在 `content/.agenttestguide/comments/<文件ID>.json` 中，包含评论文字、选区引用及定位上下文。黄色高亮只在页面中渲染，不会往 `.md` 中插入标签；文件通过网页重命名或移动后仍会关联原评论。

## 旧数据库迁移和备份

升级后第一次启动时，若 `content/` 尚未初始化，会先对旧 `backend/data/evalnote.db` 创建一致性备份，再一次性导出所有文件夹与文档。迁移保留自建内容、空文件夹、正文和文件 ID；原有同名标题会导出为不同文件名，例如 `笔记.md`、`笔记 (2).md`。迁移在临时目录中完成后整体发布，失败时不会留下半份内容目录。

原数据库保留用于归档，迁移备份位于 **`backend/data/backups/`**，迁移记录位于 `content/.agenttestguide/migration.json`。正常浏览和保存都使用文件系统，不再写入数据库。旧环境变量 `EVALNOTE_DB_PATH` 仅用于指定首次迁移的数据源。

如果指定的内容目录已经有文件，程序会直接读取已有文件，不会用旧数据库覆盖它们。没有旧数据库的新安装会生成默认的 4 个文件夹和 9 篇示例。已初始化目录不会因文档删除而重新生成示例。

日常备份只需先停止服务，再复制整个 **`content/`**，包含隐藏的 `.agenttestguide/`。也可以单独复制任意 `.md` 文件使用。浏览器草稿只是临时保护，不能替代文件备份。

当前版本面向个人本地使用，默认只监听 `127.0.0.1`，没有账号、身份验证和多人编辑冲突合并。若用于公网或多人共享，应先加入访问控制和相应的数据隔离。

## 构建后由 FastAPI 统一提供页面

在 `frontend` 目录执行：

```bash
npm run build
```

然后在根目录启动（或重启）后端：

```bash
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8317
```

打开 <http://127.0.0.1:8317>，即可通过同一服务访问页面和 API。前端生成产物在 `frontend/dist/`；后端在启动时检测该目录。

## 验证

```bash
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

测试使用独立临时目录和迁移样本，覆盖文件读写、重命名、删除与撤销、附件及评论保留、自动保存与删除衔接、外部编辑、同名保护、原子保存、迁移完整性和失败恢复，不会改动个人文档。

## 项目结构

```text
backend/
  main.py             FastAPI 接口与生产静态文件服务
  storage.py          Markdown 文件存储、扫描、原子写入和旧库迁移
  mineru.py           MinerU 云接口、上传、轮询和结果资源读取
  imports.py          持久化后台导入任务与重启恢复
  seed.py             9 篇入门知识和初始文件夹
  requirements.txt    运行依赖
  requirements-dev.txt
  tests/test_api.py   接口集成测试
  tests/test_markdown_storage.py  文件存储与迁移测试
  tests/test_comments.py  评论保存、文档关联和隔离测试
  tests/test_imports.py  文件及 URL 导入、MinerU 协议与资源安全测试
content/              实际文件夹和 Markdown 文档
frontend/
  src/App.vue         文件树、创建文件夹/文件、阅读和编辑
  src/useFiles.ts     文件数据、自动保存与浏览器草稿
  src/useComments.ts  文本选区、评论与高亮联动
  src/CommentsPanel.vue  右侧评论栏
  src/ImportDialog.vue   文件和 URL 导入弹窗
  src/annotations.ts 文本定位与跨节点高亮
  tests/annotations.test.ts  定位及重叠高亮测试（Node 24）
  src/style.css       响应式界面和 Markdown 样式
  src/types.ts        数据类型和 API 客户端
  vite.config.ts     开发服务与 API 代理
scripts/dev.py        同时启动前后端
start.command         macOS 双击启动入口
```

技术文档：[Ant Design Vue](https://antdv.com/docs/vue/getting-started/) · [Vue](https://vuejs.org/guide/introduction.html) · [FastAPI](https://fastapi.tiangolo.com/)
