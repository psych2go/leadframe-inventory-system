<template>
  <div class="camera-page">
    <van-nav-bar title="拍照入库" left-arrow @click-left="$router.back()" />

    <div class="upload-area">
      <div class="upload-cards">
        <div class="upload-card camera-card" @click="handleCapture('camera')">
          <div class="upload-icon-wrap">
            <van-icon name="photograph" size="28" />
          </div>
          <div>
            <div class="upload-text">拍照</div>
            <div class="upload-hint">实时取景</div>
          </div>
        </div>
        <div class="upload-card album-card" @click="handleCapture('album')">
          <div class="upload-icon-wrap">
            <van-icon name="photo-o" size="28" />
          </div>
          <div>
            <div class="upload-text">选择图片</div>
            <div class="upload-hint">本地图片</div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading">
      <van-loading size="24px" vertical>正在识别中...</van-loading>
    </div>

    <div v-if="ocrResult && !loading" class="result">
      <van-cell-group title="OCR 识别结果（可修改）">
        <van-field v-model="form.package_type" label="封装形式" placeholder="如 SOP、QFP、DIP" required />
        <van-field v-model="form.spec" label="规格" placeholder="请输入规格" required />
        <van-field
          v-model="form.plating_zone"
          is-link
          readonly
          label="镀银区域"
          placeholder="请选择"
          @click="showPlatingPicker = true"
        />
        <van-field
          v-model="form.surface_treatment"
          is-link
          readonly
          label="表面粗化处理"
          placeholder="请选择"
          @click="showSurfacePicker = true"
        />
        <van-field v-model="ocrSpec" label="厂家规格" readonly placeholder="OCR识别" />
        <van-field v-model="form.batch_no" label="批号" placeholder="批号" required />
        <van-field v-model="form.quantity" label="数量(K)" placeholder="数量" required />
        <van-field v-model="form.manufacturer" label="生产厂家" placeholder="厂家名称" required />
        <van-field v-model="form.note" label="备注" placeholder="备注" />
        <van-field v-model="form.production_date" label="生产日期" placeholder="YYYY-MM-DD" />
        <van-field v-model="form.expiry_date" label="有效日期" placeholder="YYYY-MM-DD" />
      </van-cell-group>

      <van-popup v-model:show="showPlatingPicker" round position="bottom">
        <van-picker
          :columns="platingOptions"
          @confirm="onPlatingConfirm"
          @cancel="showPlatingPicker = false"
        />
      </van-popup>
      <van-popup v-model:show="showSurfacePicker" round position="bottom">
        <van-picker
          :columns="surfaceOptions"
          @confirm="onSurfaceConfirm"
          @cancel="showSurfacePicker = false"
        />
      </van-popup>

      <div class="submit-bar">
        <van-button type="primary" block size="large" @click="submitStockIn" :loading="submitting">
          确认入库
        </van-button>
      </div>

      <div class="raw-text" v-if="ocrResult.raw_text">
        <van-cell-group title="原始识别文字">
          <div class="raw-text-line" v-for="(line, i) in ocrResult.raw_text.split('\n').filter(l => l.trim())" :key="i">
            <span class="line-text">{{ line }}</span>
            <van-button size="mini" plain type="primary" @click="copyValue(line)">
              复制
            </van-button>
          </div>
        </van-cell-group>
      </div>
    </div>

  </div>

  <Viewfinder
    :visible="showViewfinder"
    @capture="onViewfinderCapture"
    @cancel="onViewfinderCancel"
    @error="onViewfinderError"
  />
  <CropModal
    :visible="showCrop"
    :file="cropFile"
    @confirm="onCropConfirm"
    @cancel="onCropCancel"
  />
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { ocrRecognize, stockIn } from '../api'
import { getRawPhoto, isWebRTCSupported } from '../utils/wxsdk'
import Viewfinder from '../components/Viewfinder.vue'
import CropModal from '../components/CropModal.vue'
import { platingOptions, surfaceOptions } from '../composables/useInventoryEnums'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const ocrResult = ref(null)
const imagePath = ref('')
const ocrSpec = ref('')
const showPlatingPicker = ref(false)
const showSurfacePicker = ref(false)

// 取景框 + 裁剪弹窗状态
const showViewfinder = ref(false)
const showCrop = ref(false)
const cropFile = ref(null)

const form = reactive({
  package_type: '',
  spec: '',
  plating_zone: '',
  surface_treatment: '',
  batch_no: '',
  quantity: '',
  manufacturer: '',
  note: '',
  production_date: '',
  expiry_date: '',
})

function onPlatingConfirm({ selectedValues }) {
  form.plating_zone = selectedValues[0] || ''
  showPlatingPicker.value = false
}
function onSurfaceConfirm({ selectedValues }) {
  form.surface_treatment = selectedValues[0] || ''
  showSurfacePicker.value = false
}

async function handleCapture(source = 'camera') {
  if (source === 'camera' && isWebRTCSupported()) {
    // 方案 B：实时取景框（WebRTC）
    showViewfinder.value = true
  } else {
    // 方案 A（降级）：拍照/选图后裁剪
    try {
      const file = await getRawPhoto(source)
      cropFile.value = file
      showCrop.value = true
    } catch (e) {
      if (e.message !== '未选择图片') {
        showToast({ message: e.message === '未选择图片' ? '' : '拍照失败: ' + e.message, position: 'bottom' })
      }
    }
  }
}

