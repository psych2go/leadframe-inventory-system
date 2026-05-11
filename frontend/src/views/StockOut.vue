<template>
  <div class="stock-out-page">
    <van-nav-bar title="出库" left-arrow @click-left="$router.back()" />

    <div v-if="!selectedBatch" class="search-area">
      <van-search v-model="searchText" placeholder="搜索规格/批号" @search="doSearch" @clear="doSearch" />

      <template v-if="searchResults.length">
        <div class="group-section" v-for="group in searchResults" :key="group.package_type + group.spec + group.plating_zone + group.surface_treatment + group.manufacturer">
          <van-cell
            :title="[group.package_type, group.spec, group.plating_zone, group.surface_treatment].filter(Boolean).join('-') || '-'"
            :label="group.manufacturer || '-'"
            is-link
            @click="toggleGroup(group)"
          >
            <template #value>
              <div class="group-right">
                <span class="group-qty">{{ group.total_quantity }}K</span>
                <van-tag type="primary" size="small">{{ group.batch_count }}批次</van-tag>
              </div>
            </template>
          </van-cell>
          <div v-if="expandedGroup === group" class="batch-list">
            <van-cell
              v-for="b in group._batches"
              :key="b.id"
              clickable
              @click="selectBatch(b)"
            >
              <template #title>
                <span>批号: {{ b.batch_no || '-' }}</span>
              </template>
              <template #label>
                <span>生产日期: {{ b.production_date || '-' }}</span>
              </template>
              <template #value>
                <span class="batch-qty">{{ b.quantity }}K</span>
              </template>
            </van-cell>
          </div>
        </div>
      </template>
      <van-empty v-else-if="searched" description="未找到匹配的库存" />
    </div>

    <div v-else class="out-form">
      <van-cell-group title="库存信息">
        <van-cell title="封装形式" :value="selectedBatch.package_type || '-'" />
        <van-cell title="规格" :value="selectedBatch.spec || '-'" />
        <van-cell title="镀银区域" :value="selectedBatch.plating_zone || '-'" />
        <van-cell title="表面粗化处理" :value="selectedBatch.surface_treatment || '-'" />
        <van-cell title="生产厂家" :value="selectedBatch.manufacturer || '-'" />
        <van-cell title="批号" :value="selectedBatch.batch_no || '-'" />
        <van-cell title="当前库存(K)" :value="String(selectedBatch.quantity)" />
        <van-cell v-if="selectedBatch.note" title="备注" :value="selectedBatch.note" />
      </van-cell-group>

      <van-cell-group title="出库信息">
        <van-field v-model="outQuantity" label="出库数量(K)" type="number" placeholder="请输入出库数量" />
      </van-cell-group>

      <div class="submit-bar">
        <van-button type="primary" block @click="doStockOut" :loading="submitting">确认出库</van-button>
        <van-button block @click="selectedBatch = null" style="margin-top: 8px;">重新选择</van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { getInventoryGrouped, getInventoryGroupedDetail, getInventory, stockOut } from '../api'
import { parseQtyToK } from '../utils/qty'

const route = useRoute()

const searchText = ref('')
const searchResults = ref([])
const searched = ref(false)
const expandedGroup = ref(null)
const selectedBatch = ref(null)
const outQuantity = ref('')
const submitting = ref(false)

onMounted(async () => {
  if (route.params.id) {
    try {
      selectedBatch.value = await getInventory(route.params.id)
    } catch (e) {}
    return
  }
  // 从拍照出库跳转时，带入搜索词并自动搜索
  const q = route.query.search
  if (q) {
    searchText.value = q
  }
  doSearch()
})

async function doSearch() {
  try {
    const data = await getInventoryGrouped(searchText.value.trim(), 1, 50)
    searchResults.value = data.items.map(g => ({ ...g, _batches: [] }))
    searched.value = true
    expandedGroup.value = null
  } catch (e) {}
}

async function toggleGroup(group) {
  if (expandedGroup.value === group) {
    expandedGroup.value = null
    return
  }
  expandedGroup.value = group
  if (!group._batches.length) {
    try {
      const detail = await getInventoryGroupedDetail({
        package_type: group.package_type,
        spec: group.spec,
        plating_zone: group.plating_zone,
        surface_treatment: group.surface_treatment,
        manufacturer: group.manufacturer,
      })
      group._batches = detail.batches
    } catch (e) {}
  }
}

function selectBatch(batch) {
  selectedBatch.value = batch
  outQuantity.value = ''
}

async function doStockOut() {
  const qty = Number(outQuantity.value)
  if (!qty || qty <= 0) return showToast('请输入有效出库数量')
  const currentQty = parseQtyToK(selectedBatch.value.quantity)
  if (qty > currentQty) return showToast('出库数量不能超过库存')
  submitting.value = true
  try {
    await stockOut(selectedBatch.value.id, String(qty))
    showSuccessToast('出库成功')
    selectedBatch.value = null
  } catch (e) {
    showToast({ message: '出库失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.search-area { padding: 0; }
.group-section { margin: 0; }
.group-right { display: flex; align-items: center; gap: 6px; }
.group-qty { font-size: 14px; font-weight: 600; color: #1989fa; }
.batch-list { background: #f7f8fa; }
.batch-list :deep(.van-cell) { padding-left: 24px; }
.batch-qty { font-size: 14px; font-weight: 500; color: #333; }
.out-form { margin-top: 16px; }
.submit-bar { padding: 16px; }
</style>
