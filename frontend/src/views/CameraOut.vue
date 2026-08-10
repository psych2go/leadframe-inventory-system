<template>
  <div class="camera-page">
    <van-nav-bar title="拍照出库" left-arrow @click-left="$router.back()" />

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
      <van-cell-group title="OCR 识别结果">
        <van-cell title="批号" :value="parsed.batch_no || '-'" />
        <van-cell title="数量" :value="parsed.quantity || '-'" />
      </van-cell-group>

      <!-- 匹配库存列表 -->
      <template v-if="matchedItems.length > 0">
        <van-cell-group :title="`匹配到 ${matchedItems.length} 条库存记录（按批号匹配）`">
          <van-cell
            v-for="item in matchedItems"
            :key="item.id"
            clickable
            :class="{ 'selected-item': selectedItem?.id === item.id }"
            @click="selectedItem = item"
          >
            <template #title>
              <div class="item-title">{{ [item.package_type, item.spec, item.plating_zone, item.surface_treatment].filter(Boolean).join('-') || '-' }}</div>
            </template>
            <template #label>
              <div>{{ item.package_type || '-' }} | {{ item.manufacturer || '-' }}</div>
              <div>批号: {{ item.batch_no || '-' }}</div>
            </template>
            <template #value>
              <span class="qty">库存: {{ item.quantity }}K</span>
            </template>
          </van-cell>
        </van-cell-group>

        <div v-if="selectedItem" class="out-form">
          <van-cell-group title="出库信息">
            <van-field v-model="outQuantity" label="出库数量(K)" type="number" placeholder="请输入出库数量" required />
          </van-cell-group>

          <div class="submit-bar">
            <van-button type="danger" block size="large" @click="doStockOut" :loading="submitting">
              确认出库
            </van-button>
          </div>
        </div>
      </template>

      <van-empty v-else-if="searchDone" description="未找到匹配批号的库存记录" class="compact-empty" />

      <div class="manual-out-bar" v-if="!matchedItems.length && searchDone">
        <van-button block size="small" @click="$router.push({ path: '/stock-out', query: { search: parsed.batch_no || '' } })">手动搜索出库</van-button>
      </div>

      <div class="raw-text" v-if="ocrResult.raw_text">
        <van-cell-group title="原始识别文字">
          <div class="raw-text-content">{{ ocrResult.raw_text }}</div>
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
import { ocrRecognize, getInventoryList, stockOut } from '../api'
import { getRawPhoto, isWebRTCSupported } from '../utils/wxsdk'
import { parseQtyToK } from '../utils/qty'
import Viewfinder from '../components/Viewfinder.vue'
import CropModal from '../components/CropModal.vue'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const ocrResult = ref(null)
const parsed = reactive({
  spec: '', manufacturer: '', batch_no: '', quantity: '',
})
const matchedItems = ref([])
const selectedItem = ref(null)
const searchDone = ref(false)
const outQuantity = ref('')

// 取景框 + 裁剪弹窗状态
const showViewfinder = ref(false)
const showCrop = ref(false)
const cropFile = ref(null)

async function handleCapture(source = 'camera') {
  if (source === 'camera' && isWebRTCSupported()) {
    showViewfinder.value = true
  } else {
    try {
      const file = await getRawPhoto(source)
      cropFile.value = file
      showCrop.value = true
    } catch (e) {
      if (e.message !== '未选择图片') {
        showToast({ message: '拍照失败: ' + e.message, position: 'bottom' })
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

function onViewfinderCancel() {
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
  matchedItems.value = []
  selectedItem.value = null
  searchDone.value = false
  try {
    const result = await ocrRecognize(fileInfo.file)
    if (result.error) {
      showToast({ message: result.error, position: 'bottom' })
      return
    }
    ocrResult.value = result
    if (result.parsed) {
      parsed.spec = result.parsed.spec || ''
      parsed.manufacturer = result.parsed.manufacturer || ''
      parsed.batch_no = result.parsed.batch_no || ''
      parsed.quantity = result.parsed.quantity || ''
      outQuantity.value = result.parsed.quantity || ''
    }
    await findMatchByBatch()
  } catch (e) {
    showToast({ message: '识别失败: ' + e.message, position: 'bottom' })
  } finally {
    loading.value = false
  }
}

async function findMatchByBatch() {
  if (!parsed.batch_no) {
    searchDone.value = true
    return
  }
  try {
    const data = await getInventoryList(parsed.batch_no, 1, 100)
    const items = (data.items || []).filter(i => i.batch_no === parsed.batch_no)
    matchedItems.value = items
    if (items.length === 1) {
      selectedItem.value = items[0]
    }
  } catch (e) { console.warn(e) }
  searchDone.value = true
}

async function doStockOut() {
  if (!selectedItem.value) return showToast('请选择一条库存记录')
  const qty = Number(outQuantity.value)
  if (!qty || qty <= 0) return showToast('请输入有效出库数量')
  const currentQty = parseQtyToK(selectedItem.value.quantity)
  if (qty > currentQty) return showToast('出库数量不能超过库存')
  submitting.value = true
  try {
    await stockOut(selectedItem.value.id, String(qty))
    showSuccessToast('出库成功')
    router.push('/')
  } catch (e) {
    showToast({ message: '出库失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
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
  border-color: #ffc4cb;
  background: var(--lf-out-soft);
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
  background: var(--lf-out);
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
.out-form { margin-top: 8px; }
.raw-text { margin: 4px 0 16px; }
.raw-text-content {
  padding: 12px 14px;
  white-space: pre-wrap;
  font-family: var(--lf-data-font);
  font-size: 12px;
  line-height: 1.55;
  color: var(--lf-text);
}
.submit-bar { padding: 12px; }
.manual-out-bar { padding: 0 16px 12px; }
.compact-empty { padding: 24px 0 4px; }
.compact-empty :deep(.van-empty__image) { width: 64px; height: 64px; }
.qty { font-family: var(--lf-data-font); font-size: 14px; font-weight: 700; color: var(--lf-primary); }
.item-title { font-weight: 700; font-size: 14px; }
.selected-item { background-color: var(--lf-primary-soft); }

.camera-page :deep(.van-cell-group) {
  margin: 12px;
}
.camera-page :deep(.van-cell) {
  border-radius: 0;
}
.camera-page :deep(.van-cell__value),
.camera-page :deep(.van-field__control) {
  font-family: var(--lf-data-font);
}
</style>
