<template>
  <div class="camera-page">
    <van-nav-bar title="拍照入库" left-arrow @click-left="$router.back()" />

    <div class="upload-area">
      <div class="upload-card" @click="handleCapture">
        <div class="upload-icon-wrap">
          <van-icon name="photograph" size="40" color="#fff" />
        </div>
        <div class="upload-text">拍照 / 选择图片</div>
        <div class="upload-hint">支持 jpg、png 格式</div>
      </div>
    </div>

    <div v-if="loading" class="loading">
      <van-loading size="24px" vertical>正在识别中...</van-loading>
    </div>

    <div v-if="ocrResult && !loading" class="result">
      <van-cell-group title="OCR 识别结果（可修改）">
        <van-field
          v-model="form.material_code"
          label="物料编码"
          placeholder="根据厂家规格手动填写"
          required
          :class="{ 'auto-filled': materialCodeAutoFilled }"
          @focus="materialCodeAutoFilled = false"
        />
        <van-cell v-if="materialCodeHint" :value="materialCodeHint" size="small" />
        <van-field v-model="form.spec" label="厂家规格" placeholder="厂家规格" required />
        <van-field v-model="form.batch_no" label="批号" placeholder="批号" required />
        <van-field v-model="form.quantity" label="数量(K)" placeholder="数量" required />
        <van-field v-model="form.manufacturer" label="生产厂家" placeholder="厂家名称" required />
        <van-field v-model="form.note" label="备注" placeholder="备注" />
        <van-field v-model="form.production_date" label="生产日期" placeholder="YYYY-MM-DD" />
        <van-field v-model="form.expiry_date" label="有效日期" placeholder="YYYY-MM-DD" />
      </van-cell-group>

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

    <div class="material-code-hint">
      <div class="hint-inner">
        <div class="hint-title">物料编码规则（试行）</div>
        <div class="hint-line"><b>通用：</b>封装形式-载体尺寸-单环镀/双环镀-CRC/SRC/ERC 或 封装形式-XX型号专用;</div>
        <div class="hint-line"><b>QFN/DFN：</b>封装形式-塑封体尺寸-引脚间距e(基岛尺寸)-单环镀/双环镀-CRC/SRC/ERC；</div>
        <div class="hint-note">必须含有的信息：封装形式和载体尺寸或塑封体尺寸或XX型号；统一用*号连接。</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { ocrRecognize, stockIn, getMaterialCodeSuggest } from '../api'
import { getPhoto } from '../utils/wxsdk'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const ocrResult = ref(null)
const imagePath = ref('')

const form = reactive({
  material_code: '',
  spec: '',
  batch_no: '',
  quantity: '',
  manufacturer: '',
  note: '',
  production_date: '',
  expiry_date: '',
})
const materialCodeAutoFilled = ref(false)
const materialCodeHint = ref('')

async function handleCapture() {
  try {
    const file = await getPhoto()
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
      form.spec = result.parsed.spec || ''
      form.batch_no = result.parsed.batch_no || ''
      form.quantity = result.parsed.quantity || ''
      form.manufacturer = result.parsed.manufacturer || ''
      form.note = result.parsed.note || ''
      form.production_date = result.parsed.production_date || ''
      form.expiry_date = result.parsed.expiry_date || ''
      // 根据厂家规格自动建议物料编码
      if (form.spec) {
        try {
          const res = await getMaterialCodeSuggest(form.spec)
          if (res.suggestions && res.suggestions.length > 0) {
            form.material_code = res.suggestions[0]
            materialCodeAutoFilled.value = true
            const count = res.suggestions.length
            materialCodeHint.value = `已自动填入物料编码（共 ${count} 条历史记录），点击输入框可修改`
          } else {
            materialCodeHint.value = '无历史记录，请填写物料编码'
          }
        } catch (e) {
          // 静默处理
        }
      }
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
  if (!form.material_code.trim()) {
    showToast('请填写物料编码')
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
      material_code: form.material_code.trim(),
      spec: form.spec.trim(),
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
.upload-card {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 28px 48px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 16px;
  color: #fff;
  cursor: pointer;
  transition: transform 0.2s, box-shadow 0.2s;
  box-shadow: 0 4px 16px rgba(102, 126, 234, 0.35);
}
.upload-card:active {
  transform: scale(0.97);
}
.upload-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
}
.upload-text {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1px;
}
.upload-hint {
  font-size: 12px;
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
.auto-filled :deep(.van-field__control) {
  color: #07c160;
}

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
