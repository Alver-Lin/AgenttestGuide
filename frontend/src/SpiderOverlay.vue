<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Spider } from './spider/spider'
import { drawSpider, DEFAULT_DRAW } from './spider/draw'
import { skinById } from './spider/skins'
import type { Keyword } from './spider/keywords'
import {
  findAllKeywordSpans,
  measureRange,
  measureWord,
  measureWordSpan,
  type CatchPoint,
  type WordHit,
} from './spider/catchPoints'
import { isAiReady } from './ai/client'
import { resolveKeywords } from './spider/skills/extractKeywordsSkill'

const props = defineProps<{
  active: boolean
  dark?: boolean
  text?: string
  bodyEl?: HTMLElement | null
  /** Increment to request a keyword crawl (button-driven). */
  crawlRequestId?: number
}>()

const emit = defineEmits<{
  'update:crawling': [value: boolean]
  /** User confirmed the keyword list — parent should insert into article head. */
  confirm: [phrases: string[]]
}>()

function confirmKeywords() {
  const phrases = keywords.value.map((k) => k.phrase).filter(Boolean)
  if (!phrases.length) return
  emit('confirm', phrases)
  panelOpen.value = false
  silk = []
  status.value = '已确认关键词，可继续鼠标跟随'
}

const canvasRef = ref<HTMLCanvasElement | null>(null)
const panelOpen = ref(false)
const status = ref('')
const keywords = ref<Keyword[]>([])
const caught = ref<string[]>([])
const mode = ref<'idle' | 'crawl' | 'play' | 'done'>('idle')

const dpr = Math.min(2, window.devicePixelRatio || 1)
const zoom = 1.25

type Waypoint = {
  wordIndex: number
  endIndex?: number
  catchKey?: string
  phrase?: string
}

type HighlightMark = {
  from: number
  to: number
  a: number
}

let spider: Spider | null = null
let raf = 0
let last = 0
let W = 0
let H = 0
let waypoints: Waypoint[] = []
let wpIndex = 0
/** Seconds spent on the current waypoint without arriving. */
let wpStuck = 0
let silk: Array<{ x: number; y: number }> = []
let highlights: HighlightMark[] = []
let catchMarks: CatchPoint[] = []
/** Stable word list for the active crawl (indices must not reshuffle on scroll). */
let crawlWords: WordHit[] = []
let keywordAbort: AbortController | null = null
/** True while post-read keyword generation is in flight. */
let finalizing = false

function abortKeywordResolve() {
  keywordAbort?.abort()
  keywordAbort = null
  finalizing = false
}

const progress = computed(() => {
  const total = Math.min(10, keywords.value.length || 10)
  return { caught: caught.value.length, total }
})

/** True while analyzing or walking the crawl path. */
const crawlBusy = ref(false)
const crawling = computed(() => crawlBusy.value || mode.value === 'crawl')
watch(crawling, (value) => emit('update:crawling', value), { immediate: true })

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  W = window.innerWidth
  H = window.innerHeight
  canvas.width = Math.round(W * dpr)
  canvas.height = Math.round(H * dpr)
  canvas.style.width = `${W}px`
  canvas.style.height = `${H}px`
}

function toWorld(clientX: number, clientY: number) {
  return {
    x: (clientX - W / 2) / zoom,
    y: (clientY - H / 2) / zoom,
  }
}

function fromWorld(x: number, y: number) {
  return {
    x: x * zoom + W / 2,
    y: y * zoom + H / 2,
  }
}

