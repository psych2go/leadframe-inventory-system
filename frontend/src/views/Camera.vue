<template>
  <div class="camera-page">
    <van-nav-bar title="拍照入库" left-arrow @click-left="$router.back()" />

    <div class="upload-area">
      <div class="upload-cards">
        <div class="upload-card camera-card" @click="handleCapture('camera')">
          <div class="upload-icon-wrap">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
              <circle cx="12" cy="13" r="4"/>
            </svg>
          </div>
          <div class="upload-text">拍照</div>
          <div class="upload-hint">打开相机拍摄</div>
        </div>
        <div class="upload-card album-card" @click="handleCapture('album')">
          <div class="upload-icon-wrap">
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <circle cx="8.5" cy="8.5" r="1.5"/>
              <polyline points="21 15 16 10 5 21"/>
            </svg>
          </div>
          <div class="upload-text">选择图片</div>
          <div class="upload-hint">从相册上传</div>
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

    <div class="material-code-hint" v-if="!ocrResult">
      <div class="hint-inner">
        <div class="hint-title">物料编码命名规则（试行）</div>
        <div class="hint-line"><b>通用：</b>封装形式-载体尺寸-单环镀/双环镀-CRC/SRC/ERC 或 封装形式-XX型号专用;</div>
        <div class="hint-line"><b>QFN/DFN：</b>封装形式-塑封体尺寸-引脚间距e(基岛尺寸)-单环镀/双环镀-CRC/SRC/ERC；</div>
        <div class="hint-note">必须含有的信息：封装形式和载体尺寸或塑封体尺寸或XX型号；尺寸之间用*号连接，比如80*80。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { ocrRecognize, stockIn } from '../api'
import { getPhoto } from '../utils/wxsdk'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const ocrResult = ref(null)
const imagePath = ref('')
const ocrSpec = ref('')
const showPlatingPicker = ref(false)
const showSurfacePicker = ref(false)

const platingOptions = [{ text: '无', value: '' }, { text: '单环镀', value: '单环镀' }, { text: '双环镀', value: '双环镀' }]
const surfaceOptions = [{ text: '无', value: '' }, { text: 'CRC', value: 'CRC' }, { text: 'SRC', value: 'SRC' }, { text: 'ERC', value: 'ERC' }]

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
  try {
    const file = await getPhoto(source)
    await onFileRead({ file })
  } catch (e) {
    if (e.message !== '未选择图片') {
      showToast({ message: '拍照失败: ' + e.message, position: 'bottom' })
    }
  }
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
  background: #f7f8fa;
}
.material-code-hint {
  margin-top: auto;
  padding: 12px 16px 20px;
  text-align: center;
}
.hint-inner {
  display: inline-block;
  text-align: left;
}
.hint-title {
  font-size: 14px;
  font-weight: bold;
  color: #333;
  margin-bottom: 8px;
}
.hint-line {
  font-size: 13px;
  color: #666;
  line-height: 1.8;
}
.hint-note {
  font-size: 12px;
  color: #ff976a;
  margin-top: 6px;
}
.upload-area { padding: 32px 16px; text-align: center; }
.upload-cards {
  display: flex;
  gap: 16px;
  justify-content: center;
}
.upload-card {
  flex: 1;
  max-width: 170px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 16px;
  border-radius: 16px;
  color: #fff;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
}
.upload-card:active {
  transform: scale(0.97);
}
.camera-card {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  box-shadow: 0 4px 16px rgba(102, 126, 234, 0.35);
}
.album-card {
  background: linear-gradient(135deg, #36d1dc 0%, #5b86e5 100%);
  box-shadow: 0 4px 16px rgba(54, 209, 220, 0.35);
}
.upload-icon-wrap {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
}
.upload-text {
  font-size: 15px;
  font-weight: 600;
}
.upload-hint {
  font-size: 11px;
  opacity: 0.8;
}
.loading { padding: 40px; text-align: center; }
.result { margin-top: 16px; }
.raw-text { margin: 16px 0; }
.raw-text-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  gap: 8px;
  font-size: 13px;
  line-height: 1.6;
}
.raw-text-line:not(:last-child) {
  border-bottom: 1px solid #f5f5f5;
}
.line-text {
  flex: 1;
  word-break: break-all;
}
.submit-bar { padding: 16px; }

.camera-page :deep(.van-cell-group) {
  margin: 12px;
  border-radius: 12px;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.camera-page :deep(.van-cell) {
  border-radius: 0;
}
.camera-page :deep(.van-nav-bar) {
  background: white;
}
</style>
