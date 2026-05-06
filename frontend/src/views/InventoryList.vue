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

    <!-- 筛选栏：始终可见，修改即搜 -->
    <div class="filter-bar">
      <div class="filter-row">
        <div class="filter-chip" :class="{ active: filters.package_type }" @click="focusField('package_type')">
          <span class="chip-label">封装</span>
          <span class="chip-val">{{ filters.package_type || '全部' }}</span>
        </div>
        <div class="filter-chip" :class="{ active: filters.spec }" @click="focusField('spec')">
          <span class="chip-label">规格</span>
          <span class="chip-val">{{ filters.spec || '全部' }}</span>
        </div>
        <div class="filter-chip" :class="{ active: filters.plating_zone }" @click="showPlatingPicker = true">
          <span class="chip-label">镀银</span>
          <span class="chip-val">{{ platingLabel(filters.plating_zone) }}</span>
        </div>
        <div class="filter-chip" :class="{ active: filters.surface_treatment }" @click="showSurfacePicker = true">
          <span class="chip-label">粗化</span>
          <span class="chip-val">{{ surfaceLabel(filters.surface_treatment) }}</span>
        </div>
      </div>
      <div v-if="hasActiveFilters" class="filter-bar-bottom">
        <span class="filter-reset-link" @click="resetFilters">清除所有筛选</span>
      </div>
    </div>

    <!-- 弹出输入框（封装/规格） -->
    <van-action-sheet v-model:show="showFieldSheet" :title="'输入' + activeFieldLabel">
      <div class="field-sheet-body">
        <van-field
          v-model="activeFieldValue"
          :placeholder="'输入' + activeFieldLabel"
          clearable
          autofocus
          @input="onFieldInput"
        />
      </div>
    </van-action-sheet>

    <van-popup v-model:show="showPlatingPicker" round position="bottom">
      <van-picker :columns="platingOptions" @confirm="onPlatingConfirm" @cancel="showPlatingPicker = false" />
    </van-popup>
    <van-popup v-model:show="showSurfacePicker" round position="bottom">
      <van-picker :columns="surfaceOptions" @confirm="onSurfaceConfirm" @cancel="showSurfacePicker = false" />
    </van-popup>

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
const showPlatingPicker = ref(false)
const showSurfacePicker = ref(false)
// 文本字段弹出输入
const showFieldSheet = ref(false)
const activeFieldKey = ref('')
const activeFieldValue = ref('')
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

const fieldLabels = {
  package_type: '封装形式',
  spec: '规格',
}

const activeFieldLabel = computed(() => fieldLabels[activeFieldKey.value] || '')

function platingLabel(v) { return v || '全部' }
function surfaceLabel(v) { return v || '全部' }

function focusField(key) {
  activeFieldKey.value = key
  activeFieldValue.value = filters[key] || ''
  showFieldSheet.value = true
}

let searchTimer = null
function onFieldInput() {
  filters[activeFieldKey.value] = activeFieldValue.value
  clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadData(), 300)
}

function onPlatingConfirm({ selectedValues }) {
  filters.plating_zone = selectedValues[0] || ''
  showPlatingPicker.value = false
  loadData()
}
function onSurfaceConfirm({ selectedValues }) {
  filters.surface_treatment = selectedValues[0] || ''
  showSurfacePicker.value = false
  loadData()
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
/* 筛选栏 - Chip 风格 */
.filter-bar {
  padding: 4px 12px 8px;
}
.filter-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.filter-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 16px;
  border: 1px solid #e0e0e0;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  flex: 1;
  min-width: 0;
  justify-content: center;
}
.filter-chip:active {
  opacity: 0.7;
}
.filter-chip.active {
  border-color: #1989fa;
  background: #f0f9ff;
}
.chip-label {
  color: #999;
  white-space: nowrap;
}
.chip-val {
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 80px;
}
.filter-chip.active .chip-val {
  color: #1989fa;
  font-weight: 500;
}
.filter-bar-bottom {
  display: flex;
  justify-content: flex-end;
  padding-top: 6px;
}
.filter-reset-link {
  font-size: 12px;
  color: #ee0a24;
  cursor: pointer;
}
/* 弹出输入框 */
.field-sheet-body {
  padding: 16px;
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
