<template>
  <div class="inventory-page">
    <van-nav-bar title="库存导出" left-arrow @click-left="$router.back()">
      <template #right>
        <van-button size="small" type="success" icon="down" @click="doExport" :loading="exporting" class="export-nav-btn">导出Excel</van-button>
      </template>
    </van-nav-bar>

    <div class="search-bar">
      <van-search v-model="searchText" placeholder="搜索规格/批号/厂家" @search="onSearch" />
    </div>

    <!-- 筛选面板 -->
    <div class="filter-bar">
      <van-button size="small" plain :type="hasActiveFilters ? 'primary' : 'default'" @click="showFilter = !showFilter" class="filter-toggle-btn">
        <span>{{ showFilter ? '收起筛选' : '展开筛选' }}</span>
        <van-icon :name="showFilter ? 'up' : 'down'" />
      </van-button>
      <van-button v-if="hasActiveFilters" size="small" plain type="warning" @click="resetFilters" class="filter-reset-btn">
        清除筛选
      </van-button>
    </div>

    <div v-if="showFilter" class="filter-panel">
      <div class="filter-grid">
        <div class="filter-item">
          <span class="filter-label">封装形式</span>
          <van-field v-model="filters.package_type" placeholder="如 SOP、QFP" clearable />
        </div>
        <div class="filter-item">
          <span class="filter-label">规格</span>
          <van-field v-model="filters.spec" placeholder="规格关键词" clearable />
        </div>
        <div class="filter-item">
          <span class="filter-label">镀银区域</span>
          <van-field
            v-model="filters.plating_zone"
            is-link
            readonly
            placeholder="全部"
            @click="showPlatingPicker = true"
          />
        </div>
        <div class="filter-item">
          <span class="filter-label">表面粗化处理</span>
          <van-field
            v-model="filters.surface_treatment"
            is-link
            readonly
            placeholder="全部"
            @click="showSurfacePicker = true"
          />
        </div>
      </div>
      <div class="filter-actions">
        <van-button type="primary" size="small" @click="applyFilters">应用筛选</van-button>
      </div>
      <van-popup v-model:show="showPlatingPicker" round position="bottom">
        <van-picker :columns="platingOptions" @confirm="onPlatingConfirm" @cancel="showPlatingPicker = false" />
      </van-popup>
      <van-popup v-model:show="showSurfacePicker" round position="bottom">
        <van-picker :columns="surfaceOptions" @confirm="onSurfaceConfirm" @cancel="showSurfacePicker = false" />
      </van-popup>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list v-model:loading="loading" :finished="finished" @load="loadMore">
        <van-swipe-cell v-for="item in items" :key="item.id">
          <van-cell
            :title="[item.package_type, item.spec, item.plating_zone, item.surface_treatment].filter(Boolean).join('-') || '-'"
            :label="`${item.manufacturer || '-'}`"
            is-link
            @click="$router.push(`/inventory/${item.id}`)"
          >
            <template #value>
              <span :class="isLowStock(item.quantity) ? 'qty-alert' : 'qty'">
                {{ item.quantity }}K
                <van-tag v-if="isLowStock(item.quantity)" type="danger" size="medium">预警</van-tag>
              </span>
            </template>
          </van-cell>
          <template #right>
            <van-button square type="danger" text="删除" class="delete-btn" @click="doDelete(item)" />
          </template>
        </van-swipe-cell>
      </van-list>
      <van-empty v-if="!loading && !items.length" description="暂无库存" />
    </van-pull-refresh>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { showToast, showSuccessToast, showDialog } from 'vant'
import { getInventoryList, deleteInventory, exportInventory } from '../api'
import { isLowStock } from '../utils/qty'

const searchText = ref('')
const items = ref([])
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const exporting = ref(false)
const showFilter = ref(false)
const showPlatingPicker = ref(false)
const showSurfacePicker = ref(false)
let page = 1

const filters = reactive({
  package_type: '',
  spec: '',
  plating_zone: '',
  surface_treatment: '',
})

const platingOptions = [
  { text: '全部', value: '' },
  { text: '单环镀', value: '单环镀' },
  { text: '双环镀', value: '双环镀' },
]
const surfaceOptions = [
  { text: '全部', value: '' },
  { text: 'CRC', value: 'CRC' },
  { text: 'SRC', value: 'SRC' },
  { text: 'ERC', value: 'ERC' },
]

