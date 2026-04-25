<template>
  <div class="camera-page">
    <van-nav-bar title="拍照出库" left-arrow @click-left="$router.back()" />

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
      <van-cell-group title="OCR 识别结果">
        <van-cell title="批号" :value="parsed.batch_no || '-'" />
        <van-cell title="厂家规格" :value="parsed.spec || '-'" />
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
              <div class="item-title">{{ item.material_code || '(未填物料编码)' }}</div>
            </template>
            <template #label>
              <div>{{ item.spec }} | {{ item.manufacturer || '-' }}</div>
              <div>批号: {{ item.batch_no || '-' }}</div>
            </template>
            <template #value>
              <span class="qty">库存: {{ item.quantity }}</span>
            </template>
          </van-cell>
        </van-cell-group>

        <div v-if="selectedItem" class="out-form">
          <van-cell-group title="已选库存">
            <van-cell title="物料编码" :value="selectedItem.material_code || '-'" />
            <van-cell title="厂家规格" :value="selectedItem.spec" />
            <van-cell title="批号" :value="selectedItem.batch_no || '-'" />
            <van-cell title="当前库存" :value="String(selectedItem.quantity)" />
            <van-cell v-if="selectedItem.note" title="备注" :value="selectedItem.note" />
          </van-cell-group>

          <van-cell-group title="出库信息">
            <van-field v-model="outQuantity" label="出库数量" type="number" placeholder="请输入出库数量" required />
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
import { ocrRecognize, getInventoryList, stockOut } from '../api'
import { getPhoto } from '../utils/wxsdk'

const router = useRouter()

function parseQty(val) {
  if (typeof val === 'number') return val
  const s = String(val).trim()
  const kMatch = s.match(/([\d.]+)\s*[Kk]/)
  if (kMatch) return parseFloat(kMatch[1]) * 1000
  const mMatch = s.match(/([\d.]+)\s*[Mm]/)
  if (mMatch) return parseFloat(mMatch[1]) * 1000000
  const numMatch = s.match(/([\d.]+)/)
  return numMatch ? parseFloat(numMatch[1]) : 0
}
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
  const currentQty = parseQty(selectedItem.value.quantity)
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
