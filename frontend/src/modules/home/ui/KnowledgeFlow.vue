<template>
  <div ref="host" class="knowledge-flow" aria-hidden="true">
    <canvas ref="canvas"></canvas>
  </div>
</template>

<script setup>
import { nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useThemeStore } from '@/shared/model/theme'

const props = defineProps({ engaged: Boolean })
const themeStore = useThemeStore()
const host = ref(null)
const canvas = ref(null)
const pointer = { x: 0, y: 0 }
const target = { x: 0, y: 0 }
let context
let observer
let media
let frame = null
let active = true
let width = 0
let height = 0
let elapsed = 0
let previous = 0
let engagement = 0
let ink = ''
let paper = ''

/** 固定种子使曲线与节点在主题切换和重绘时保持相同构图。 */
function noise(seed) {
  const value = Math.sin(seed * 127.1 + 311.7) * 43758.5453
  return value - Math.floor(value)
}

const strands = Array.from({ length: 88 }, (_, index) => {
  const spread = noise(index + 1) - 0.5
  const loose = index % 5 === 0
  return {
    start: 0.64 + spread * (loose ? 0.9 : 0.38),
    bend: 1.04 + (noise(index + 23) - 0.5) * (loose ? 0.65 : 0.35),
    rise: 0.95 + (noise(index + 46) - 0.5) * (loose ? 0.9 : 0.5),
    end: -0.12 + spread * 0.75,
    phase: noise(index + 9) * Math.PI * 2,
    alpha: loose ? 0.09 : 0.11 + noise(index + 5) * 0.14,
    weight: index % 9 === 0 ? 1 : 0.55
  }
})
const nodes = Array.from({ length: 104 }, (_, index) => ({
  strand: strands[index % strands.length],
  offset: noise(index + 113),
  speed: 0.002 + noise(index + 321) * 0.004,
  radius: index % 8 === 0 ? 2.6 : 0.85 + noise(index + 75) * 1.1,
  outline: index % 11 === 0,
  alpha: 0.3 + noise(index + 15) * 0.4
}))

/** 同一条贝塞尔流线承载细线与移动节点，轻微摆动仅改变背景。 */
function pointOnStrand(strand, position) {
  const t = position
  const inverse = 1 - t
  const bend = 3 * inverse * inverse * t
  const rise = 3 * inverse * t * t
  const spread = Math.sin(t * Math.PI)
  return {
    x:
      width * (inverse ** 3 * -0.12 + bend * 0.18 + rise * 0.82 + t ** 3 * 1.12) +
      pointer.x * 16 * spread,
    y:
      height *
        (inverse ** 3 * strand.start +
          bend * strand.bend +
          rise * strand.rise +
          t ** 3 * strand.end) +
      Math.sin(elapsed * 0.16 + strand.phase + t * 4) * 10 * spread +
      pointer.y * 12 * spread -
      engagement * 18 * spread
  }
}

/** 从当前主题读取中性色，几何和运动不随明暗模式改变。 */
function readPalette() {
  const style = getComputedStyle(host.value)
  ink = style.getPropertyValue('--gray-600').trim()
  paper = style.getPropertyValue('--gray-10').trim()
}

/** 先铺细线，再绘制稀疏连接和节点，保留中央输入区的留白。 */
function draw() {
  if (!context || !width || !height) return
  context.clearRect(0, 0, width, height)
  context.strokeStyle = ink
  const calm = 1 - engagement * 0.3
  for (const strand of strands) {
    context.globalAlpha = strand.alpha * calm
    context.lineWidth = strand.weight
    context.beginPath()
    for (let step = 0; step <= 72; step++) {
      const point = pointOnStrand(strand, step / 72)
      if (step === 0) context.moveTo(point.x, point.y)
      else context.lineTo(point.x, point.y)
    }
    context.stroke()
  }

  const positions = nodes.map((node) =>
    pointOnStrand(node.strand, (node.offset + elapsed * node.speed) % 1)
  )
  context.lineWidth = 0.6
  context.globalAlpha = 0.16 * calm
  for (let index = 0; index < positions.length - 1; index += 2) {
    const from = positions[index]
    const to = positions[index + 1]
    const distance = Math.hypot(from.x - to.x, from.y - to.y)
    if (distance > 22 && distance < width * 0.12) {
      context.beginPath()
      context.moveTo(from.x, from.y)
      context.lineTo(to.x, to.y)
      context.stroke()
    }
  }

  nodes.forEach((node, index) => {
    const point = positions[index]
    // 少量节点沿原有曲线留下细尾迹，输入时随背景收淡。
    if (index % 17 === 0) {
      const progress = (node.offset + elapsed * node.speed) % 1
      let from = pointOnStrand(node.strand, Math.max(0, progress - 0.045))
      context.lineWidth = 1
      for (let step = 1; step <= 12; step++) {
        const to = pointOnStrand(node.strand, Math.max(0, progress - 0.045 * (1 - step / 12)))
        context.globalAlpha = (step / 12) * 0.28 * calm
        context.beginPath()
        context.moveTo(from.x, from.y)
        context.lineTo(to.x, to.y)
        context.stroke()
        from = to
      }
      const breath = (Math.sin(elapsed * 0.35 + node.offset * Math.PI * 2) + 1) / 2
      context.globalAlpha = (0.07 + breath * 0.05) * calm
      context.lineWidth = 0.65
      context.beginPath()
      context.arc(point.x, point.y, 6 + breath * 2, 0, Math.PI * 2)
      context.stroke()
    }
    context.globalAlpha = node.alpha * calm
    context.beginPath()
    context.arc(point.x, point.y, node.outline ? node.radius + 1.6 : node.radius, 0, Math.PI * 2)
    context.fillStyle = node.outline ? paper : ink
    context.fill()
    if (node.outline) {
      context.lineWidth = 1
      context.stroke()
    }
  })
  context.globalAlpha = 1
}

