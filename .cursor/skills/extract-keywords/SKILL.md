---
name: extract-keywords
description: >-
  Full-article keyword answers for the AgenttestGuide spider. No AI: local RAKE.
  AI on: extract-keywords skill for human navigational keywords. Always finish
  reading before answering. Use when editing crawl, spider, or this skill.
---

# Extract Keywords（爬取关键词）

## 产品合同（必须遵守）

1. **先通读，后给答案**：小蜘蛛走完整文路径之前，不得打开最终关键词结果。
2. **无 AI**：全文跑本地轻量 **RAKE**，取最多 10 个关键词（`extractKeywords`）。
3. **有 AI**：通读结束后调用本 skill，生成更合理、更人性化的最多 10 个关键词；失败则回退到 (2)。

## 两种答案差在哪

| | 无 AI（本地 RAKE） | 有 AI（本技能） |
|--|--|--|
| 时机 | 通读全文之后 | 通读全文之后 |
| 算法 | 停用词切分 + 词频/共现/词长打分 | 语义 / 教学导航显著性 |
| 典型结果 | 统计上显著的短语搭配 | 主线术语、定义项、关键 API、完整专名 |

## Runtime

1. `beginCrawl` → 只建通读路径（无预计算抓取点）
2. 路径走完 → `finalizeAfterRead` → `resolveKeywords`
3. `isAiReady()` → AI skill；否则或失败 → 本地 RAKE
4. 定位高亮 + 打开结果面板

文件：

- 编排：`frontend/src/SpiderOverlay.vue`
- Skill：`frontend/src/spider/skills/extractKeywordsSkill.ts`（`EXTRACT_KEYWORDS_SYSTEM`）
- RAKE：`frontend/src/spider/keywords.ts`
- 客户端：`frontend/src/ai/client.ts`

### 输出契约（AI）

```json
{"keywords":[{"phrase":"原文短语","count":1,"reason":"为何值得作为答案"}]}
```

## Agent 约定

- 不要改回「先抽 10 词再爬、抓满即停」
- 不要删 RAKE 兜底；不要把 API Key 写入仓库