function collectWords(root: HTMLElement): WordHit[] {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const words: WordHit[] = []
    // CJK as single glyphs so multi-char keywords can be joined precisely for
    // full-article highlighting (greedy {1,8} blocks hide later hits).
    const re = /[\u4e00-\u9fff]|[A-Za-z][A-Za-z0-9+#._-]*/g
  while (walker.nextNode()) {
    const node = walker.currentNode as Text
    const parent = node.parentElement
    if (!parent || parent.closest('code, pre, script, style')) continue
    const text = node.textContent || ''
    let m: RegExpExecArray | null
    re.lastIndex = 0
    while ((m = re.exec(text))) {
      const start = m.index
      const end = m.index + m[0].length
      const box = measureRange(node, start, end)
      // Keep off-screen words (non-zero box) so crawl indices stay stable while scrolling.
      if (!box) continue
      words.push({
        text: m[0],
        norm: m[0].toLowerCase(),
        node,
        start,
        end,
        x: box.x,
        y: box.y,
        w: box.w,
        h: box.h,
      })
    }
  }
  return words
}

function buildWaypoints(words: WordHit[], catches: CatchPoint[]): Waypoint[] {
  if (!words.length) return []
  const catchByIndex = new Map(catches.map((c) => [c.index, c]))
  const path: Waypoint[] = []
  // Dense enough to feel continuous, always spanning the full article.
  const step = Math.max(1, Math.floor(words.length / 120))
  for (let i = 0; i < words.length; i += step) {
    const hit = catchByIndex.get(i)
    path.push({
      wordIndex: i,
      endIndex: hit?.endIndex,
      catchKey: hit?.key,
      phrase: hit?.phrase,
    })
  }
  for (const c of catches) {
    if (path.some((p) => p.catchKey === c.key)) continue
    const wp = {
      wordIndex: c.index,
      endIndex: c.endIndex,
      catchKey: c.key,
      phrase: c.phrase,
    }
    const at = path.findIndex((p) => p.wordIndex > c.index)
    if (at < 0) path.push(wp)
    else path.splice(at, 0, wp)
  }
  // Guarantee the crawl ends at the last word so results wait until "全文读完".
  const last = words.length - 1
  if (path[path.length - 1]?.wordIndex !== last) {
    const hit = catchByIndex.get(last)
    path.push({
      wordIndex: last,
      endIndex: hit?.endIndex,
      catchKey: hit?.key,
      phrase: hit?.phrase,
    })
  }
  return path
}

function liveWord(index: number): WordHit | null {
  if (!crawlWords.length) return null
  const hit = crawlWords[Math.min(Math.max(0, index), crawlWords.length - 1)]
  if (!hit) return null
  measureWord(hit)
  return hit
}

function scrollToward(clientX: number, clientY: number) {
  const pad = 120
  if (clientY < pad) window.scrollBy({ top: clientY - pad, behavior: 'auto' })
  else if (clientY > window.innerHeight - pad)
    window.scrollBy({ top: clientY - (window.innerHeight - pad), behavior: 'auto' })
  // also scroll document reader if present
  const reader = props.bodyEl?.closest('.document-scroll') as HTMLElement | null
  if (reader) {
    const rect = reader.getBoundingClientRect()
    if (clientY < rect.top + pad) reader.scrollTop += clientY - (rect.top + pad)
    else if (clientY > rect.bottom - pad) reader.scrollTop += clientY - (rect.bottom - pad)
  }
  void clientX
}

/**
 * Keep spider + silk locked to page content when the scroller moves the viewport.
 * Without shifting historical silk, the trail freezes in screen space and reads as a
 * horizontal scribble while the article scrolls vertically underneath.
 */
function compensateSpiderForScreenDelta(dx: number, dy: number) {
  if (!spider || (dx === 0 && dy === 0)) return
  const wx = dx / zoom
  const wy = dy / zoom
  spider.pos.x += wx
  spider.pos.y += wy
  spider.goal.x += wx
  spider.goal.y += wy
  for (const p of silk) {
    p.x += wx
    p.y += wy
  }
}

/** Append a silk sample only when the spider actually moved (cleaner vertical path). */
function pushSilk() {
  if (!spider) return
  const cur = { x: spider.pos.x, y: spider.pos.y }
  const prev = silk[silk.length - 1]
  if (prev && Math.hypot(cur.x - prev.x, cur.y - prev.y) < 1.6) return
  silk.push(cur)
  if (silk.length > 600) silk.shift()
}

function advanceWaypoint() {
  wpIndex++
  wpStuck = 0
  if (waypoints.length && mode.value === 'crawl' && !finalizing) {
    const pct = Math.min(99, Math.floor((wpIndex / waypoints.length) * 100))
    status.value = `通读全文中 ${pct}%`
  }
}

function clearCrawlArtifacts() {
  abortKeywordResolve()
  crawlBusy.value = false
  panelOpen.value = false
  caught.value = []
  keywords.value = []
  silk = []
  highlights = []
  catchMarks = []
  crawlWords = []
  waypoints = []
  wpIndex = 0
  wpStuck = 0
  finalizing = false
  status.value = ''
}

/** Idle mouse-follow cosmetic mode (no keyword crawl). */
function beginFollow(clientX = window.innerWidth / 2, clientY = window.innerHeight * 0.35) {
  clearCrawlArtifacts()
  mode.value = 'play'
  ensureSpider(clientX, clientY)
}

/** Cancel crawl / clear marks, but keep current spider pose and keep following the mouse. */
function resumeFollowWithoutReset() {
  clearCrawlArtifacts()
  mode.value = 'play'
  if (!spider) ensureSpider(window.innerWidth / 2, window.innerHeight * 0.35)
}

/**
 * Phase 1: walk the full article. Keywords are NOT finalized here —
 * answers come only after the path reaches the end (see finalizeAfterRead).
 */
async function beginCrawl() {
  if (!props.active) return
  abortKeywordResolve()
  const ac = new AbortController()
  keywordAbort = ac
  crawlBusy.value = true
  panelOpen.value = false
  keywords.value = []
  caught.value = []
  silk = []
  highlights = []
  catchMarks = []
  crawlWords = []
  waypoints = []
  wpIndex = 0
  wpStuck = 0
  finalizing = false
  status.value = '准备通读全文…'

  await nextTick()
  await new Promise((r) => requestAnimationFrame(() => r(null)))
  if (!props.active || ac.signal.aborted) {
    crawlBusy.value = false
    return
  }

  const body = props.bodyEl
  if (!body) {
    status.value = '找不到正文节点，改为自由跟随'
    mode.value = 'play'
    crawlBusy.value = false
    ensureSpider(window.innerWidth / 2, 160)
    return
  }

  body.scrollIntoView({ block: 'start' })
  const scroller = body.closest('.document-scroll') as HTMLElement | null
  if (scroller) scroller.scrollTop = 0
  await nextTick()

  const words = collectWords(body)
  crawlWords = words
  // Reading path only — no precomputed catch targets.
  waypoints = buildWaypoints(words, [])

  if (!waypoints.length) {
    status.value = '正文太短，无法通读'
    mode.value = 'play'
    crawlBusy.value = false
    crawlWords = []
    ensureSpider(window.innerWidth / 2, 160)
    return
  }

  const first = waypoints[0]
  const firstBox =
    measureWordSpan(words, first.wordIndex, first.endIndex ?? first.wordIndex) ||
    words[first.wordIndex] ||
    words[0]
  ensureSpider(firstBox.x, firstBox.y)
  mode.value = 'crawl'
  status.value = isAiReady()
    ? '通读全文中 0% · 读完后由 AI skill 生成关键词'
    : '通读全文中 0% · 读完后用本地 RAKE 提取'
}

function ensureSpider(clientX: number, clientY: number) {
  const pos = toWorld(clientX, clientY)
  if (!spider) spider = new Spider(pos, skinById('blueprint'))
  else spider.jumpTo(pos)
  spider.goal = pos
}

/** Phase 2: only after full-article read — local RAKE or AI skill. */
async function finalizeAfterRead() {
  if (finalizing) return
  finalizing = true
  crawlBusy.value = true
  const ac = keywordAbort
  status.value = isAiReady()
    ? '全文已读完 · 正在用 AI skill 生成关键词…'
    : '全文已读完 · 正在用本地 RAKE 提取关键词…'

  try {
    const text = props.text || props.bodyEl?.innerText || ''
    const resolved = await resolveKeywords(text, 10, ac?.signal)
    if (!props.active || (ac && keywordAbort !== ac) || ac?.signal.aborted) return

    const kws = resolved.keywords
    keywords.value = kws
    if (!kws.length) {
      status.value = '全文读完'
      mode.value = 'play'
      panelOpen.value = false
      return
    }

    // Refresh DOM word list after the full scroll so late-page hits are present.
    const body = props.bodyEl
    if (body) crawlWords = collectWords(body)
    catchMarks = findAllKeywordSpans(crawlWords, kws)
    caught.value = kws.map((k) => k.key)
    highlights = catchMarks.map((c) => ({ from: c.index, to: c.endIndex, a: 0.35 }))
    silk = []
    panelOpen.value = true
    mode.value = 'done'
    status.value = '全文读完'
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') return
    silk = []
    status.value = '全文读完'
    mode.value = 'play'
  } finally {
    crawlBusy.value = false
    finalizing = false
  }
}

function onPointerMove(e: PointerEvent) {
  if (!props.active || !spider) return
  if (mode.value !== 'play' && mode.value !== 'done') return
  const pos = toWorld(e.clientX, e.clientY)
  spider.goal = pos
}

function onPointerDown(e: PointerEvent) {
  if (!props.active || !spider) return
  if (mode.value !== 'play' && mode.value !== 'done') return
  const t = e.target as HTMLElement | null
  if (t?.closest?.('button, a, input, textarea, select, [role="button"], .ant-modal-root, .spider-result')) {
    return
  }
  spider.jumpTo(toWorld(e.clientX, e.clientY))
}

function updateCrawl(dt: number) {
  if (!spider || !waypoints.length || finalizing) return
  // Full article read complete → then generate the keyword answer.
  if (wpIndex >= waypoints.length) {
    void finalizeAfterRead()
    return
  }
  const wp = waypoints[wpIndex]
  const to = wp.endIndex ?? wp.wordIndex
  const word = liveWord(wp.wordIndex)
  if (!word) {
    advanceWaypoint()
    return
  }

  // Measure → scroll → remeasure, then shift spider by the same screen delta so the
  // target does not "run away" in world space (that chase loop looks like a death spiral).
  const before =
    measureWordSpan(crawlWords, wp.wordIndex, to) || {
      x: word.x,
      y: word.y,
      w: word.w,
      h: word.h,
    }
  const screen = fromWorld(spider.pos.x, spider.pos.y)
  scrollToward(screen.x, screen.y)
  const after =
    measureWordSpan(crawlWords, wp.wordIndex, to) || {
      x: word.x,
      y: word.y,
      w: word.w,
      h: word.h,
    }
  compensateSpiderForScreenDelta(after.x - before.x, after.y - before.y)

  const goal = toWorld(after.x, after.y)
  spider.goal = goal
  pushSilk()

  const dist = Math.hypot(goal.x - spider.pos.x, goal.y - spider.pos.y)
  if (dist < 11) {
    advanceWaypoint()
    return
  }

  wpStuck += dt
  if (wpStuck > 2.8) {
    // Unreachable / oscillating target — skip rather than spin forever.
    advanceWaypoint()
  }
}

function drawOverlay(ctx: CanvasRenderingContext2D) {
  // silk in world space is drawn after transform; highlights in live screen space first
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, W, H)

  for (const h of highlights) {
    h.a = Math.min(0.45, h.a + 0.04)
    const box = measureWordSpan(crawlWords, h.from, h.to)
    if (!box) continue
    ctx.fillStyle = props.dark ? `rgba(244, 180, 0, ${h.a})` : `rgba(244, 180, 0, ${h.a + 0.1})`
    ctx.fillRect(box.x - box.w / 2 - 4, box.y - box.h / 2 - 2, box.w + 8, box.h + 4)
  }

  ctx.setTransform(dpr * zoom, 0, 0, dpr * zoom, (dpr * W) / 2, (dpr * H) / 2)
  if (silk.length > 1) {
    ctx.beginPath()
    ctx.strokeStyle = props.dark ? 'rgba(63,156,240,0.45)' : 'rgba(9,105,218,0.35)'
    ctx.lineWidth = 1.1 / zoom
    ctx.moveTo(silk[0].x, silk[0].y)
    for (let i = 1; i < silk.length; i++) ctx.lineTo(silk[i].x, silk[i].y)
    ctx.stroke()
  }
  if (spider) {
    drawSpider(ctx, spider, {
      ...DEFAULT_DRAW,
      px: zoom * dpr,
      shadow: props.dark ? 0.7 : 0.28,
    })
  }
}

