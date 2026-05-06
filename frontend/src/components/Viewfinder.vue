<template>
  <div class="viewfinder-overlay" v-if="visible" :style="frameStyle" @click.self="cancel">
    <video ref="videoEl" autoplay playsinline muted />

    <!-- 取景框暗色遮罩，中间镂空区域透明露出视频 -->
    <div class="mask">
      <div class="mask-section top"></div>
      <div class="mask-section middle">
        <div class="mask-section left"></div>
        <div class="frame" ref="frameEl">
          <div class="corner tl"></div>
          <div class="corner tr"></div>
          <div class="corner bl"></div>
          <div class="corner br"></div>
        </div>
        <div class="mask-section right"></div>
      </div>
      <div class="mask-section bottom"></div>
    </div>

    <div class="hint">请将标签对准框内</div>

    <!-- 底部控制区 -->
    <div class="controls">
      <button class="btn-capture" @click="capture">
        <span class="btn-capture-ring"></span>
      </button>
    </div>

    <button class="btn-close" @click="cancel" aria-label="取消">&times;</button>
  </div>
</template>

<script setup>
import { ref, computed, watch, onBeforeUnmount } from 'vue'

const props = defineProps({
  visible: Boolean,
  aspectRatio: { type: Number, default: 3 / 4 },
})

const emit = defineEmits(['capture', 'cancel', 'error'])

const videoEl = ref(null)
const frameEl = ref(null)
let mediaStream = null

const frameWidth = typeof window !== 'undefined'
  ? Math.min(window.innerWidth * 0.85, 480)
  : 400
const frameHeight = frameWidth / props.aspectRatio
const frameStyle = computed(() => ({
  '--frame-w': `${frameWidth}px`,
  '--frame-h': `${frameHeight}px`,
}))

function stopStream() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((t) => t.stop())
    mediaStream = null
  }
}

async function startCamera() {
  try {
    const constraints = {
      video: {
        facingMode: 'environment',
        width: { ideal: 1920 },
        height: { ideal: 1080 },
      },
      audio: false,
    }
    const stream = await navigator.mediaDevices.getUserMedia(constraints)
    mediaStream = stream
    if (videoEl.value) {
      videoEl.value.srcObject = stream
    }
  } catch (e) {
    emit('error', e instanceof DOMException && e.name === 'NotAllowedError' ? '摄像头权限被拒绝' : '无法启动摄像头: ' + e.message)
  }
}

watch(
  () => props.visible,
  (v) => {
    if (v) {
      startCamera()
    } else {
      stopStream()
    }
  },
)

onBeforeUnmount(() => stopStream())

function capture() {
  const video = videoEl.value
  const frame = frameEl.value
  if (!video || !frame || video.readyState < 2) return

  const vr = video.getBoundingClientRect()
  const fr = frame.getBoundingClientRect()

  const vw = video.videoWidth
  const vh = video.videoHeight

  // 处理 object-fit: cover 的可见区域偏移
  const videoAspect = vw / vh
  const containerAspect = vr.width / vr.height

  let sx, sy, sw, sh
  if (videoAspect > containerAspect) {
    const visibleW = vh * containerAspect
    sx = (vw - visibleW) / 2
    sy = 0
    sw = visibleW
    sh = vh
  } else {
    const visibleH = vw / containerAspect
    sx = 0
    sy = (vh - visibleH) / 2
    sw = vw
    sh = visibleH
  }

  // 将取景框坐标映射到视频像素坐标
  const cropX = sx + ((fr.left - vr.left) / vr.width) * sw
  const cropY = sy + ((fr.top - vr.top) / vr.height) * sh
  const cropW = (fr.width / vr.width) * sw
  const cropH = (fr.height / vr.height) * sh

  // 裁切 ROI 后降分辨率到 max 1000px
  const MAX_OUTPUT_W = 1000
  let outW = Math.round(cropW)
  let outH = Math.round(cropH)
  if (outW > MAX_OUTPUT_W) {
    const scale = MAX_OUTPUT_W / outW
    outW = MAX_OUTPUT_W
    outH = Math.round(outH * scale)
  }
  const canvas = document.createElement('canvas')
  canvas.width = outW
  canvas.height = outH
  const ctx = canvas.getContext('2d')
  ctx.drawImage(video, cropX, cropY, cropW, cropH, 0, 0, canvas.width, canvas.height)

  // 转 File（质量 0.85，标签 ROI 足够）
  canvas.toBlob(
    (blob) => {
      stopStream()
      const file = new File([blob], 'viewfinder.jpg', { type: 'image/jpeg' })
      emit('capture', file)
    },
    'image/jpeg',
    0.85,
  )
}

function cancel() {
  stopStream()
  emit('cancel')
}
</script>

<style scoped>
.viewfinder-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: #000;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 暗色遮罩，中间镂空 */
.mask {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template-rows:
    [top-start] 1fr [top-end mid-start] var(--frame-h) [mid-end bottom-start] 1fr [bottom-end];
  grid-template-columns:
    [left-start] 1fr [left-end mid-start] var(--frame-w) [mid-end right-start] 1fr [right-end];
  pointer-events: none;
}

.mask-section {
  background: rgba(0, 0, 0, 0.6);
}

.mask-section.top {
  grid-row: top-start / top-end;
  grid-column: left-start / right-end;
}

.mask-section.middle {
  grid-row: mid-start / mid-end;
  grid-column: left-start / right-end;
  display: contents;
}

.mask-section.left {
  grid-row: mid-start / mid-end;
  grid-column: left-start / left-end;
}

.mask-section.right {
  grid-row: mid-start / mid-end;
  grid-column: right-start / right-end;
}

.mask-section.bottom {
  grid-row: bottom-start / bottom-end;
  grid-column: left-start / right-end;
}

/* 取景框 - 透明区域 */
.frame {
  grid-row: mid-start / mid-end;
  grid-column: mid-start / mid-end;
  width: var(--frame-w);
  height: var(--frame-h);
  position: relative;
  pointer-events: auto;
}

/* 角落装饰 */
.corner {
  position: absolute;
  width: 24px;
  height: 24px;
  border-color: #fff;
  border-style: solid;
}
.corner.tl { top: -2px; left: -2px; border-width: 3px 0 0 3px; border-radius: 3px 0 0 0; }
.corner.tr { top: -2px; right: -2px; border-width: 3px 3px 0 0; border-radius: 0 3px 0 0; }
.corner.bl { bottom: -2px; left: -2px; border-width: 0 0 3px 3px; border-radius: 0 0 0 3px; }
.corner.br { bottom: -2px; right: -2px; border-width: 0 3px 3px 0; border-radius: 0 0 3px 0; }

.hint {
  position: absolute;
  bottom: 120px;
  color: rgba(255, 255, 255, 0.85);
  font-size: 15px;
  letter-spacing: 1px;
  z-index: 2;
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.6);
}

/* 底部控制 */
.controls {
  position: absolute;
  bottom: 40px;
  z-index: 2;
  pointer-events: auto;
}

.btn-capture {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 255, 255, 0.2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.btn-capture-ring {
  display: block;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: #fff;
  transition: opacity 0.15s;
}

.btn-capture:active .btn-capture-ring {
  opacity: 0.8;
}

.btn-close {
  position: absolute;
  top: 16px;
  right: 16px;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: none;
  background: rgba(0, 0, 0, 0.4);
  color: #fff;
  font-size: 28px;
  line-height: 40px;
  text-align: center;
  cursor: pointer;
  z-index: 2;
  padding: 0;
}
</style>
