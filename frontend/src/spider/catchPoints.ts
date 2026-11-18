import type { Keyword } from './keywords'

/** A token in the article with a stable DOM anchor for live remeasurement. */
export type WordHit = {
  text: string
  norm: string
  node: Text
  start: number
  end: number
  /** Last measured screen-space box (CSS px, viewport). */
  x: number
  y: number
  w: number
  h: number
}

export type CatchPoint = {
  key: string
  phrase: string
  index: number
  /** Inclusive end word index for multi-token phrases. */
  endIndex: number
  x: number
  y: number
  w: number
  h: number
}

export type ScreenBox = { x: number; y: number; w: number; h: number }

/** Fresh viewport box for a text range; null if not laid out / zero-size. */
export function measureRange(node: Text, start: number, end: number): ScreenBox | null {
  if (!node.isConnected) return null
  const len = node.data.length
  const a = Math.max(0, Math.min(start, len))
  const b = Math.max(a, Math.min(end, len))
  if (b <= a) return null
  const range = document.createRange()
  range.setStart(node, a)
  range.setEnd(node, b)
  const rect = range.getBoundingClientRect()
  if (rect.width < 0.5 || rect.height < 0.5) return null
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
    w: rect.width,
    h: rect.height,
  }
}

export function measureWord(hit: WordHit): ScreenBox | null {
  const box = measureRange(hit.node, hit.start, hit.end)
  if (!box) return null
  hit.x = box.x
  hit.y = box.y
  hit.w = box.w
  hit.h = box.h
  return box
}

/** Union box covering words[from..to] (inclusive), remeasured live. */
export function measureWordSpan(words: WordHit[], from: number, to: number): ScreenBox | null {
  let left = Infinity
  let top = Infinity
  let right = -Infinity
  let bottom = -Infinity
  let any = false
  for (let i = from; i <= to; i++) {
    const w = words[i]
    if (!w) continue
    const box = measureWord(w)
    if (!box) continue
    any = true
    left = Math.min(left, box.x - box.w / 2)
    right = Math.max(right, box.x + box.w / 2)
    top = Math.min(top, box.y - box.h / 2)
    bottom = Math.max(bottom, box.y + box.h / 2)
  }
  if (!any) return null
  return {
    x: (left + right) / 2,
    y: (top + bottom) / 2,
    w: Math.max(right - left, 24),
    h: Math.max(bottom - top, 14),
  }
}

function pushCatchPoint(
  points: CatchPoint[],
  kw: Keyword,
  words: WordHit[],
  from: number,
  to: number,
) {
  const box = measureWordSpan(words, from, to)
  const mid = words[Math.floor((from + to) / 2)] || words[from]
  points.push({
    key: kw.key,
    phrase: kw.phrase,
    index: from,
    endIndex: to,
    x: box?.x ?? mid.x,
    y: box?.y ?? mid.y,
    w: box?.w ?? Math.max(mid.w, 24),
    h: box?.h ?? Math.max(mid.h, 14),
  })
}

function matchKeywordAt(
  words: WordHit[],
  kw: Keyword,
  i: number,
): { from: number; to: number } | null {
  const parts = kw.key.split(/\s+/).filter(Boolean)

  // 1) token sequence (English phrases / spaced keys)
  if (parts.length > 1 || (parts.length === 1 && !/[\u4e00-\u9fff]/.test(kw.phrase))) {
    let ok = true
    for (let j = 0; j < parts.length; j++) {
      const w = words[i + j]
      if (!w || (w.norm !== parts[j] && w.text !== parts[j] && w.norm !== kw.key)) {
        ok = false
        break
      }
    }
    if (ok) return { from: i, to: i + parts.length - 1 }
  }

  // 2) Chinese / mixed: concatenate nearby glyphs until phrase matches exactly
  if (/[\u4e00-\u9fff]/.test(kw.phrase)) {
    let joined = ''
    for (let end = i; end < Math.min(words.length, i + kw.phrase.length + 2); end++) {
      const w = words[end]
      if (!w) break
      joined += w.text
      if (joined === kw.phrase) return { from: i, to: end }
      if (joined.length > kw.phrase.length) break
      if (!/[\u4e00-\u9fffA-Za-z0-9]/.test(w.text)) break
    }
  }

  // 3) exact single token
  const w = words[i]
  if (w && (w.text === kw.phrase || w.norm === kw.key)) return { from: i, to: i }

  return null
}

/** First hit per keyword (legacy crawl targeting). */
export function findCatchPoints(words: WordHit[], kws: Keyword[]): CatchPoint[] {
  const points: CatchPoint[] = []
  const used = new Set<number>()

  for (const kw of kws) {
    if (points.length >= 10) break
    for (let i = 0; i < words.length; i++) {
      if (used.has(i)) continue
      const hit = matchKeywordAt(words, kw, i)
      if (!hit) continue
      for (let k = hit.from; k <= hit.to; k++) used.add(k)
      pushCatchPoint(points, kw, words, hit.from, hit.to)
      break
    }
  }

  return points.sort((a, b) => a.index - b.index)
}

/**
 * Every occurrence of every keyword in the article (for final highlight).
 * Caps total marks for draw performance on very long notes.
 */
export function findAllKeywordSpans(
  words: WordHit[],
  kws: Keyword[],
  max = 500,
): CatchPoint[] {
  const points: CatchPoint[] = []

  for (const kw of kws) {
    for (let i = 0; i < words.length; i++) {
      if (points.length >= max) return points.sort((a, b) => a.index - b.index)
      const hit = matchKeywordAt(words, kw, i)
      if (!hit) continue
      // Skip overlapping continuation of the same match window
      if (points.some((p) => p.key === kw.key && !(hit.to < p.index || hit.from > p.endIndex))) {
        continue
      }
      pushCatchPoint(points, kw, words, hit.from, hit.to)
      // Advance past this match so we don't re-hit the same span
      i = hit.to
    }
  }

  return points.sort((a, b) => a.index - b.index)
}
