<template>
  <div class="camera-page">
    <van-nav-bar title="拍照出库" left-arrow @click-left="$router.back()" />

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
      <van-cell-group title="OCR 识别结果">
        <van-cell title="批号" :value="parsed.batch_no || '-'" />
        <van-cell title="规格" :value="parsed.spec || '-'" />
        <van-cell title="生产厂家" :value="parsed.manufacturer || '-'" />
      </van-cell-group>

      <!-- 多条匹配时列表选择 -->
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
          <van-cell-group title="已选库存">
            <van-cell title="封装形式" :value="selectedItem.package_type || '-'" />
            <van-cell title="规格" :value="selectedItem.spec || '-'" />
            <van-cell title="镀银区域" :value="selectedItem.plating_zone || '-'" />
            <van-cell title="表面粗化处理" :value="selectedItem.surface_treatment || '-'" />
            <van-cell title="生产厂家" :value="selectedItem.manufacturer || '-'" />
            <van-cell title="批号" :value="selectedItem.batch_no || '-'" />
            <van-cell title="当前库存(K)" :value="String(selectedItem.quantity)" />
            <van-cell v-if="selectedItem.note" title="备注" :value="selectedItem.note" />
          </van-cell-group>

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

      <van-empty v-else-if="searchDone" description="未找到匹配批号的库存记录" />

      <div class="submit-bar" v-if="!matchedItems.length && searchDone">
        <van-button block @click="$router.push('/stock-out')">手动搜索出库</van-button>
      </div>

      <div class="raw-text" v-if="ocrResult.raw_text">
        <van-cell-group title="原始识别文字">
          <div class="raw-text-content">{{ ocrResult.raw_text }}</div>
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
import { getRawPhoto, compressImage, isWebRTCSupported } from '../utils/wxsdk'
import { parseQtyToK } from '../utils/qty'
import Viewfinder from '../components/Viewfinder.vue'
import CropModal from '../components/CropModal.vue'

const router = useRouter()
const loading = ref(false)
const submitting = ref(false)
const ocrResult = ref(null)
const parsed = reactive({
  spec: '', manufacturer: '', batch_no: '',
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
  try {
    const file = await getRawPhoto('camera')
    cropFile.value = file
    showCrop.value = true
  } catch (e) {
    if (e.message !== '未选择图片') {
      showToast({ message: '拍照失败: ' + e.message, position: 'bottom' })
    }
  }
}

function onViewfinderCancel() {
  showViewfinder.value = false
}

async function onCropConfirm(file) {
  showCrop.value = false
  cropFile.value = null
  const compressed = await compressImage(file)
  await onFileRead({ file: compressed })
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
  if (!parsed.batch_no && !parsed.spec) {
    searchDone.value = true
    return
  }
  try {
    // 先用批号搜索
    let items = []
    if (parsed.batch_no) {
      const data = await getInventoryList(parsed.batch_no, 1, 100)
      items = data.items || []
      // 精确匹配批号
      items = items.filter(i => i.batch_no === parsed.batch_no)
    }
    // 如果批号没匹配到，降级用厂家规格搜索
    if (items.length === 0 && parsed.spec) {
      const data = await getInventoryList(parsed.spec, 1, 100)
      items = data.items || []
      items = items.filter(i => i.spec === parsed.spec)
    }
    matchedItems.value = items
    if (items.length === 1) {
      selectedItem.value = items[0]
    }
  } catch (e) {}
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
  background: #f7f8fa;
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
.out-form { margin-top: 12px; }
.raw-text { margin: 16px 0; }
.raw-text-content {
  padding: 12px 16px;
  white-space: pre-wrap;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
}
.submit-bar { padding: 16px; }
.qty { font-size: 14px; font-weight: bold; color: #1989fa; }
.item-title { font-weight: bold; font-size: 14px; }
.selected-item { background-color: #f0f9ff; }

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
