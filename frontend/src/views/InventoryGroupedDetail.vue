<template>
  <div class="grouped-detail">
    <van-nav-bar title="库存详情" left-arrow @click-left="$router.back()">
      <template #right>
        <van-icon name="edit" size="18" @click="onEdit" />
      </template>
    </van-nav-bar>

    <van-cell-group title="基本信息">
      <van-cell title="封装形式" :value="info.package_type || '-'" />
      <van-cell title="规格" :value="info.spec || '-'" />
      <van-cell title="镀银区域" :value="info.plating_zone || '-'" />
      <van-cell title="表面粗化处理" :value="info.surface_treatment || '-'" />
      <van-cell title="生产厂家" :value="info.manufacturer || '-'" />
    </van-cell-group>

    <van-cell-group title="汇总">
      <van-cell title="总数量" :value="`${info.total_quantity}K`" />
      <van-cell title="批次数" :value="`${info.batch_count} 批`" />
    </van-cell-group>

    <div class="section-title">
      <span>批次明细</span>
      <div class="section-actions">
        <span class="section-action section-action-in" @click="showInForm = true">
          <van-icon name="down" size="14" />
          入库
        </span>
        <span class="section-action" @click="showOutForm = true">
          <van-icon name="upgrade" size="14" />
          出库
        </span>
      </div>
    </div>

    <div class="batch-list">
      <van-swipe-cell v-for="b in batches" :key="b.id">
        <van-cell
          clickable
          :class="{ 'selected-batch': selectedBatch?.id === b.id }"
          @click="selectedBatch = b"
        >
          <template #title>
            <div class="batch-title">
              <span>批号: {{ b.batch_no || '-' }}</span>
              <van-tag v-if="isLowStock(info.total_quantity)" type="danger" size="small">预警</van-tag>
            </div>
          </template>
          <template #label>
            <div>生产日期: {{ b.production_date || '-' }}</div>
            <div>有效期: {{ b.expiry_date || '-' }}</div>
            <div v-if="b.note" class="note-row">
              <span>备注: {{ b.note }}</span>
              <van-icon name="edit" size="14" color="#1989fa" @click.stop="onEditNote(b)" />
            </div>
            <div v-else class="note-row">
              <span class="add-note" @click.stop="onEditNote(b)">添加备注</span>
            </div>
          </template>
          <template #value>
            <span :class="isLowStock(info.total_quantity) ? 'qty-alert' : 'qty'">{{ b.quantity }}K</span>
          </template>
        </van-cell>
        <template #right>
          <van-button square type="danger" text="删除" class="batch-delete-btn"
            @click="onDeleteBatch(b)" />
        </template>
      </van-swipe-cell>
      <van-empty v-if="!batches.length" description="暂无批次数据" />
    </div>

    <!-- 出入库记录 -->
    <div class="section-title">
      <span>出入库记录</span>
    </div>
    <div class="log-list">
      <van-list v-model:loading="logsLoading" :finished="logsFinished" @load="loadMoreLogs" :immediate-check="false">
        <van-swipe-cell v-for="log in stockLogs" :key="log.id">
          <div class="log-item">
            <div class="log-icon" :class="log.type === 'in' ? 'log-in' : 'log-out'">
              <van-icon
                :name="log.type === 'in' ? 'down' : 'upgrade'"
                :color="log.type === 'in' ? '#07c160' : '#ee0a24'"
                size="20"
              />
            </div>
            <div class="log-main">
              <span class="log-title">{{ log.batch_no || '-' }}</span>
              <span class="log-time">{{ log.created_at }}</span>
              <span v-if="log.note" class="log-note">{{ log.note }}</span>
            </div>
            <span class="log-qty" :class="log.type === 'in' ? 'text-green' : 'text-red'">
              {{ log.type === 'in' ? '+' : '-' }}{{ log.quantity }}K
            </span>
          </div>
          <template #right>
            <van-button square type="danger" text="删除" class="batch-delete-btn"
              @click="onDeleteLog(log)" />
          </template>
        </van-swipe-cell>
        <template #finished>
          <span v-if="stockLogs.length" class="log-finished">没有更多了</span>
        </template>
      </van-list>
      <van-empty v-if="!logsLoading && !stockLogs.length" description="暂无出入库记录" image="default" />
    </div>

    <!-- 出库弹窗 -->
    <!-- 入库弹窗 -->
    <van-popup v-model:show="showInForm" position="bottom" round :style="{ maxHeight: '70%' }">
      <div class="out-popup">
        <div class="out-popup-header">
          <span class="out-popup-title">选择入库批次</span>
          <van-icon name="cross" size="20" color="#999" @click="showInForm = false" />
        </div>
        <div class="out-batch-list">
          <div
            v-for="b in batches"
            :key="'in-'+b.id"
            class="out-batch-item"
            :class="{ active: inBatch?.id === b.id }"
            @click="inBatch = b"
          >
            <div class="out-batch-info">
              <span class="out-batch-no">批号: {{ b.batch_no || '-' }}</span>
              <span class="out-batch-date">{{ b.production_date || '-' }}</span>
            </div>
            <span class="out-batch-qty">{{ b.quantity }}K</span>
          </div>
        </div>
        <div v-if="inBatch" class="out-form">
          <van-field v-model="inQuantity" label="入库数量(K)" type="number" placeholder="请输入入库数量" />
          <van-button type="primary" block @click="doStockIn" :loading="submitting">确认入库</van-button>
        </div>
      </div>
    </van-popup>

    <!-- 出库弹窗 -->
    <van-popup v-model:show="showOutForm" position="bottom" round :style="{ maxHeight: '70%' }">
      <div class="out-popup">
        <div class="out-popup-header">
          <span class="out-popup-title">选择出库批次</span>
          <van-icon name="cross" size="20" color="#999" @click="showOutForm = false" />
        </div>
        <div class="out-batch-list">
          <div
            v-for="b in batches"
            :key="'out-'+b.id"
            class="out-batch-item"
            :class="{ active: outBatch?.id === b.id }"
            @click="outBatch = b"
          >
            <div class="out-batch-info">
              <span class="out-batch-no">批号: {{ b.batch_no || '-' }}</span>
              <span class="out-batch-date">{{ b.production_date || '-' }}</span>
            </div>
            <span class="out-batch-qty">{{ b.quantity }}K</span>
          </div>
        </div>
        <div v-if="outBatch" class="out-form">
          <van-field v-model="outQuantity" label="出库数量(K)" type="number" placeholder="请输入出库数量" />
          <van-button type="danger" block @click="doStockOut" :loading="submitting">确认出库</van-button>
        </div>
      </div>
    </van-popup>

    <!-- 备注编辑弹窗 -->
    <van-popup v-model:show="showNoteForm" position="bottom" round :style="{ maxHeight: '50%' }">
      <div class="note-popup">
        <div class="out-popup-header">
          <span class="out-popup-title">编辑备注</span>
          <van-icon name="cross" size="20" color="#999" @click="showNoteForm = false" />
        </div>
        <div class="note-popup-info">
          批号: {{ noteBatch?.batch_no || '-' }}　　数量: {{ noteBatch?.quantity || '0' }}K
        </div>
        <van-field v-model="noteText" type="textarea" rows="3" placeholder="请输入备注" />
        <div style="padding: 12px 16px;">
          <van-button type="primary" block @click="saveNote" :loading="noteSubmitting">保存</van-button>
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast, showSuccessToast, showConfirmDialog } from 'vant'
import { getInventoryGroupedDetail, stockIn, stockOut, deleteInventory, updateInventory, getStockLogsGrouped, deleteStockLog } from '../api'
import { isLowStock, parseQtyToK } from '../utils/qty'

