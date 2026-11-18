# FastAPI 实战：测评成绩管理 API

本篇对应 [FastAPI 全景地图](./0-全景地图.md) 的第 **6** 层，把前几篇串成一个可运行的小服务。

**学习目标**：实现成绩的增删改查、及格筛选与平均分统计；用 `/docs` 与 Apifox 完成联调；对照 REST 语义检查方法和状态码。

数据存在**进程内存**中，重启服务会清空——这是刻意简化，便于把注意力放在接口设计上。

---

## 1｜接口一览

| 方法 | 路径 | 说明 | 成功状态码 |
|------|------|------|------------|
| GET | `/health` | 健康检查 | 200 |
| GET | `/scores` | 列表；支持 `passed_only`、`min_score` | 200 |
| POST | `/scores` | 创建成绩 | 201 |
| GET | `/scores/{score_id}` | 按 ID 查询 | 200 |
| PUT | `/scores/{score_id}` | 整体更新 | 200 |
| PATCH | `/scores/{score_id}` | 局部更新 | 200 |
| DELETE | `/scores/{score_id}` | 删除 | 204 |
| GET | `/scores/stats/summary` | 人数、平均分、及格率 | 200 |

资源命名与方法语义见 [RESTful 使用方法](../RESTful使用方法.md)。

---

## 2｜项目文件

### 2.1 目录

```text
score-api/
├── main.py
├── requirements.txt
├── schemas.py
└── routers/
    ├── __init__.py
    └── scores.py
```

`routers/__init__.py` 可留空。

### 2.2 requirements.txt

```text
fastapi[standard]>=0.115.0
```

安装：

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 2.3 schemas.py

```python
from pydantic import BaseModel, Field


class ScoreCreate(BaseModel):
    name: str = Field(min_length=1, max_length=32, examples=["小林"])
    score: int = Field(ge=0, le=100, examples=[85])
    course: str = Field(default="Python", min_length=1, max_length=64)


class ScoreUpdate(BaseModel):
    """PUT：要求提交完整可写字段。"""

    name: str = Field(min_length=1, max_length=32)
    score: int = Field(ge=0, le=100)
    course: str = Field(min_length=1, max_length=64)


class ScorePatch(BaseModel):
    """PATCH：字段均可选，只更新提供的项。"""

    name: str | None = Field(default=None, min_length=1, max_length=32)
    score: int | None = Field(default=None, ge=0, le=100)
    course: str | None = Field(default=None, min_length=1, max_length=64)


class ScoreOut(BaseModel):
    id: int
    name: str
    score: int
    course: str
    passed: bool


class ScoreSummary(BaseModel):
    count: int
    average: float | None
    pass_rate: float | None
```

### 2.4 routers/scores.py

```python
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status

from schemas import ScoreCreate, ScoreOut, ScorePatch, ScoreSummary, ScoreUpdate

router = APIRouter(prefix="/scores", tags=["成绩"])

_STORE: dict[int, ScoreOut] = {}
_NEXT_ID = 1


def _to_out(score_id: int, name: str, score: int, course: str) -> ScoreOut:
    return ScoreOut(
        id=score_id,
        name=name,
        score=score,
        course=course,
        passed=score >= 60,
    )


@router.get("/stats/summary", response_model=ScoreSummary)
def summary():
    rows = list(_STORE.values())
    if not rows:
        return ScoreSummary(count=0, average=None, pass_rate=None)
    average = sum(r.score for r in rows) / len(rows)
    passed = sum(1 for r in rows if r.passed)
    return ScoreSummary(
        count=len(rows),
        average=round(average, 2),
        pass_rate=round(passed / len(rows), 4),
    )


@router.get("", response_model=list[ScoreOut])
def list_scores(
    passed_only: bool = False,
    min_score: Annotated[int, Query(ge=0, le=100)] = 0,
):
    rows = [r for r in _STORE.values() if r.score >= min_score]
    if passed_only:
        rows = [r for r in rows if r.passed]
    return rows


@router.post("", response_model=ScoreOut, status_code=status.HTTP_201_CREATED)
def create_score(payload: ScoreCreate):
    global _NEXT_ID
    for row in _STORE.values():
        if row.name == payload.name and row.course == payload.course:
            raise HTTPException(status_code=409, detail="同课程下已存在同名成绩")
    row = _to_out(_NEXT_ID, payload.name, payload.score, payload.course)
    _STORE[_NEXT_ID] = row
    _NEXT_ID += 1
    return row


@router.get("/{score_id}", response_model=ScoreOut)
def get_score(score_id: int):
    row = _STORE.get(score_id)
    if row is None:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    return row


@router.put("/{score_id}", response_model=ScoreOut)
def replace_score(score_id: int, payload: ScoreUpdate):
    if score_id not in _STORE:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    row = _to_out(score_id, payload.name, payload.score, payload.course)
    _STORE[score_id] = row
    return row


@router.patch("/{score_id}", response_model=ScoreOut)
def patch_score(score_id: int, payload: ScorePatch):
    old = _STORE.get(score_id)
    if old is None:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    data = old.model_dump()
    patch = payload.model_dump(exclude_unset=True)
    data.update(patch)
    row = _to_out(score_id, data["name"], data["score"], data["course"])
    _STORE[score_id] = row
    return row


@router.delete("/{score_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_score(score_id: int):
    if score_id not in _STORE:
        raise HTTPException(status_code=404, detail="成绩记录不存在")
    del _STORE[score_id]
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

注意：`/stats/summary` 写在 `/{score_id}` **之前**，避免 `stats` 被当成 id。

### 2.5 main.py

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import scores

app = FastAPI(
    title="测评成绩 API",
    description="FastAPI 实战：内存版成绩 CRUD",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 仅本地练习；有前端正式联调时改成明确域名
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scores.router)


@app.get("/health", tags=["系统"])
def health():
    return {"status": "ok"}
```

