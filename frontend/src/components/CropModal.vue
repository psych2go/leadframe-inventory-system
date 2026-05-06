<template>
  <van-popup :show="visible" position="bottom" :style="{ height: '100vh' }" :closeable="false" @click-overlay="cancel">
    <div class="crop-modal">
      <!-- 全屏裁剪区域 -->
      <div class="crop-body" ref="containerEl">
        <img ref="imgEl" :src="imageUrl" alt="裁剪" style="display:none" />
      </div>
      <!-- 顶部操作栏（叠加在图片上） -->
      <div class="crop-header">
        <span class="crop-cancel" @click="cancel">取消</span>
        <span class="crop-title">裁剪标签区域</span>
        <span class="crop-confirm" @click="confirm">确认</span>
      </div>
      <div class="crop-hint">调整选框，保留标签区域，减少背景干扰</div>
    </div>
  </van-popup>
</template>

<script setup>
import { ref, watch, nextTick, onBeforeUnmount } from 'vue'
import Cropper from 'cropperjs'

const props = defineProps({
  visible: Boolean,
  file: { type: File, default: null },
  aspectRatio: { type: Number, default: NaN },
})

const emit = defineEmits(['confirm', 'cancel'])

const containerEl = ref(null)
const imgEl = ref(null)
const imageUrl = ref('')
let cropper = null

watch(
  () => props.visible,
  async (v) => {
    if (v && props.file) {
      destroyCropper()
      imageUrl.value = URL.createObjectURL(props.file)
      await nextTick()
      initCropper()
    }
    if (!v) {
      destroyCropper()
      revokeUrl()
    }
  },
)

function initCropper() {
  if (!imgEl.value || !containerEl.value) return
  const options = {
    template: [
      '<cropper-canvas background>',
      '  <cropper-image rotatable scalable skewable translatable></cropper-image>',
      '  <cropper-shade hidden></cropper-shade>',
      '  <cropper-handle action="select" plain></cropper-handle>',
      '  <cropper-selection initial-coverage="0.8" movable resizable>',
      '    <cropper-grid role="grid" bordered covered></cropper-grid>',
      '    <cropper-crosshair centered></cropper-crosshair>',
      '    <cropper-handle action="move" theme-color="rgba(255, 255, 255, 0.35)"></cropper-handle>',
      '    <cropper-handle action="n-resize"></cropper-handle>',
      '    <cropper-handle action="e-resize"></cropper-handle>',
      '    <cropper-handle action="s-resize"></cropper-handle>',
      '    <cropper-handle action="w-resize"></cropper-handle>',
      '    <cropper-handle action="ne-resize"></cropper-handle>',
      '    <cropper-handle action="nw-resize"></cropper-handle>',
      '    <cropper-handle action="se-resize"></cropper-handle>',
      '    <cropper-handle action="sw-resize"></cropper-handle>',
      '  </cropper-selection>',
      '</cropper-canvas>',
    ].join('\n'),
    container: containerEl.value,
  }
  if (!isNaN(props.aspectRatio)) {
    options.aspectRatio = props.aspectRatio
  }
  cropper = new Cropper(imgEl.value, options)
}

function destroyCropper() {
  if (cropper) {
    cropper.destroy()
    cropper = null
  }
}

function revokeUrl() {
  if (imageUrl.value) {
    URL.revokeObjectURL(imageUrl.value)
    imageUrl.value = ''
  }
}

async function confirm() {
  if (!cropper) {
    emit('cancel')
    return
  }
  const cropperCanvas = cropper.getCropperCanvas()
  if (!cropperCanvas) {
    emit('cancel')
    return
  }
  try {
    const canvas = await cropperCanvas.$toCanvas({
      maxWidth: 1000,
      maxHeight: 1000,
      imageSmoothingQuality: 'high',
    })
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', 0.85))
    if (blob) {
      const cropped = new File([blob], props.file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' })
      emit('confirm', cropped)
    } else {
      emit('cancel')
    }
  } catch (e) {
    console.warn('[CropModal] 裁剪失败:', e)
    emit('cancel')
  }
}

function cancel() {
  emit('cancel')
}

onBeforeUnmount(() => {
  destroyCropper()
  revokeUrl()
})
</script>

<style scoped>
.crop-modal {
  position: relative;
  height: 100vh;
  background: #000;
  overflow: hidden;
}

/* 全屏裁剪容器 */
.crop-body {
  position: absolute;
  inset: 0;
  display: flex;
  background: #000;
}
/* cropper-canvas 是 JS 动态注入的 Shadow DOM 元素，
   通过 flex stretch 让它自行拉伸填满容器 */
.crop-body :deep(cropper-canvas) {
  flex: 1;
}

/* 顶栏叠加层 */
.crop-header {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  padding-top: calc(14px + env(safe-area-inset-top, 0px));
  background: linear-gradient(to bottom, rgba(0,0,0,0.6), transparent);
  font-size: 16px;
  color: #fff;
}

.crop-cancel {
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 4px;
  background: rgba(255,255,255,0.15);
}

.crop-title {
  font-weight: 600;
  text-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.crop-confirm {
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  padding: 4px 12px;
  border-radius: 4px;
  background: #1989fa;
}

/* 底部提示叠加 */
.crop-hint {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 10;
  text-align: center;
  padding: 10px;
  padding-bottom: calc(10px + env(safe-area-inset-bottom, 0px));
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
  background: linear-gradient(to top, rgba(0,0,0,0.5), transparent);
}
</style>