function onPlatingConfirm({ selectedValues }) {
  filters.plating_zone = selectedValues[0] || ''
  showPlatingPicker.value = false
}
function onSurfaceConfirm({ selectedValues }) {
  filters.surface_treatment = selectedValues[0] || ''
  showSurfacePicker.value = false
}

const hasActiveFilters = computed(() =>
  filters.package_type || filters.spec || filters.plating_zone || filters.surface_treatment,
)

function getFilterParams() {
  const params = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v
  }
  return params
}

async function loadData() {
  page = 1
  finished.value = false
  items.value = []
  await loadMore()
}

async function loadMore() {
  try {
    const data = await getInventoryList(searchText.value, page, getFilterParams())
    if (page === 1) {
      items.value = data.items
    } else {
      items.value.push(...data.items)
    }
    loading.value = false
    refreshing.value = false
    if (items.value.length >= data.total) {
      finished.value = true
    } else {
      page++
    }
  } catch (e) {
    loading.value = false
    refreshing.value = false
  }
}

function onRefresh() {
  loadData()
}

function onSearch() {
  loadData()
}

function applyFilters() {
  showFilter.value = false
  loadData()
}

function resetFilters() {
  filters.package_type = ''
  filters.spec = ''
  filters.plating_zone = ''
  filters.surface_treatment = ''
  loadData()
}

async function doDelete(item) {
  try {
    await showDialog({
      title: '确认删除',
      message: `删除 ${item.spec}（批号: ${item.batch_no || '-'}）的所有库存记录？`,
      showCancelButton: true,
    })
    await deleteInventory(item.id)
    showSuccessToast('已删除')
    items.value = items.value.filter(i => i.id !== item.id)
  } catch (e) {
    if (e !== 'cancel') showToast('删除失败')
  }
}

async function doExport() {
  exporting.value = true
  try {
    await exportInventory(searchText.value, getFilterParams())
    showSuccessToast('导出成功')
  } catch (e) {
    showToast('导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.inventory-page {
  background: #f7f8fa;
  min-height: 100vh;
  padding-bottom: 20px;
}
.export-nav-btn {
  font-size: 13px;
  padding: 0 12px;
  height: 32px;
  border-radius: 16px;
}
.search-bar {
  padding: 8px 12px 0;
}
.search-bar :deep(.van-search) {
  padding: 0;
  background: white;
  border-radius: 8px;
}
.search-bar :deep(.van-search__content) {
  border-radius: 8px;
}
/* 筛选面板 */
.filter-bar {
  display: flex;
  gap: 8px;
  padding: 8px 12px;
  align-items: center;
}
.filter-toggle-btn {
  font-size: 13px;
  height: 32px;
  border-radius: 6px;
}
.filter-reset-btn {
  font-size: 13px;
  height: 32px;
  border-radius: 6px;
}
.filter-panel {
  background: white;
  margin: 0 12px 4px;
  padding: 8px 12px 4px;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.filter-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 0;
}
.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-label {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
  width: 7em;
  text-align: right;
}
.filter-item :deep(.van-field) {
  flex: 1;
  padding: 6px 8px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  background: #fafafa;
  font-size: 13px;
  min-height: 32px;
}
.filter-select {
  flex: 1;
}
.filter-actions {
  display: flex;
  justify-content: center;
  padding: 8px 0 4px;
}
.inventory-page :deep(.van-cell) {
  margin: 8px 12px;
  border-radius: 8px;
  background: white;
  padding: 12px 16px;
}
.inventory-page :deep(.van-swipe-cell) {
  margin: 0 12px;
}
.inventory-page :deep(.van-swipe-cell__right) {
  border-radius: 8px;
}
.delete-btn {
  border-radius: 0 8px 8px 0;
}
.inventory-page :deep(.van-nav-bar) {
  background: white;
}
.qty {
  font-size: 16px;
  font-weight: bold;
  color: #1989fa;
}
.qty-alert {
  font-size: 16px;
  font-weight: bold;
  color: #ee0a24;
}
.inventory-page :deep(.van-list) {
  margin-top: 8px;
}
.inventory-page :deep(.van-empty) {
  padding: 60px 0;
}
</style>