function frame(now: number) {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx || !props.active) {
    raf = 0
    return
  }
  const dt = Math.min(0.05, ((now - last) || 16) / 1000)
  last = now
  if (mode.value === 'crawl') updateCrawl(dt)
  spider?.update(dt)
  drawOverlay(ctx)
  raf = requestAnimationFrame(frame)
}

function startLoop() {
  resize()
  last = performance.now()
  if (!raf) raf = requestAnimationFrame(frame)
}

function stopAll() {
  abortKeywordResolve()
  if (raf) cancelAnimationFrame(raf)
  raf = 0
  spider = null
  crawlBusy.value = false
  mode.value = 'idle'
  waypoints = []
  wpIndex = 0
  wpStuck = 0
  finalizing = false
  crawlWords = []
  silk = []
  highlights = []
  panelOpen.value = false
  status.value = ''
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (canvas && ctx) {
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
  }
}

watch(
  () => props.active,
  (on) => {
    if (on) {
      startLoop()
      beginFollow()
    } else stopAll()
  },
)

watch(
  () => [props.text, props.bodyEl] as const,
  () => {
    // Switching articles via sidebar: keep following mouse; do not jump/reset pose.
    if (props.active) resumeFollowWithoutReset()
  },
)

watch(
  () => props.crawlRequestId ?? 0,
  (id, prev) => {
    if (id > 0 && id !== prev && props.active) void beginCrawl()
  },
)

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('pointerdown', onPointerDown, { passive: true })
  if (props.active) {
    startLoop()
    beginFollow()
  }
})