async function onViewfinderCapture(file) {
  showViewfinder.value = false
  await onFileRead({ file })
}

async function onViewfinderError(msg) {
  showViewfinder.value = false
  showToast({ message: msg + '，使用系统相机', position: 'bottom' })
  handleCapture('camera')
}

async function onViewfinderCancel() {
  showViewfinder.value = false
}

async function onCropConfirm(file) {
  showCrop.value = false
  cropFile.value = null
  // CropModal 已输出 1000px/0.85 的 JPEG，直接送 OCR
  await onFileRead({ file })
}

function onCropCancel() {
  showCrop.value = false
  cropFile.value = null
}

async function onFileRead(fileInfo) {
  loading.value = true
  ocrResult.value = null
  try {
    const result = await ocrRecognize(fileInfo.file)
    if (result.error) {
      showToast({ message: result.error, position: 'bottom' })
      return
    }
    ocrResult.value = result
    imagePath.value = result.image_path || ''
    if (result.parsed) {
      ocrSpec.value = result.parsed.spec || ''
      form.spec = result.parsed.spec || ''
      form.batch_no = result.parsed.batch_no || ''
      form.quantity = result.parsed.quantity || ''
      form.manufacturer = result.parsed.manufacturer || ''
      form.note = result.parsed.note || ''
      form.production_date = result.parsed.production_date || ''
      form.expiry_date = result.parsed.expiry_date || ''
    }
  } catch (e) {
    showToast({ message: '识别失败: ' + e.message, position: 'bottom' })
  } finally {
    loading.value = false
  }
}

function copyValue(line) {
  const idx = Math.max(line.indexOf(':'), line.indexOf('：'))
  const value = idx >= 0 ? line.substring(idx + 1).trim() : line.trim()
  navigator.clipboard.writeText(value)
  showToast({ message: `已复制: ${value}`, position: 'bottom', duration: 1000 })
}

async function submitStockIn() {
  if (!form.package_type.trim()) {
    showToast('请填写封装形式')
    return
  }
  if (!form.spec.trim()) {
    showToast('请填写厂家规格')
    return
  }
  if (!form.quantity) {
    showToast('请填写有效数量')
    return
  }
  submitting.value = true
  try {
    await stockIn({
      package_type: form.package_type.trim(),
      spec: form.spec.trim(),
      plating_zone: form.plating_zone.trim(),
      surface_treatment: form.surface_treatment.trim(),
      manufacturer: form.manufacturer.trim(),
      batch_no: form.batch_no.trim(),
      quantity: form.quantity.trim(),
      note: form.note.trim(),
      production_date: form.production_date.trim(),
      expiry_date: form.expiry_date.trim(),
      image_path: imagePath.value || null,
    })
    showSuccessToast('入库成功')
    router.push('/')
  } catch (e) {
    showToast({ message: '入库失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.camera-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--lf-bg);
}
.upload-area { padding: 20px 16px 8px; }
.upload-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.upload-card {
  display: flex;
  align-items: center;
  min-height: 88px;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--lf-border);
  border-radius: 8px;
  background: white;
  color: var(--lf-text);
  cursor: pointer;
  transition: border-color 0.16s, background-color 0.16s, transform 0.16s;
}
.upload-card:active { transform: translateY(1px); }
.camera-card {
  border-color: #a9e8c8;
  background: var(--lf-in-soft);
}
.album-card {
  border-color: #a9dcf4;
  background: var(--lf-primary-soft);
}
.upload-icon-wrap {
  width: 44px;
  height: 44px;
  flex: 0 0 44px;
  border-radius: 6px;
  background: var(--lf-primary);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
}
.album-card .upload-icon-wrap { background: var(--lf-primary); }
.upload-text {
  font-size: 14px;
  font-weight: 700;
}
.upload-hint {
  margin-top: 3px;
  color: var(--lf-text-muted);
  font-size: 11px;
  font-weight: 500;
}
.loading {
  margin: 16px;
  padding: 40px 16px;
  border: 1px solid var(--lf-border);
  border-radius: 8px;
  background: white;
  text-align: center;
}
.result { padding-bottom: 24px; }
.raw-text { margin: 4px 0 16px; }
.raw-text-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 8px 14px;
  gap: 8px;
  font-family: var(--lf-data-font);
  font-size: 12px;
  line-height: 1.5;
}
.raw-text-line:not(:last-child) {
  border-bottom: 1px solid var(--lf-border);
}
.line-text {
  flex: 1;
  word-break: break-all;
}
.submit-bar { padding: 12px; }

.camera-page :deep(.van-cell-group) {
  margin: 12px;
}
.camera-page :deep(.van-cell) {
  border-radius: 0;
}
.camera-page :deep(.van-field__control),
.camera-page :deep(.van-cell__value) {
  font-family: var(--lf-data-font);
}
.camera-page :deep(.van-button--primary) {
  background: var(--lf-in);
  border-color: var(--lf-in);
}
</style>
