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
      <span class="section-action" @click="showOutForm = true">
        <van-icon name="upgrade" size="14" />
        出库
      </span>
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
            <div v-if="b.note">备注: {{ b.note }}</div>
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast, showSuccessToast, showConfirmDialog } from 'vant'
import { getInventoryGroupedDetail, stockOut, deleteInventory } from '../api'
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
const showOutForm = ref(false)
const outBatch = ref(null)
const outQuantity = ref('')
const submitting = ref(false)

onMounted(() => { loadData() })

async function loadData() {
  try {
    const q = route.query
    const data = await getInventoryGroupedDetail({
      package_type: q.package_type || '',
      spec: q.spec || '',
      plating_zone: q.plating_zone || '',
      surface_treatment: q.surface_treatment || '',
      manufacturer: q.manufacturer || '',
    })
    Object.assign(info, data)
    batches.value = data.batches
  } catch (e) {
    showToast('获取详情失败')
  }
}

function onEdit() {
  const q = route.query
  router.push({
    name: 'InventoryGroupedEdit',
    query: {
      package_type: q.package_type || '',
      spec: q.spec || '',
      plating_zone: q.plating_zone || '',
      surface_treatment: q.surface_treatment || '',
      manufacturer: q.manufacturer || '',
    },
  })
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
.section-action {
  font-size: 13px; color: #ee0a24; cursor: pointer;
  display: flex; align-items: center; gap: 4px;
}
.batch-list { padding: 0 12px; }
.batch-title { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.qty { font-size: 14px; font-weight: 600; color: #1989fa; }
.qty-alert { font-size: 14px; font-weight: 600; color: #ee0a24; }
.selected-batch { background: #f0f9ff; }
.batch-delete-btn { height: 100%; }

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
