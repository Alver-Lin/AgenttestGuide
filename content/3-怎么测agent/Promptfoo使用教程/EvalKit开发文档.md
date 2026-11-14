# EvalKit

> 开发与使用文档

EvalKit 是面向评测同学的 **Promptfoo 可视化工作台**：配置 Prompt / Provider / Tests，一键调度 `promptfoo eval`，并在浏览器中查看结果矩阵与报告下载。

本文面向两类读者：

- **使用者**：如何安装、配置、跑评测、读报告
- **开发者**：系统架构、目录约定、API、扩展点与排错

## 1. 产品概览

| 能力 | 说明 |
|------|------|
| 测评任务 | 创建 / 编辑 / 删除 promptfoo 配置（可视化表单或 YAML） |
| 一键运行 | 异步执行 `promptfoo eval`，支持并发与缓存开关 |
| 测评报告 | 列表筛选、详情页矩阵对比、JSON / HTML / CSV 下载 |
| 示例任务 | 启动时自动种子 `Demo Mock Eval`、`OpenAI Sample` |

技术栈：

- **前端**：Vue 3 + TypeScript + Vite + Ant Design Vue + ECharts
- **后端**：Python 3 + FastAPI + Pydantic
- **引擎**：本地 `tools/` 安装的 [promptfoo](https://www.promptfoo.dev/)（当前锁定 `0.125.1`）

---

## 2. 系统架构

```text
浏览器 (Vue)
   │  /api/*  (Vite 代理 → :8000)
   ▼
FastAPI
   ├─ configs   配置 CRUD（落盘 data/configs）
   ├─ runs      创建运行 / 查状态 / 报告
   └─ dashboard 统计（可选）
   │
   ▼
PromptfooRunner (asyncio 子进程)
   └─ promptfoo eval -c promptfooconfig.yaml --output results.json --output report.html
```

核心数据流：

1. 前端保存任务 → 后端写入 `data/configs/{id}/promptfooconfig.yaml` + `meta.json`
2. 点击「运行」→ 后端创建 `data/runs/{run_id}/`，拷贝配置与附属文件（如 `mock_provider.py`）
3. 子进程执行 promptfoo，写出 `results.json`、`report.html`、`stdout.log`、`stderr.log`
4. 后端解析结果更新 `meta.json`（通过率、状态等）
5. 前端轮询运行状态，成功后拉取 `/api/runs/{id}/report` 渲染矩阵

---

## 3. 目录结构

```text
Evalkit/
├── backend/                 # FastAPI 服务
│   ├── app/
│   │   ├── api/             # configs / runs / dashboard 路由
│   │   ├── core/config.py   # 路径、CORS、promptfoo 命令解析
│   │   ├── models/schemas.py
│   │   └── services/        # store / runner / report_builder / seed
│   └── requirements.txt
├── frontend/                # Vue 应用
│   ├── src/
│   │   ├── api/client.ts    # Axios 封装
│   │   ├── components/      # VisualConfigForm、StatusTag …
│   │   ├── layouts/         # 侧栏布局
│   │   ├── utils/           # YAML ↔ 可视化模型、DeepSeek 别名
│   │   └── views/           # 任务列表 / 详情 / 报告列表 / 报告详情
│   └── vite.config.ts       # /api → http://127.0.0.1:8000
├── tools/                   # 本地 promptfoo CLI（npm 依赖）
├── samples/                 # 示例 YAML 与 mock provider
├── data/                    # 运行时数据（默认 gitignore）
│   ├── configs/{config_id}/
│   ├── runs/{run_id}/
│   └── reports/
└── README.md                # 本说明文档
```

`ROOT_DIR` 由 `backend/app/core/config.py` 解析为仓库根目录；**数据目录在仓库根下的 `data/`**，不放在 `backend/` 内，避免 `uvicorn --reload` 因写文件反复重启。

---

## 4. 环境要求

| 组件 | 版本建议 |
|------|----------|
| Node.js | ≥ 22.22（promptfoo 0.125.x 要求） |
| Python | ≥ 3.10（推荐 3.11+） |
| 包管理 | npm / pip + venv |

可选环境变量：

| 变量 | 作用 |
|------|------|
| `OPENAI_API_KEY` | OpenAI 类供应商 |
| `PROMPTFOO_BIN` | 覆盖 promptfoo 可执行路径（也可在 Settings 里配） |
| 其它供应商 Key | 按 promptfoo 文档设置，或写在配置 YAML 的 `config.apiKey` |

---

## 5. 本地启动（开发）

在三个终端分别执行：

### 5.1 安装 promptfoo

```bash
cd tools
npm install
```

成功后应存在：`tools/node_modules/.bin/promptfoo`。

### 5.2 启动后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：http://127.0.0.1:8000/api/health

API 文档：http://127.0.0.1:8000/docs

### 5.3 启动前端

```bash
cd frontend
npm install
npm run dev
```

浏览器打开：http://localhost:5173  
前端通过 Vite 把 `/api` 代理到 `http://127.0.0.1:8000`。

### 5.4 生产构建（可选）

```bash
cd frontend
npm run build          # 输出 frontend/dist
# 可用任意静态服务器托管 dist，并保证 /api 反代到后端
```

---

## 6. 使用指南

### 6.1 测评任务

路径：`/configs`

1. **新建配置**：填写任务名称、描述，进入详情编辑
2. **可视化配置**（推荐）：分步填写
   - 基本信息：任务名称、描述
   - 提示词：一条或多条 Prompt（支持 `{{var}}`）
   - 供应商：见下方「供应商格式要求」
   - 测试用例：vars + 断言（断言可空）；可配全局断言，详见 [6.3 添加断言](#63-添加断言)
3. **YAML 模式**：直接编辑 promptfoo 配置，保存时校验必须含 `prompts` 与 `providers`/`targets`
4. **运行**：右侧设置并发数、是否使用缓存，点「运行」

列表支持按名称/描述搜索、按最近运行结果筛选。

### 6.2 供应商格式要求

遵循 [promptfoo Providers](https://www.promptfoo.dev/docs/providers/) 约定。可视化表单与 YAML 最终都会落到同样的 `providers` 配置。

**真正必填的只有 Provider ID**，格式为 `provider:model`（或带子类型的 `provider:type:model`），用来指定适配器与模型。常见写法：

| Provider ID 示例 | 含义 |
|------------------|------|
| `openai:gpt-4o-mini` | OpenAI 官方（简写） |
| `openai:chat:deepseek-chat` | OpenAI Chat Completions 兼容接口，模型名为 `deepseek-chat` |
| `anthropic:messages:claude-...` | Anthropic |
| `python:mock_provider.py` | 本地 Python Provider |
| `https://...` | 直接 HTTP 端点 |

可视化表单其它字段：

| 字段 | 是否必填 | 说明 |
|------|----------|------|
| Provider ID | **必填** | 唯一硬性格式要求 |
| Label | 可选 | 报告中的显示名，不影响调用 |
| API Key | 一般需要 | 可写在表单，也可走环境变量（如 `OPENAI_API_KEY`） |
| API Host | 非官方 OpenAI 时需要 | 对应官方配置里的 `apiBaseUrl`；须含协议与 `/v1`，不要带 `/chat/completions` |
| Organization | 可选 | 主要用于 OpenAI 组织 ID |

#### OpenAI

```yaml
providers:
  - id: openai:gpt-4o-mini
    label: gpt-4o-mini
```

启动后端前：

```bash
export OPENAI_API_KEY=sk-...
```

#### DeepSeek

当前内置 promptfoo **0.125.x 不识别裸写 `deepseek`**，需走 OpenAI 兼容接口：

```yaml
providers:
  - id: openai:chat:deepseek-chat
    label: deepseek
    config:
      apiKey: sk-...
      apiBaseUrl: https://api.deepseek.com/v1
```

可视化里 Provider ID 填 `deepseek` 或 `deepseek:deepseek-chat` 时，保存会自动规范化为上述格式，并默认 Host `https://api.deepseek.com/v1`。最少填三项：Provider ID、API Key、API Host。

#### 本地 Python Provider

```yaml
providers:
  - id: python:mock_provider.py
    label: mock
```

`mock_provider.py` 需放在该配置目录（`data/configs/{id}/`）下；运行时会连同 YAML 一起拷贝到 `data/runs/{run_id}/`。

入口约定：

```python
def call_api(prompt: str, options: dict, context: dict):
    return {"output": "..."}
```

### 6.3 添加断言

#### 怎么用

写在用例的 `assert` 或全局 `defaultTest.assert` 里。可视化下拉与 `frontend/src/constants/assertOptions.ts` 一致。

| 属性 | 说明 |
|------|------|
| `type` | 断言类型（必填） |
| `value` | 期望值 / 评分标准 / 脚本等（视类型） |
| `threshold` | 相似度、成本、模型评分等阈值（可视化暂不支持，用 YAML） |

- 几乎都可用 `not-` 取反，如 `not-contains`
- 详细语义与高级参数见官方：[Assertions](https://www.promptfoo.dev/docs/configuration/expected-outputs/) · [Deterministic](https://www.promptfoo.dev/docs/configuration/expected-outputs/deterministic/) · [Model-graded](https://www.promptfoo.dev/docs/configuration/expected-outputs/model-graded/)

#### 断言速查（按类）

YAML 写在用例的 `assert` 列表中。变体类型（如 `similar:cosine`）把 `type` 换成对应名字即可。模型评分类如需指定 grader，可再加 `provider`。

##### 模型评分

| 类型 | 中文名 | 适用场景 | YAML 示例 |
|------|--------|----------|-----------|
| `similar` / `similar:cosine` / `similar:dot` / `similar:euclidean` | 语义相似 | 语义接近即可，不要求原文一致 | <pre>- type: similar<br>  value: 法国的首都是巴黎<br>  threshold: 0.8</pre> |
| `llm-rubric` | 模型评分标准 | 用自然语言标准让 LLM Judge 打分 | <pre>- type: llm-rubric<br>  value: 回答准确、有帮助，且不道歉推诿<br>  threshold: 0.7</pre> |
| `factuality` / `model-graded-factuality` | 事实性 | 对照参考事实句是否一致 | <pre>- type: factuality<br>  value: 萨克拉门托是加利福尼亚州的首府</pre> |
| `model-graded-closedqa` | 封闭问答评分 | 是否满足某条要求（如不道歉） | <pre>- type: model-graded-closedqa<br>  value: 回答不道歉、直接给出结论</pre> |
| `answer-relevance` | 答案相关性 | 输出是否答到原问题上 | <pre>- type: answer-relevance<br>  threshold: 0.7</pre> |
| `g-eval` | G-Eval | 按自定义标准 CoT 打分 | <pre>- type: g-eval<br>  value: 回答事实准确、结构清晰<br>  threshold: 0.7</pre> |
| `agent-rubric` | Agent 评分 | 需检查代码/工作区证据时 | <pre>- type: agent-rubric<br>  value: 核实输出中声称的 API 确实存在于 src/report.ts<br>  provider:<br>    id: openai:codex-sdk<br>    config:<br>      working_dir: ./sample-project<br>      sandbox_mode: read-only</pre> |
| `search-rubric` | 检索评分 | 需联网核对时效信息 | <pre>- type: search-rubric<br>  value: 给出的比特币现价与市场价误差在 5% 以内</pre> |
| `pi` | Pi 评分 | 用 Pi Labs 专用模型打分（需 `WITHPI_API_KEY`） | <pre>- type: pi<br>  value: 不道歉，并给出清晰简洁的答案<br>  threshold: 0.8</pre> |
| `classifier` | 分类器 | 毒性、语气等分类检测 | <pre>- type: classifier<br>  value: toxic<br>  threshold: 0.5</pre> |

##### 文本匹配

| 类型 | 中文名 | 适用场景 | YAML 示例 |
|------|--------|----------|-----------|
| `contains` / `icontains` | 包含 | 必须出现某子串（后者忽略大小写） | <pre>- type: contains<br>  value: 巴黎</pre> |
| `equals` | 完全相等 | 输出与期望完全一致 | <pre>- type: equals<br>  value: 你好，世界</pre> |
| `starts-with` | 以…开头 | 固定前缀 | <pre>- type: starts-with<br>  value: 答：</pre> |
| `contains-all` / `contains-any` | 包含全部 / 任一项 | 多关键词 | <pre>- type: contains-all<br>  value:<br>    - 巴黎<br>    - 法国</pre> |
| `icontains-all` / `icontains-any` | 同上（忽略大小写） | 多关键词、大小写不敏感 | <pre>- type: icontains-any<br>  value:<br>    - 巴黎<br>    - 里昂</pre> |
| `not-contains` | 不得出现 | 禁止某措辞 | <pre>- type: not-contains<br>  value: 作为一个人工智能</pre> |
| `regex` | 正则 | 模式匹配 | <pre>- type: regex<br>  value: "\\d{4}"</pre> |
| `javascript` / `python` / `ruby` | 自定义脚本 | 复杂规则 | <pre>- type: javascript<br>  value: output.length &lt; 100</pre> |
| `webhook` | Webhook | 远端打分 | <pre>- type: webhook<br>  value: https://example.com/grade</pre> |
| `levenshtein` | 编辑距离 | 允许少量字符差异 | <pre>- type: levenshtein<br>  value: 你好世界<br>  threshold: 2</pre> |
| `word-count` | 词数 | 长度约束 | <pre>- type: word-count<br>  threshold: 50</pre> |

##### 结构 / 格式

| 类型 | 中文名 | 适用场景 | YAML 示例 |
|------|--------|----------|-----------|
| `is-json` / `contains-json` | JSON | 整段或片段为 JSON（可带 Schema） | <pre>- type: is-json<br>  value:<br>    type: object<br>    required: [name]</pre> |
| `is-xml` / `contains-xml` | XML | XML 结构 | <pre>- type: is-xml<br>  value:<br>    requiredElements: [root.child]</pre> |
| `is-html` / `contains-html` | HTML | HTML 输出 | <pre>- type: contains-html</pre> |
| `is-sql` / `contains-sql` | SQL | SQL 语句或代码块 | <pre>- type: is-sql<br>  value:<br>    databaseType: MySQL</pre> |
| `is-refusal` | 是否拒答 | 检测拒答行为 | <pre>- type: is-refusal</pre> |
| `finish-reason` | 结束原因 | `stop` / `length` / `tool_calls` 等 | <pre>- type: finish-reason<br>  value: stop</pre> |
| `is-valid-function-call` | 合法函数调用 | 函数参数符合 Schema | <pre>- type: is-valid-function-call</pre> |
| `is-valid-openai-function-call` | 合法 OpenAI 函数调用 | OpenAI function calling | <pre>- type: is-valid-openai-function-call</pre> |
| `is-valid-openai-tools-call` | 合法 OpenAI Tools 调用 | 全部 tool calls 合法 | <pre>- type: is-valid-openai-tools-call</pre> |

##### RAG / 上下文

| 类型 | 中文名 | 适用场景 | YAML 示例 |
|------|--------|----------|-----------|
| `context-recall` | 上下文召回 | 事实是否出现在 context | <pre>- type: context-recall<br>  value: 巴黎是法国的首都<br>  threshold: 0.5</pre> |
| `context-relevance` | 上下文相关性 | 检索到的 context 是否相关 | <pre>- type: context-relevance<br>  threshold: 0.5</pre> |
| `context-faithfulness` | 上下文忠实度 | 输出是否胡编、是否忠于 context | <pre>- type: context-faithfulness<br>  threshold: 0.5</pre> |
| `conversation-relevance` | 对话相关性 | 多轮是否始终相关 | <pre>- type: conversation-relevance<br>  threshold: 0.5</pre> |

##### 指标 / 成本

| 类型 | 中文名 | 适用场景 | YAML 示例 |
|------|--------|----------|-----------|
| `cost` | 成本阈值 | 单次调用费用上限 | <pre>- type: cost<br>  threshold: 0.001</pre> |
| `latency` | 耗时阈值 | 延迟（毫秒） | <pre>- type: latency<br>  threshold: 2000</pre> |
| `perplexity` / `perplexity-score` | 困惑度 | 语言模型困惑度 | <pre>- type: perplexity<br>  threshold: 10</pre> |
| `bleu` / `gleu` / `meteor` | 机器翻译指标 | 对照参考译文 | <pre>- type: bleu<br>  value: 猫坐在垫子上<br>  threshold: 0.5</pre> |
| `rouge-n` / `rouge-l` / `rouge-s` | ROUGE | 摘要 / 生成重叠度 | <pre>- type: rouge-l<br>  value: 参考摘要文本<br>  threshold: 0.75</pre> |
| `moderation` | 内容审核 | 安全策略 | <pre>- type: moderation</pre> |
| `guardrails` | 护栏 | 输入/输出护栏信号 | <pre>- type: guardrails</pre> |

##### Agent / Trace

| 类型 | 中文名 | 适用场景 | YAML 示例 |
|------|--------|----------|-----------|
| `tool-call-f1` | 工具调用 F1 | 工具名集合是否接近期望 | <pre>- type: tool-call-f1<br>  value: [search, calculator]<br>  threshold: 0.8</pre> |
| `skill-used` | 技能是否使用 | skill 元数据 | <pre>- type: skill-used<br>  value: web-search</pre> |
| `trajectory:goal-success` | 轨迹目标成功 | Agent 是否达成目标 | <pre>- type: trajectory:goal-success<br>  value: 用户已成功预订机票</pre> |
| `trajectory:tool-used` / `tool-args-match` / `tool-sequence` / `step-count` | 轨迹工具相关 | 工具是否调用、参数、顺序、步数 | <pre>- type: trajectory:tool-used<br>  value: search</pre> |
| `trace-error-spans` / `trace-span-count` / `trace-span-duration` | 追踪 Span | 错误数、数量、耗时 | <pre>- type: trace-span-duration<br>  threshold: 1000</pre> |

##### 特殊

| 类型 | 中文名 | 适用场景 | YAML 示例 |
|------|--------|----------|-----------|
| `select-best` | 选择最优 | 多 prompt/provider 里选最好的 | <pre>- type: select-best<br>  value: 选择事实最准确且最简洁的回答</pre> |
| `human` | 人工评分 | 人工介入 | <pre>- type: human<br>  value: 请按 1-5 分评价有用性</pre> |
| `max-score` | 最高分 | 按其它断言聚合分选优 | <pre>- type: max-score</pre> |
| `assert-set` | 断言集合 | YAML 中把多条断言分组（可视化未单列） | <pre>- type: assert-set<br>  threshold: 0.5<br>  assert:<br>    - type: cost<br>      threshold: 0.001<br>    - type: latency<br>      threshold: 2000</pre> |

### 6.4 测评报告

路径：`/runs`

- 列表：按运行 ID / 任务名称、运行结果筛选；进行中任务会自动轮询
- 详情：`/runs/:id`
  - 汇总条：通过率、通过/失败/错误、耗时
  - 图表：结果分布饼图、Provider 通过率柱状图
  - 详细结果矩阵：测试项 ×（供应商 × 提示词）
  - 筛选：关键词、结果、供应商多选、提示词多选 → 查询 / 重置
  - 下载：JSON / CSV / HTML（官方 promptfoo HTML 新标签页打开）

进行中的任务会自动轮询；后端重启会把未完成的 pending/running 标为 failed。

### 6.5 跑通 Demo（无需 Key）

1. 打开「测评任务」→ **Demo Mock Eval**
2. 确认供应商为 `python:mock_provider.py`，同目录有 `mock_provider.py`
3. 点击「运行」
4. 到报告详情查看 3 条翻译用例结果

## 7. 数据落盘约定

### 配置 `data/configs/{config_id}/`

| 文件 | 说明 |
|------|------|
| `meta.json` | id、名称、描述、时间戳、yaml 全文 |
| `promptfooconfig.yaml` | 实际评测配置 |
| `*.py` 等 | 附属资源（如 mock provider） |

### 运行 `data/runs/{run_id}/`

| 文件 | 说明 |
|------|------|
| `meta.json` | 状态、计数、通过率、错误信息 |
| `promptfooconfig.yaml` | 运行时拷贝 |
| `results.json` | promptfoo JSON 输出 |
| `report.html` | promptfoo HTML 报告 |
| `stdout.log` / `stderr.log` | 进程日志 |

`data/configs`、`data/runs`、`data/reports` 默认在 `.gitignore` 中，勿提交密钥。

---

## 8. HTTP API

前缀：`/api`

| Method | Path | 说明 |
|--------|------|------|
| GET | `/health` | 健康检查 |
| GET | `/dashboard/stats` | 配置数、运行数、平均通过率、最近运行 |
| GET | `/configs` | 配置列表 |
| POST | `/configs` | 创建 `{ name, description?, yaml_content }` |
| GET | `/configs/{id}` | 详情 |
| PUT | `/configs/{id}` | 更新 |
| DELETE | `/configs/{id}` | 删除 |
| GET | `/runs` | 运行列表 |
| POST | `/runs` | 启动 `{ config_id, max_concurrency?, cache?, description? }` |
| GET | `/runs/{id}` | 详情（含 stdout/stderr、结果引用） |
| GET | `/runs/{id}/report` | 结构化报告视图（前端矩阵用） |
| GET | `/runs/{id}/report.json` | 下载 JSON |
| GET | `/runs/{id}/report.html` | 内联 HTML |
| GET | `/runs/{id}/report.csv` | 下载 CSV |

运行状态枚举：`pending` | `running` | `succeeded` | `failed`。

---

## 9. 前端模块说明

| 路径 | 职责 |
|------|------|
| `layouts/AppLayout.vue` | 侧栏导航（测评任务 / 测评报告） |
| `views/ConfigsView.vue` | 任务列表、筛选、新建 |
| `views/ConfigDetailView.vue` | 分步可视化 / YAML、保存、运行 |
| `views/RunsView.vue` | 报告列表与筛选 |
| `views/ReportView.vue` | 报告详情、图表、矩阵筛选 |
| `components/VisualConfigForm.vue` | 可视化表单 |
| `utils/promptfooConfig.ts` | YAML ↔ VisualConfig；DeepSeek 等别名解析 |
| `api/client.ts` | 统一 API 客户端 |

路由：

| Path | 页面 |
|------|------|
| `/configs` | 测评任务 |
| `/configs/:id` | 任务详情 |
| `/runs` | 测评报告列表 |
| `/runs/:id` | 报告详情 |

开发时改 UI 后热更新即可；涉及 API 契约时同步改 `frontend/src/types/index.ts` 与后端 `schemas.py`。

---

## 10. 后端模块说明

| 模块 | 职责 |
|------|------|
| `services/store.py` | 配置 / 运行的文件存储与 YAML 校验 |
| `services/promptfoo_runner.py` | 异步拉起 promptfoo、写日志、汇总状态 |
| `services/report_builder.py` | 将 results.json 转成前端报告视图与 CSV |
| `services/seed.py` | 首次启动写入示例配置与 samples |
| `core/config.py` | `data_dir`、CORS、promptfoo 命令解析 |

Promptfoo 命令解析优先级：

1. Settings 中的 `promptfoo_bin`
2. `tools/node_modules/.bin/promptfoo`
3. 回退 `npx --yes promptfoo@0.125.1`

---

*文档版本与仓库代码同步维护。若行为与文档不一致，以代码与 `/api/docs` 为准。*