/** 动效按真实帧间隔推进，最多每秒绘制约三十帧。 */
function animate(timestamp) {
  frame = requestAnimationFrame(animate)
  if (timestamp - previous < 32) return
  const delta = Math.min(timestamp - previous, 64) / 1000
  previous = timestamp
  elapsed += delta
  const follow = 1 - Math.exp(-delta * 3)
  pointer.x += (target.x - pointer.x) * follow
  pointer.y += (target.y - pointer.y) * follow
  engagement += (Number(props.engaged) - engagement) * follow
  draw()
}

/** 页面隐藏、失活和系统减少动效时仅保留静态绘制。 */
function syncAnimation() {
  if (frame !== null) cancelAnimationFrame(frame)
  frame = null
  if (media?.matches) engagement = Number(props.engaged)
  draw()
  if (!active || media?.matches || document.hidden || !context) return
  previous = performance.now()
  frame = requestAnimationFrame(animate)
}

/** 画布跟随整个首屏，像素密度限制为二以控制绘制开销。 */
function resize() {
  width = host.value.clientWidth
  height = host.value.clientHeight
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  canvas.value.width = Math.round(width * ratio)
  canvas.value.height = Math.round(height * ratio)
  context.setTransform(ratio, 0, 0, ratio, 0, 0)
  draw()
}

/** 指针只轻微牵动背景，不干扰文字和输入框。 */
function movePointer(event) {
  if (!active || media?.matches) return
  target.x = event.clientX / window.innerWidth - 0.5
  target.y = event.clientY / window.innerHeight - 0.5
}

/** 指针离开窗口后缓慢恢复流线位置。 */
function resetPointer() {
  target.x = 0
  target.y = 0
}

watch(
  () => props.engaged,
  () => {
    if (!media?.matches) return
    engagement = Number(props.engaged)
    draw()
  }
)
watch(
  () => themeStore.isDark,
  async () => {
    await nextTick()
    if (!host.value) return
    readPalette()
    draw()
  }
)
onMounted(() => {
  context = canvas.value.getContext('2d')
  if (!context) return
  readPalette()
  observer = new ResizeObserver(resize)
  observer.observe(host.value)
  media = window.matchMedia('(prefers-reduced-motion: reduce)')
  media.addEventListener('change', syncAnimation)
  document.addEventListener('visibilitychange', syncAnimation)
  window.addEventListener('pointermove', movePointer, { passive: true })
  document.documentElement.addEventListener('pointerleave', resetPointer)
  syncAnimation()
})
onActivated(() => {
  active = true
  syncAnimation()
})
onDeactivated(() => {
  active = false
  syncAnimation()
})
onUnmounted(() => {
  active = false
  syncAnimation()
  observer?.disconnect()
  media?.removeEventListener('change', syncAnimation)
  document.removeEventListener('visibilitychange', syncAnimation)
  window.removeEventListener('pointermove', movePointer)
  document.documentElement.removeEventListener('pointerleave', resetPointer)
})
</script>

<style scoped>
.knowledge-flow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
  mask-image: linear-gradient(transparent, black 15%, black 84%, transparent);
}
.knowledge-flow::after {
  content: '';
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse 36% 29% at 50% 41%, var(--gray-10) 40%, transparent 100%);
}
canvas {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
