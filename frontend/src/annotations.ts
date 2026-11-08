import type { TextAnchor } from './types'

export interface AnchorRange {
  start: number
  end: number
}
export interface HighlightSpan extends AnchorRange {
  id: string
  draft?: boolean
}

function matchingSuffix(a: string, b: string) {
  let count = 0
  while (
    count < a.length &&
    count < b.length &&
    a[a.length - 1 - count] === b[b.length - 1 - count]
  )
    count++
  return count
}
function matchingPrefix(a: string, b: string) {
  let count = 0
  while (count < a.length && count < b.length && a[count] === b[count]) count++
  return count
}

/** Resolve against visible text, using context to disambiguate repeated phrases. */
export function locateAnchor(text: string, anchor: TextAnchor): AnchorRange | null {
  if (!anchor.quote) return null
  const atOriginal = text.slice(anchor.start, anchor.end) === anchor.quote
  if (
    atOriginal &&
    text.slice(Math.max(0, anchor.start - anchor.prefix.length), anchor.start) === anchor.prefix &&
    text.slice(anchor.end, anchor.end + anchor.suffix.length) === anchor.suffix
  ) {
    return { start: anchor.start, end: anchor.end }
  }
  const candidates: { start: number; score: number }[] = []
  let offset = text.indexOf(anchor.quote)
  while (offset !== -1) {
    const end = offset + anchor.quote.length
    const score =
      matchingSuffix(
        text.slice(Math.max(0, offset - anchor.prefix.length), offset),
        anchor.prefix,
      ) + matchingPrefix(text.slice(end, end + anchor.suffix.length), anchor.suffix)
    candidates.push({ start: offset, score })
    offset = text.indexOf(anchor.quote, offset + 1)
  }
  if (candidates.length === 1)
    return { start: candidates[0]!.start, end: candidates[0]!.start + anchor.quote.length }
  candidates.sort((a, b) => b.score - a.score)
  const best = candidates[0]
  if (!best || !best.score || best.score === candidates[1]?.score) return null
  return { start: best.start, end: best.start + anchor.quote.length }
}

export function highlightSegments(length: number, spans: HighlightSpan[]) {
  const valid = spans.filter(
    (span) => span.start >= 0 && span.end <= length && span.end > span.start,
  )
  const boundaries = [
    ...new Set([0, length, ...valid.flatMap((span) => [span.start, span.end])]),
  ].sort((a, b) => a - b)
  return boundaries.slice(0, -1).map((start, index) => {
    const end = boundaries[index + 1]!
    const matching = valid.filter((span) => span.start <= start && span.end >= end)
    return {
      start,
      end,
      ids: [...new Set(matching.map((span) => span.id).filter(Boolean))],
      draft: matching.some((span) => span.draft),
    }
  })
}

export function readSelectionAnchor(host: HTMLElement): TextAnchor | null {
  const selection = host.ownerDocument.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount !== 1) return null
  const range = selection.getRangeAt(0)
  if (!host.contains(range.startContainer) || !host.contains(range.endContainer)) return null
  const quote = range.toString()
  if (!quote.trim() || quote.length > 5000) return null
  const prefixRange = range.cloneRange()
  prefixRange.selectNodeContents(host)
  prefixRange.setEnd(range.startContainer, range.startOffset)
  const start = prefixRange.toString().length
  const text = host.textContent || ''
  const end = start + quote.length
  return {
    quote,
    start,
    end,
    prefix: text.slice(Math.max(0, start - 48), start),
    suffix: text.slice(end, end + 48),
  }
}

/** Split text nodes rather than changing Markdown or replacing HTML with untrusted text. */
export function paintHighlights(host: HTMLElement, spans: HighlightSpan[], activeId: string) {
  for (const mark of [...host.querySelectorAll('mark.comment-highlight[data-annotation]')]) {
    mark.replaceWith(...mark.childNodes)
  }
  host.normalize()
  const nodes: Text[] = []
  const walker = host.ownerDocument.createTreeWalker(host, 4)
  let node: Node | null
  while ((node = walker.nextNode())) nodes.push(node as Text)
  const segments = highlightSegments((host.textContent || '').length, spans)
  let offset = 0
  for (const textNode of nodes) {
    const value = textNode.data
    const end = offset + value.length
    const parts = segments.filter((segment) => segment.start < end && segment.end > offset)
    if (parts.some((part) => part.ids.length || part.draft)) {
      const fragment = host.ownerDocument.createDocumentFragment()
      for (const part of parts) {
        const text = value.slice(
          Math.max(0, part.start - offset),
          Math.min(value.length, part.end - offset),
        )
        if (part.ids.length || part.draft) {
          const mark = host.ownerDocument.createElement('mark')
          mark.className =
            'comment-highlight' +
            (part.ids.includes(activeId) ? ' is-active' : '') +
            (part.draft ? ' is-draft' : '')
          mark.dataset.annotation = 'true'
          mark.dataset.commentIds = part.ids.join(' ')
          mark.textContent = text
          mark.title = part.draft && !part.ids.length ? '正在为这段文字添加评论' : '查看评论'
          fragment.append(mark)
        } else fragment.append(host.ownerDocument.createTextNode(text))
      }
      textNode.replaceWith(fragment)
    }
    offset = end
  }
}
