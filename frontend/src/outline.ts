export interface OutlineItem {
  id: string
  level: number
  text: string
}

/** Collect h1–h3 headings while skipping fenced code blocks. */
export function extractOutline(content: string): OutlineItem[] {
  const items: OutlineItem[] = []
  let index = 0
  let inFence = false
  for (const line of (content || '').split(/\r?\n/)) {
    if (/^(`{3,}|~{3,})/.test(line.trimStart())) {
      inFence = !inFence
      continue
    }
    if (inFence) continue
    const match = /^(#{1,3})\s+(.+)$/.exec(line)
    if (!match) continue
    const text = match[2]
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/[*_`~]+/g, '')
      .trim()
    if (!text) continue
    items.push({ id: `heading-${index++}`, level: match[1].length, text })
  }
  return items
}

export function outlineHasChildren(items: OutlineItem[], index: number): boolean {
  const level = items[index]?.level
  if (level == null) return false
  for (let i = index + 1; i < items.length; i++) {
    if (items[i].level <= level) return false
    return true
  }
  return false
}

export function outlineItemVisible(
  items: OutlineItem[],
  index: number,
  collapsedIds: ReadonlySet<string>,
): boolean {
  let currentLevel = items[index]?.level
  if (currentLevel == null) return false
  for (let i = index - 1; i >= 0; i--) {
    if (items[i].level < currentLevel) {
      if (collapsedIds.has(items[i].id)) return false
      currentLevel = items[i].level
    }
  }
  return true
}

export function collapsibleOutlineIds(items: OutlineItem[]): string[] {
  return items.filter((_, index) => outlineHasChildren(items, index)).map((item) => item.id)
}
