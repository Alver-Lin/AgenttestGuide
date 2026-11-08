import type { TextAnchor } from './types'

export interface AnchorRange {
  start: number
  end: number
}
export interface HighlightSpan extends AnchorRange {
  id: string
  draft?: boolean
  kind?: 'comment' | 'bookmark'
}

export interface HighlightSegment {
  start: number
  end: number
  commentIds: string[]
  bookmarkIds: string[]
  draft: boolean
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

export function highlightSegments(length: number, spans: HighlightSpan[]): HighlightSegment[] {
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
      commentIds: [
        ...new Set(
          matching
            .filter((span) => (span.kind || 'comment') === 'comment')
            .map((span) => span.id)
            .filter(Boolean),
        ),
      ],
      bookmarkIds: [
        ...new Set(
          matching
            .filter((span) => span.kind === 'bookmark')
            .map((span) => span.id)
            .filter(Boolean),
        ),
      ],
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

export function selectionRect(host: HTMLElement): DOMRect | null {
  const selection = host.ownerDocument.getSelection()
  if (!selection || selection.isCollapsed || selection.rangeCount !== 1) return null
  const range = selection.getRangeAt(0)
  if (!host.contains(range.startContainer) || !host.contains(range.endContainer)) return null
  const rects = [...range.getClientRects()].filter((rect) => rect.width || rect.height)
  return rects[rects.length - 1] || range.getBoundingClientRect()
}

/** Split text nodes rather than changing Markdown or replacing HTML with untrusted text. */
export function paintHighlights(
  host: HTMLElement,
  spans: HighlightSpan[],
  activeCommentId: string,
  activeBookmarkId = '',
) {
  for (const mark of [...host.querySelectorAll('mark[data-annotation]')]) {
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
    if (parts.some((part) => part.commentIds.length || part.bookmarkIds.length || part.draft)) {
      const fragment = host.ownerDocument.createDocumentFragment()
      for (const part of parts) {
        const text = value.slice(
          Math.max(0, part.start - offset),
          Math.min(value.length, part.end - offset),
        )
        if (part.commentIds.length || part.bookmarkIds.length || part.draft) {
          const mark = host.ownerDocument.createElement('mark')
          const classes = ['annotation-highlight']
          if (part.commentIds.length || part.draft) classes.push('comment-highlight')
          if (part.bookmarkIds.length) classes.push('bookmark-highlight')
          if (part.commentIds.includes(activeCommentId) || part.bookmarkIds.includes(activeBookmarkId))
            classes.push('is-active')
          if (part.draft) classes.push('is-draft')
          mark.className = classes.join(' ')
          mark.dataset.annotation = 'true'
          if (part.commentIds.length) mark.dataset.commentIds = part.commentIds.join(' ')
          if (part.bookmarkIds.length) mark.dataset.bookmarkIds = part.bookmarkIds.join(' ')
          mark.textContent = text
          mark.title = part.draft
            ? '正在为这段文字添加注释'
            : part.bookmarkIds.length && !part.commentIds.length
              ? '查看书签'
              : part.commentIds.length && !part.bookmarkIds.length
                ? '查看注释'
                : '查看标注'
          fragment.append(mark)
        } else fragment.append(host.ownerDocument.createTextNode(text))
      }
      textNode.replaceWith(fragment)
    }
    offset = end
  }
}
