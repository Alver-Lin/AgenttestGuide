/** Local keyword fallback: lightweight RAKE-style extraction for zh/en. */

export interface Keyword {
  phrase: string
  key: string
  score: number
  count: number
}

const EN_STOP = new Set(
  `a an the and or but if then else when at by for with about against between into through during before after above below to from up down in out on off over under again further once here there all any both each few more most other some such no nor not only own same so than too very can will just should now is are was were be been being do does did doing have has had having of this that these those i you he she it we they me him her us them my your his its our their what which who whom whose as also than while because although though until while of into onto upon via per vs etc etc. via`.split(
    /\s+/,
  ),
)

const ZH_STOP = new Set(
  `的 了 在 是 我 有 和 就 不 人 都 一 一个 上 也 很 到 说 要 去 你 会 着 没有 看 好 自己 这 那 他 她 它 们 与 及 或 而 被 把 让 从 对 于 中 以 为 之 其 等 并 但 却 则 已 将 还 又 更 最 什么 怎么 如何 为什么 可以 可能 应该 需要 进行 通过 以及 如果 因为 所以 因此 然而 虽然 但是 关于 由于 根据 其中 这些 那些 这个 那个 一种 一些 我们 你们 他们 自己 什么 哪个 哪些 不是 没有 已经 正在 能够 作为 包括 例如 比如 等等 方面 问题 时候 之后 之前 之间 之后`.split(
    /\s+/,
  ),
)

export interface Token {
  text: string
  norm: string
  start: number
  end: number
  boundaryBefore: boolean
}

function segmenter(lang: string) {
  try {
    return new Intl.Segmenter(lang, { granularity: 'word' })
  } catch {
    return new Intl.Segmenter('en', { granularity: 'word' })
  }
}

export function detectLang(text: string): 'zh' | 'en' {
  const cjk = (text.match(/[\u4e00-\u9fff]/g) || []).length
  const latin = (text.match(/[A-Za-z]/g) || []).length
  return cjk > latin ? 'zh' : 'en'
}

export function tokenize(text: string): Token[] {
  const lang = detectLang(text)
  const seg = segmenter(lang === 'zh' ? 'zh-CN' : 'en')
  const out: Token[] = []
  let boundary = true
  for (const part of seg.segment(text)) {
    if (!part.isWordLike) {
      if (/[.,;:!?()[\]{}"“”「」『』、，。！？；：…\n]/.test(part.segment)) boundary = true
      continue
    }
    const surface = part.segment
    if (!/\p{L}/u.test(surface) && !/[\u4e00-\u9fff]/.test(surface)) {
      boundary = true
      continue
    }
    const norm = surface.toLowerCase()
    out.push({
      text: surface,
      norm,
      start: part.index,
      end: part.index + surface.length,
      boundaryBefore: boundary,
    })
    boundary = false
  }
  return out
}

function isStop(norm: string, text: string): boolean {
  if (EN_STOP.has(norm)) return true
  if (ZH_STOP.has(text) || ZH_STOP.has(norm)) return true
  if (/^[\u4e00-\u9fff]$/.test(text)) return true // single CJK char usually weak alone
  if (/^[a-z]$/.test(norm)) return true
  return false
}

function isContent(t: Token): boolean {
  if (isStop(t.norm, t.text)) return false
  if (/^[\u4e00-\u9fff]+$/.test(t.text)) return t.text.length >= 2
  return t.norm.length >= 3
}

function scrubArticle(raw: string): string {
  return raw
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`[^`]+`/g, ' ')
    .replace(/!\[[^\]]*\]\([^)]+\)/g, ' ')
    .replace(/\[[^\]]*\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/[*_~>|-]+/g, ' ')
}

/**
 * Non-AI path: RAKE-style keyword extraction over the full article.
 * Candidate phrases are split on stop words / boundaries, then scored by
 * frequency · co-occurrence · length (not raw unigram count alone).
 */
export function extractKeywords(raw: string, max = 10): Keyword[] {
  if (!raw.trim()) return []
  const text = scrubArticle(raw)
  const tokens = tokenize(text)
  if (!tokens.length) return []

  const content = tokens.map(isContent)
  const freq = new Map<string, number>()
  for (let i = 0; i < tokens.length; i++) {
    if (!content[i]) continue
    freq.set(tokens[i].norm, (freq.get(tokens[i].norm) ?? 0) + 1)
  }

  type Cand = {
    key: string
    words: string[]
    count: number
    surfaces: Map<string, number>
    score: number
  }
  const cands = new Map<string, Cand>()
  const push = (from: number, to: number) => {
    const words: string[] = []
    for (let k = from; k <= to; k++) words.push(tokens[k].norm)
    const key = words.join(' ')
    let c = cands.get(key)
    if (!c) {
      c = { key, words, count: 0, surfaces: new Map(), score: 0 }
      cands.set(key, c)
    }
    c.count++
    const surface = text.slice(tokens[from].start, tokens[to].end).replace(/\s+/g, ' ').trim()
    if (surface) c.surfaces.set(surface, (c.surfaces.get(surface) ?? 0) + 1)
  }

  let run = -1
  const flush = (end: number) => {
    if (run < 0) return
    for (let i = run; i < end; i++) {
      for (let n = 1; n <= 3 && i + n - 1 < end; n++) push(i, i + n - 1)
    }
    run = -1
  }
  for (let i = 0; i < tokens.length; i++) {
    if (!content[i] || tokens[i].boundaryBefore) flush(i)
    if (content[i] && run < 0) run = i
  }
  flush(tokens.length)

  const wordWeight = (w: string) => {
    const f = freq.get(w) ?? 1
    const len = Math.min(1.4, Math.max(0.8, 0.6 + w.length / 10))
    return len * (1 + Math.log1p(f) * 0.15)
  }

  const scored: Cand[] = []
  for (const c of cands.values()) {
    if (c.words.length > 1 && c.count < 2) continue
    if (new Set(c.words).size !== c.words.length) continue
    const weight = c.words.reduce((s, w) => s + wordWeight(w), 0)
    let cohesion = 1
    if (c.words.length > 1) {
      const minFreq = Math.min(...c.words.map((w) => freq.get(w) ?? 1))
      cohesion = 1.15 * (0.5 + 0.5 * Math.min(1, c.count / minFreq))
    }
    c.score = Math.pow(c.count, 0.9) * weight * cohesion
    scored.push(c)
  }
  scored.sort((a, b) => (b.count >= 2 ? 1 : 0) - (a.count >= 2 ? 1 : 0) || b.score - a.score)

  const contains = (big: string[], small: string[]) => {
    outer: for (let i = 0; i + small.length <= big.length; i++) {
      for (let j = 0; j < small.length; j++) if (big[i + j] !== small[j]) continue outer
      return true
    }
    return false
  }

  const selected: Cand[] = []
  for (const c of scored) {
    if (selected.length >= max) break
    if (selected.some((s) => contains(s.words, c.words))) continue
    const subs = selected.filter((s) => contains(c.words, s.words))
    if (!subs.length) {
      selected.push(c)
      continue
    }
    const strongest = Math.max(...subs.map((s) => s.score))
    if (c.count >= 2 && c.score >= 0.3 * strongest) {
      for (const s of subs) selected.splice(selected.indexOf(s), 1)
      selected.push(c)
    }
  }

  return selected.slice(0, max).map((c) => {
    let phrase = ''
    let best = -1
    for (const [surface, n] of c.surfaces) {
      if (n > best) {
        phrase = surface
        best = n
      }
    }
    return { phrase, key: c.key, score: c.score, count: c.count }
  })
}
