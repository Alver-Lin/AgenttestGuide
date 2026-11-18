/**
 * Skill: extract-keywords
 *
 * Contract (product):
 * 1. Spider must finish reading the full article before any final keyword answer.
 * 2. No AI → local RAKE-style extraction over the full article (top 10).
 * 3. AI on → this skill produces more reasonable / human navigational keywords;
 *    on failure, fall back to (2).
 */

import { chatCompletion, isAiReady, AiClientError } from '../../ai/client'
import { extractKeywords, type Keyword } from '../keywords'
import { appSettings } from '../../useSettings'

export const EXTRACT_KEYWORDS_SKILL = {
  name: 'extract-keywords',
  version: 3,
  description:
    '通读全文后生成关键词：无 AI 用本地 RAKE；有 AI 用本技能做更合理的人性化抽取。',
} as const

/**
 * AI path differentiator vs local RAKE.
 * Local RAKE = statistical phrase salience; this skill = teaching / navigation salience.
 */
export const EXTRACT_KEYWORDS_SYSTEM = `你正在执行 AgenttestGuide 阅读器技能「extract-keywords」(v3)。
场景：小蜘蛛已经通读完整篇笔记，现在要给出最终的最多 {{max}} 个关键词答案。

# 与本地兜底的差别（必须赢在这里）

本地无 AI 时使用轻量 RAKE：停用词切分候选短语，再按词频 · 共现 · 词长打分取 Top {{max}}。
它比纯词频合理（能保住「Model Context Protocol」这类搭配），但仍分不清：
- 高频套话 vs 真正概念
- 文章结构角色（定义 / 流程 / API / 坑点）
- 本篇特有术语 vs 通用空话

你的答案必须更合理、更人性化：
1. **主线优先**：若读者只记住 {{max}} 个词，应能复述本文主题与关键结构（是什么 / 怎么做 / 关键接口或对象）。
2. **教学显著性 > 统计显著性**：低频但处在定义句、标题、步骤核心的术语，可以压过 RAKE 高分套话。
3. **完整专名**：保留原文规范写法（MCP、Model Context Protocol、ClientSession、FastAPI…）；不要拆成无弱碎片。
4. **可落地**：phrase 必须在原文中真实出现（标题或正文为宜），方便在页面上定位高亮。
5. **去套话**：不要选「可以、通过、进行、我们、使用、如下、问题、方法、内容」这类空词。
6. **多样性**：避免十个近义重复；中英文专名按原文。
7. **排序**：按「对理解本篇的重要性」降序，绝不是按 RAKE 分数或出现次数。

# 输出（严格）

只输出 JSON，不要 Markdown 围栏，不要解释：
{"keywords":[{"phrase":"原文短语","count":出现次数估计,"reason":"≤16字：为何比本地 RAKE 更值得作为答案"}]}`

/** Safety cap only; prefer sending the full article when possible. */
const MAX_ARTICLE_CHARS = 100_000

export type KeywordSource = 'ai' | 'local'

export type ResolveKeywordsResult = {
  keywords: Keyword[]
  source: KeywordSource
  note?: string
}

function stripForModel(raw: string): string {
  return raw
    .replace(/```[\s\S]*?```/g, '\n[代码块已省略]\n')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '§ ')
    .replace(/[*_~>|-]{2,}/g, ' ')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function buildUserPrompt(article: string, max: number): string {
  const body =
    article.length > MAX_ARTICLE_CHARS
      ? `${article.slice(0, MAX_ARTICLE_CHARS)}\n\n[正文过长已截断，请基于已给全文部分作答]`
      : article
  return `小蜘蛛已通读全文。请给出最终最多 ${max} 个关键词。

对照：
- 本地兜底是 RAKE 统计短语——你必须明显优于「高频搭配/碎片」水准
- 你应交更合理、更人性化、能代表文章主线的 ${max} 个词

笔记正文（§ = 原标题）：
---
${body}
---`
}

/** Parse model output into Keyword[]; returns [] if unusable. */
export function parseKeywordSkillResponse(raw: string, max = 10): Keyword[] {
  const trimmed = raw.trim()
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const jsonText = (fenced?.[1] || trimmed).trim()

  let parsed: unknown
  try {
    parsed = JSON.parse(jsonText)
  } catch {
    const start = jsonText.indexOf('{')
    const end = jsonText.lastIndexOf('}')
    if (start < 0 || end <= start) return []
    try {
      parsed = JSON.parse(jsonText.slice(start, end + 1))
    } catch {
      return []
    }
  }

  const list = Array.isArray(parsed)
    ? parsed
    : parsed &&
        typeof parsed === 'object' &&
        Array.isArray((parsed as { keywords?: unknown }).keywords)
      ? (parsed as { keywords: unknown[] }).keywords
      : null
  if (!list) return []

  const out: Keyword[] = []
  const seen = new Set<string>()
  for (const item of list) {
    if (out.length >= max) break
    let phrase = ''
    let count = 1
    if (typeof item === 'string') {
      phrase = item.trim()
    } else if (item && typeof item === 'object') {
      const row = item as { phrase?: unknown; key?: unknown; count?: unknown }
      phrase = String(row.phrase ?? row.key ?? '').trim()
      const n = Number(row.count)
      if (Number.isFinite(n) && n > 0) count = Math.floor(n)
    }
    if (!phrase || phrase.length > 48) continue
    if (/^(的|了|是|在|和|与|或|等|可以|通过|进行|使用|我们|这个|一个|方法|问题|内容)$/u.test(phrase)) {
      continue
    }
    const key = phrase.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ phrase, key, score: max - out.length, count })
  }
  return out
}

export async function extractKeywordsWithAi(
  raw: string,
  max = 10,
  signal?: AbortSignal,
): Promise<Keyword[]> {
  const article = stripForModel(raw)
  if (!article) return []

  const system = EXTRACT_KEYWORDS_SYSTEM.replace(/\{\{max\}\}/g, String(max))
  const content = await chatCompletion({
    temperature: 0.15,
    // JSON answer is short; keep headroom. Thinking is disabled in the client
    // so DeepSeek won't burn the budget on reasoning_content.
    maxTokens: 1600,
    thinking: 'disabled',
    signal,
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: buildUserPrompt(article, max) },
    ],
  })

  return parseKeywordSkillResponse(content, max)
}

/** After full-article read: AI skill if ready, else RAKE; AI errors → RAKE. */
export async function resolveKeywords(
  raw: string,
  max = 10,
  signal?: AbortSignal,
): Promise<ResolveKeywordsResult> {
  const local = () => ({
    keywords: extractKeywords(raw, max),
    source: 'local' as const,
  })

  if (!isAiReady(appSettings.ai)) {
    return { ...local(), note: '未启用 AI · 本地 RAKE' }
  }

  try {
    const keywords = await extractKeywordsWithAi(raw, max, signal)
    if (!keywords.length) {
      return { ...local(), note: 'AI 无有效结果 · 已回退本地 RAKE' }
    }
    return { keywords, source: 'ai', note: 'AI skill · 人性化关键词' }
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') throw err
    const reason =
      err instanceof AiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : 'AI 调用失败'
    return { ...local(), note: `${reason} · 已回退本地 RAKE` }
  }
}