onBeforeUnmount(() => {
  stopAll()
  window.removeEventListener('resize', resize)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerdown', onPointerDown)
})
</script>

<template>
  <canvas
    ref="canvasRef"
    class="spider-overlay"
    :class="{ active }"
    aria-hidden="true"
  />
  <div v-if="active && status" class="spider-status" role="status">{{ status }}</div>
  <aside v-if="active && panelOpen" class="spider-result" aria-label="关键词抓取结果">
    <header>
      <strong>关键词 · {{ caught.length }}/{{ progress.total }}</strong>
      <button type="button" class="spider-result-close" aria-label="关闭" @click="panelOpen = false">
        ×
      </button>
    </header>
    <ol>
      <li v-for="(kw, i) in keywords" :key="kw.key" :class="{ caught: caught.includes(kw.key) }">
        <span class="idx">{{ i + 1 }}</span>
        <span class="phrase">{{ kw.phrase }}</span>
        <span class="meta">×{{ kw.count }}</span>
      </li>
    </ol>
    <button
      type="button"
      class="spider-confirm"
      :disabled="!keywords.length"
      @click="confirmKeywords"
    >
      确认
    </button>
  </aside>
</template>

<style scoped>
.spider-overlay {
  position: fixed;
  inset: 0;
  z-index: 40;
  pointer-events: none;
  display: none;
}
.spider-overlay.active {
  display: block;
}
.spider-status {
  position: fixed;
  left: 50%;
  bottom: 18px;
  transform: translateX(-50%);
  z-index: 45;
  pointer-events: none;
  max-width: min(520px, calc(100vw - 32px));
  padding: 8px 14px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--ant-color-bg-elevated, #1f1f1f) 92%, transparent);
  border: 1px solid color-mix(in srgb, var(--ant-color-border, #424242) 80%, transparent);
  color: var(--ant-color-text, #e8e8e8);
  font: 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
}
.spider-result {
  position: fixed;
  right: 18px;
  bottom: 56px;
  z-index: 46;
  width: min(300px, calc(100vw - 28px));
  max-height: min(420px, calc(100vh - 100px));
  overflow: auto;
  border-radius: 12px;
  background: var(--ant-color-bg-elevated, #1f1f1f);
  border: 1px solid var(--ant-color-border, #424242);
  color: var(--ant-color-text, #e8e8e8);
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.25);
  padding: 12px 12px 10px;
}
.spider-result header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  font: 600 13px/1.3 ui-sans-serif, system-ui, sans-serif;
}
.spider-result-close {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  opacity: 0.7;
}
.spider-result-close:hover {
  opacity: 1;
}
.spider-result ol {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.spider-result li {
  display: grid;
  grid-template-columns: 22px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 6px 8px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--ant-color-fill-secondary, #ffffff) 6%, transparent);
  font: 12px/1.35 ui-sans-serif, system-ui, sans-serif;
  opacity: 0.55;
}
.spider-result li.caught {
  opacity: 1;
  background: color-mix(in srgb, #f4b400 18%, transparent);
}
.spider-result .idx {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font: 600 11px/1 ui-monospace, Menlo, Consolas, monospace;
  background: color-mix(in srgb, #3f9cf0 25%, transparent);
  color: #3f9cf0;
}
.spider-result .meta {
  color: var(--ant-color-text-secondary, #8b949e);
  font: 11px ui-monospace, Menlo, Consolas, monospace;
}
.spider-confirm {
  margin-top: 12px;
  width: 100%;
  height: 34px;
  border: 0;
  border-radius: 8px;
  cursor: pointer;
  font: 600 13px/1 ui-sans-serif, system-ui, sans-serif;
  color: #0d1117;
  background: #f4b400;
}
.spider-confirm:hover:not(:disabled) {
  filter: brightness(1.06);
}
.spider-confirm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
</style>