const route = useRoute()
const router = useRouter()

const info = reactive({
  package_type: '', spec: '', plating_zone: '',
  surface_treatment: '', manufacturer: '',
  total_quantity: '0', batch_count: 0,
})
const batches = ref([])
const selectedBatch = ref(null)
const showInForm = ref(false)
const inBatch = ref(null)
const inQuantity = ref('')
const showOutForm = ref(false)
const outBatch = ref(null)
const outQuantity = ref('')
const submitting = ref(false)
const showNoteForm = ref(false)
const noteBatch = ref(null)
const noteText = ref('')
const noteSubmitting = ref(false)
const stockLogs = ref([])
const logsLoading = ref(false)
const logsFinished = ref(false)
let logsPage = 1

onMounted(() => { loadData() })
watch(() => route.fullPath, () => { loadData() })

function getQueryParams() {
  const q = route.query
  return {
    package_type: q.package_type || '',
    spec: q.spec || '',
    plating_zone: q.plating_zone || '',
    surface_treatment: q.surface_treatment || '',
    manufacturer: q.manufacturer || '',
  }
}

async function loadData() {
  try {
    const data = await getInventoryGroupedDetail(getQueryParams())
    Object.assign(info, data)
    batches.value = data.batches
    resetLogs()
    loadMoreLogs()
  } catch (e) {
    if (e.response?.status === 404) {
      showToast('该分组不存在或已被修改')
      router.replace('/inventory')
    } else {
      showToast('获取详情失败')
    }
  }
}