---

## 3｜启动与自测

```bash
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

打开 [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)，按下面顺序点 Execute：

1. `POST /scores` 创建小林 85 分；
2. 再创建小王 55 分；
3. `GET /scores?passed_only=true` 应只看到小林；
4. `GET /scores/stats/summary` 查看平均分与及格率；
5. `PATCH /scores/2`，把小王改为 75；
6. `DELETE /scores/2`，再 `GET /scores/2` 应得到 404。

用 curl 创建：

```bash
curl -X POST http://127.0.0.1:8000/scores \
  -H "Content-Type: application/json" \
  -d '{"name":"小林","score":85}'
```

---

## 4｜用 Apifox 联调

1. 新建 HTTP 项目，环境里设 `baseUrl = http://127.0.0.1:8000`。
2. 按上表建接口；POST/PUT/PATCH 的 Body 选 JSON。
3. 把创建返回的 `id` 填进后续路径参数。
4. 断言建议：`POST` 状态码为 201；`DELETE` 为 204；错误 id 为 404；`score: 120` 为 422。

方法与 Body 填写细节见 [Apifox 的使用方法](../Apifox的使用方法.md)。

也可导入 OpenAPI：浏览器打开 [http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)，在 Apifox 选择导入 OpenAPI。

---

## 5｜设计上值得回看的点

1. **输入/输出模型分离**：`ScoreCreate` / `ScoreUpdate` / `ScorePatch` / `ScoreOut` 各司其职。
2. **PUT vs PATCH**：PUT 带齐字段；PATCH 用 `exclude_unset=True` 只改给出的字段。
3. **409 冲突**：同课程同名视为业务冲突，不是 422。
4. **路由顺序**：静态子路径 `/stats/summary` 优先于 `/{score_id}`。
5. **内存存储**：演示够用；下一步可换成 SQLite / PostgreSQL，接口形状尽量保持不变。

---

## 6｜可选加分扩展

按兴趣选做（不必一次做完）：

- 用 `Depends` 抽出分页参数，列表接口返回 `{items, total, page}`；
- 增加 `GET /scores/export`，返回 CSV（体会非 JSON 响应）；
- 为删除以外的写操作加简单 `X-Api-Key` 依赖；
- 把 `_STORE` 换成 SQLite + `sqlite3` 或 SQLAlchemy。

流式输出、Webhook 等形态见 [接口常见输出方式](../接口常见输出方式.md)。

---

**本节练习（过关任务）**

独立实现本篇 API（可对照上文，但建议先自己写再比对），并满足：

1. CRUD + summary 全部可在 `/docs` 跑通；
2. 非法分数 → 422；不存在 id → 404；同名冲突 → 409；
3. 在 Apifox 中保存至少 4 个用例（创建、查询、筛选、删除）。

**过关标准**：能不看文档说出每个接口的方法与状态码；能解释为何 `/stats/summary` 要写在 `/{score_id}` 前；能用 Apifox 独立完成联调。

返回目录：[FastAPI 全景地图](./0-全景地图.md)。
