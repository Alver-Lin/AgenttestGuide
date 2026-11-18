<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Spider } from './spider/spider'
import { drawSpider, DEFAULT_DRAW } from './spider/draw'
import { skinById } from './spider/skins'

const props = defineProps<{
  active: boolean
  dark?: boolean
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const dpr = Math.min(2, window.devicePixelRatio || 1)
const zoom = 1.35

let spider: Spider | null = null
let mouse: { x: number; y: number } | null = null
let raf = 0
let last = 0
let W = 0
let H = 0

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

function onPointerMove(e: PointerEvent) {
  if (!props.active || !spider) return
  mouse = toWorld(e.clientX, e.clientY)
  spider.goal = mouse
}

function onPointerDown(e: PointerEvent) {
  if (!props.active || !spider) return
  // ignore clicks on interactive controls
  const t = e.target as HTMLElement | null
  if (t?.closest?.('button, a, input, textarea, select, [role="button"], .ant-modal-root, .ant-dropdown')) {
    return
  }
  spider.jumpTo(toWorld(e.clientX, e.clientY))
}

function frame(now: number) {
  const canvas = canvasRef.value
  const ctx = canvas?.getContext('2d')
  if (!canvas || !ctx || !spider || !props.active) {
    raf = 0
    return
  }
  const dt = Math.min(0.05, ((now - last) || 16) / 1000)
  last = now
  if (mouse) spider.goal = mouse
  spider.update(dt)

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, W, H)
  ctx.setTransform(dpr * zoom, 0, 0, dpr * zoom, (dpr * W) / 2, (dpr * H) / 2)
  drawSpider(ctx, spider, {
    ...DEFAULT_DRAW,
    px: zoom * dpr,
    shadow: props.dark ? 0.7 : 0.28,
  })

  raf = requestAnimationFrame(frame)
}

function start() {
  resize()
  if (!spider) {
    const startPos = mouse ?? { x: 40, y: 20 }
    spider = new Spider(startPos, skinById('blueprint'))
    spider.goal = startPos
  }
  last = performance.now()
  if (!raf) raf = requestAnimationFrame(frame)
}

function stop() {
  if (raf) cancelAnimationFrame(raf)
  raf = 0
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
    if (on) start()
    else stop()
  },
)

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
  window.addEventListener('pointermove', onPointerMove, { passive: true })
  window.addEventListener('pointerdown', onPointerDown, { passive: true })
  if (props.active) start()
})

onBeforeUnmount(() => {
  stop()
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
</style>