function resetLogs() {
  stockLogs.value = []
  logsPage = 1
  logsFinished.value = false
  logsLoading.value = false
}

async function loadMoreLogs() {
  try {
    const data = await getStockLogsGrouped(getQueryParams(), logsPage, 20)
    if (logsPage === 1) {
      stockLogs.value = data.items
    } else {
      stockLogs.value.push(...data.items)
    }
    logsLoading.value = false
    if (stockLogs.value.length >= data.total) {
      logsFinished.value = true
    } else {
      logsPage++
    }
  } catch (e) {
    logsLoading.value = false
  }
}

function onEdit() {
  router.push({ name: 'InventoryGroupedEdit', query: getQueryParams() })
}

function onEditNote(b) {
  noteBatch.value = b
  noteText.value = b.note || ''
  showNoteForm.value = true
}

async function saveNote() {
  if (!noteBatch.value) return
  noteSubmitting.value = true
  try {
    await updateInventory(noteBatch.value.id, { note: noteText.value.trim() })
    noteBatch.value.note = noteText.value.trim()
    showNoteForm.value = false
    showSuccessToast('保存成功')
  } catch (e) {
    showToast({ message: '保存失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    noteSubmitting.value = false
  }
}

async function onDeleteLog(log) {
  const actionText = log.type === 'in' ? '入库' : '出库'
  try {
    await showConfirmDialog({
      title: '确认删除',
      message: `确定撤销这条${actionText}记录？将${log.type === 'in' ? '从库存中扣减' : '归还到库存'} ${log.quantity}K。`,
      confirmButtonColor: '#ee0a24',
    })
  } catch { return }
  try {
    await deleteStockLog(log.id)
    showSuccessToast('删除成功')
    loadData()
  } catch (e) {
    showToast(e.response?.data?.detail || '删除失败')
  }
}

async function onDeleteBatch(b) {
  try {
    await showConfirmDialog({
      title: '确认删除',
      message: `删除批号 ${b.batch_no || '-'} 的库存记录（${b.quantity}K）？`,
      confirmButtonColor: '#ee0a24',
    })
  } catch { return }
  try {
    await deleteInventory(b.id)
    showSuccessToast('已删除')
    loadData()
  } catch (e) {
    showToast('删除失败')
  }
}

async function doStockIn() {
  if (!inBatch.value) return showToast('请选择入库批次')
  const qty = Number(inQuantity.value)
  if (!qty || qty <= 0) return showToast('请输入有效入库数量')
  submitting.value = true
  try {
    await stockIn({
      ...getQueryParams(),
      batch_no: inBatch.value.batch_no || '',
      production_date: inBatch.value.production_date || '',
      expiry_date: inBatch.value.expiry_date || '',
      quantity: String(qty),
    })
    showSuccessToast('入库成功')
    showInForm.value = false
    inBatch.value = null
    inQuantity.value = ''
    loadData()
  } catch (e) {
    showToast({ message: '入库失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    submitting.value = false
  }
}

async function doStockOut() {
  if (!outBatch.value) return showToast('请选择出库批次')
  const qty = Number(outQuantity.value)
  if (!qty || qty <= 0) return showToast('请输入有效出库数量')
  const currentQty = parseQtyToK(outBatch.value.quantity)
  if (qty > currentQty) return showToast('出库数量不能超过该批次库存')
  submitting.value = true
  try {
    await stockOut(outBatch.value.id, String(qty))
    showSuccessToast('出库成功')
    showOutForm.value = false
    outBatch.value = null
    outQuantity.value = ''
    loadData()
  } catch (e) {
    showToast({ message: '出库失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.grouped-detail { padding-bottom: 20px; background: #f7f8fa; min-height: 100vh; }
.section-title {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 16px 8px; font-size: 15px; font-weight: 600; color: #333;
}
.section-actions { display: flex; gap: 12px; }
.section-action {
  font-size: 13px; color: #ee0a24; cursor: pointer;
  display: flex; align-items: center; gap: 4px;
}
.section-action-in {
  font-size: 13px; color: #07c160; cursor: pointer;
  display: flex; align-items: center; gap: 4px;
}
.batch-list { padding: 0 12px; }
.batch-title { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.qty { font-size: 14px; font-weight: 600; color: #1989fa; }
.qty-alert { font-size: 14px; font-weight: 600; color: #ee0a24; }
.selected-batch { background: #f0f9ff; }
.batch-delete-btn { height: 100%; }
.note-row { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.add-note { font-size: 12px; color: #1989fa; cursor: pointer; }
.note-popup { padding: 16px 0; }
.note-popup-info { padding: 0 16px 12px; font-size: 13px; color: #666; }
.note-popup :deep(.van-cell) { margin: 0 16px; border-radius: 8px; background: #f7f8fa; }

.log-list { padding: 0 12px; }
.log-finished { display: block; text-align: center; padding: 12px 0; font-size: 13px; color: #999; }
.log-item {
  display: flex; align-items: center; padding: 12px;
  background: white; border-radius: 8px; margin-bottom: 8px;
}
.log-icon {
  width: 36px; height: 36px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  margin-right: 10px; flex-shrink: 0;
}
.log-in { background: #e8f5e9; }
.log-out { background: #fff1f0; }
.log-main { display: flex; flex-direction: column; flex: 1; min-width: 0; }
.log-title { font-size: 14px; font-weight: 500; color: #333; }
.log-time { font-size: 12px; color: #999; margin-top: 2px; }
.log-note { font-size: 12px; color: #666; margin-top: 2px; }
.log-qty { font-size: 15px; font-weight: 700; flex-shrink: 0; margin-left: 8px; }
.text-green { color: #07c160; }
.text-red { color: #ee0a24; }
.grouped-detail :deep(.van-swipe-cell) { margin: 0 0 8px; }
.grouped-detail :deep(.van-swipe-cell__right) { border-radius: 8px; }

.out-popup { padding: 16px; }
.out-popup-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.out-popup-title { font-size: 16px; font-weight: 600; }
.out-batch-list { max-height: 240px; overflow-y: auto; }
.out-batch-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px; border: 1px solid #e0e0e0; border-radius: 8px;
  margin-bottom: 8px; cursor: pointer; transition: all 0.15s;
}
.out-batch-item.active { border-color: #1989fa; background: #f0f9ff; }
.out-batch-info { display: flex; flex-direction: column; }
.out-batch-no { font-size: 14px; font-weight: 500; }
.out-batch-date { font-size: 12px; color: #999; margin-top: 2px; }
.out-batch-qty { font-size: 14px; font-weight: 600; color: #1989fa; }
.out-form { margin-top: 16px; }
</style>
