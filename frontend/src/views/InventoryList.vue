<template>
  <div class="inventory-page">
    <van-nav-bar :title="isAlertMode ? '低库存项' : '库存'" left-arrow @click-left="$router.back()">
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
        <div class="filter-chip" :class="{ active: filters.package_type }" @click="showPkgPicker = true">
          <span class="chip-label">封装形式</span>
          <span class="chip-val">{{ filters.package_type || '全部' }}</span>
        </div>
        <div class="filter-chip" :class="{ active: filters.spec }" @click="showSpecPicker = true">
          <span class="chip-label">规格</span>
          <span class="chip-val">{{ filters.spec || '全部' }}</span>
        </div>
        <div class="filter-chip" :class="{ active: filters.plating_zone }" @click="showPlatingPicker = true">
          <span class="chip-label">镀银</span>
          <span class="chip-val">{{ filterLabel(filters.plating_zone) }}</span>
        </div>
        <div class="filter-chip" :class="{ active: filters.surface_treatment }" @click="showSurfacePicker = true">
          <span class="chip-label">粗化</span>
          <span class="chip-val">{{ filterLabel(filters.surface_treatment) }}</span>
        </div>
        <div class="filter-chip" :class="{ active: filters.manufacturer }" @click="showMfrPicker = true">
          <span class="chip-label">厂家</span>
          <span class="chip-val">{{ filters.manufacturer || '全部' }}</span>
        </div>
      </div>
      <div v-if="hasActiveFilters" class="filter-bar-bottom">
        <span class="filter-reset-link" @click="resetFilters">清除所有筛选</span>
      </div>
    </div>

    <!-- 动态选项 Picker -->
    <van-popup v-model:show="showPkgPicker" round position="bottom">
      <van-picker :columns="pkgOptions" @confirm="onPkgConfirm" @cancel="showPkgPicker = false" />
    </van-popup>
    <van-popup v-model:show="showSpecPicker" round position="bottom">
      <van-picker :columns="specOptions" @confirm="onSpecConfirm" @cancel="showSpecPicker = false" />
    </van-popup>
    <van-popup v-model:show="showPlatingPicker" round position="bottom">
      <van-picker :columns="platingOptions" @confirm="onPlatingConfirm" @cancel="showPlatingPicker = false" />
    </van-popup>
    <van-popup v-model:show="showSurfacePicker" round position="bottom">
      <van-picker :columns="surfaceOptions" @confirm="onSurfaceConfirm" @cancel="showSurfacePicker = false" />
    </van-popup>
    <van-popup v-model:show="showMfrPicker" round position="bottom">
      <van-picker :columns="mfrOptions" @confirm="onMfrConfirm" @cancel="showMfrPicker = false" />
    </van-popup>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list v-model:loading="loading" :finished="finished" @load="loadMore">
        <van-swipe-cell v-for="item in items" :key="item.package_type + item.spec + item.plating_zone + item.surface_treatment + item.manufacturer">
          <van-cell
            :title="[item.package_type, item.spec, item.plating_zone, item.surface_treatment].filter(Boolean).join('-') || '-'"
            is-link
            @click="goGroupedDetail(item)"
          >
            <template #label>
              <span>{{ item.manufacturer || '-' }}</span>
            </template>
            <template #value>
              <div class="item-right">
                <span :class="isLowStock(item.total_quantity) ? 'qty-alert' : 'qty'">
                  {{ item.total_quantity }}K
                </span>
                <div class="item-tags">
                  <van-tag type="primary" size="medium" class="batch-tag">{{ item.batch_count }}批次</van-tag>
                  <van-tag v-if="isLowStock(item.total_quantity)" type="danger" size="medium">预警</van-tag>
                </div>
              </div>
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
import { ref, reactive, computed, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { showToast, showSuccessToast, showDialog } from 'vant'
import { getInventoryGrouped, deleteInventoryGrouped, exportInventory, getFilterOptions } from '../api'
import { isLowStock } from '../utils/qty'
import { platingFilterOptions as platingOptions, surfaceFilterOptions as surfaceOptions } from '../composables/useInventoryEnums'

const router = useRouter()
const route = useRoute()
const isAlertMode = computed(() => !!route.query.alert)
watch(() => route.query.alert, () => loadData())
const searchText = ref('')
loadFilterOptions()
const items = ref([])
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const exporting = ref(false)
const showPkgPicker = ref(false)
const showSpecPicker = ref(false)
const showPlatingPicker = ref(false)
const showSurfacePicker = ref(false)
const showMfrPicker = ref(false)
let page = 1

const filters = reactive({
  package_type: '',
  spec: '',
  plating_zone: '',
  surface_treatment: '',
  manufacturer: '',
})

const pkgOptions = ref([{ text: '全部', value: '' }])
const specOptions = ref([{ text: '全部', value: '' }])
const mfrOptions = ref([{ text: '全部', value: '' }])

const filterLabel = (v) => v || '全部'

async function loadFilterOptions() {
  try {
    const opts = await getFilterOptions()
    pkgOptions.value = [{ text: '全部', value: '' }, ...opts.package_types.map(v => ({ text: v, value: v }))]
    specOptions.value = [{ text: '全部', value: '' }, ...opts.specs.map(v => ({ text: v, value: v }))]
    mfrOptions.value = [{ text: '全部', value: '' }, ...opts.manufacturers.map(v => ({ text: v, value: v }))]
  } catch (e) { console.warn(e) }
}

function makePickerHandler(filterKey, showRef) {
  return ({ selectedValues }) => {
    filters[filterKey] = selectedValues[0] || ''
    showRef.value = false
    loadData()
  }
}
const onPkgConfirm = makePickerHandler('package_type', showPkgPicker)
const onSpecConfirm = makePickerHandler('spec', showSpecPicker)
const onPlatingConfirm = makePickerHandler('plating_zone', showPlatingPicker)
const onSurfaceConfirm = makePickerHandler('surface_treatment', showSurfacePicker)
const onMfrConfirm = makePickerHandler('manufacturer', showMfrPicker)

const hasActiveFilters = computed(() =>
  filters.package_type || filters.spec || filters.plating_zone || filters.surface_treatment || filters.manufacturer,
)

function getFilterParams() {
  const params = {}
  for (const [k, v] of Object.entries(filters)) {
    if (v) params[k] = v
  }
  return params
}

function goGroupedDetail(item) {
  const q = {
    package_type: item.package_type || '',
    spec: item.spec || '',
    plating_zone: item.plating_zone || '',
    surface_treatment: item.surface_treatment || '',
    manufacturer: item.manufacturer || '',
  }
  router.push({ name: 'InventoryGroupedDetail', query: q })
}

async function loadData() {
  page = 1
  finished.value = false
  items.value = []
  await loadMore()
}

async function loadMore() {
  try {
    const data = await getInventoryGrouped(searchText.value, page, getFilterParams(), isAlertMode.value)
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

function onRefresh() { loadData() }
function onSearch() { loadData() }

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
      message: `删除「${[item.package_type, item.spec, item.plating_zone, item.surface_treatment].filter(Boolean).join('-')}」的所有批次（共 ${item.batch_count} 批）？`,
      showCancelButton: true,
    })
    await deleteInventoryGrouped({
      package_type: item.package_type,
      spec: item.spec,
      plating_zone: item.plating_zone,
      surface_treatment: item.surface_treatment,
      manufacturer: item.manufacturer,
    })
    showSuccessToast('已删除')
    loadData()
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
.search-bar { padding: 8px 12px; }
.search-bar :deep(.van-search) {
  padding: 0;
  background: white;
}
/* content / field / control 三层同高，control 用 line-height==height 实现与设备无关的垂直居中 */
.search-bar :deep(.van-search__content) {
  height: 34px;
  padding: 0 12px;
  border-radius: 8px;
  display: flex;
  align-items: center;
}
.search-bar :deep(.van-search__field) {
  flex: 1;
  height: 34px;
  padding: 0;
  display: flex;
  align-items: center;
}
.search-bar :deep(.van-field__control) {
  height: 34px;
  line-height: 34px;
  padding: 0;
}
.filter-bar { padding: 4px 12px 8px; }
.filter-row { display: flex; gap: 8px; flex-wrap: wrap; }
.filter-chip {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 10px; border-radius: 16px;
  border: 1px solid #e0e0e0; background: #fff;
  font-size: 12px; cursor: pointer; transition: all 0.15s;
  flex: 1; min-width: 0; justify-content: center;
}
.filter-chip:active { opacity: 0.7; }
.filter-chip.active { border-color: #1989fa; background: #f0f9ff; }
.chip-label { color: #999; white-space: nowrap; }
.chip-val { color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 80px; }
.filter-chip.active .chip-val { color: #1989fa; font-weight: 500; }
.filter-bar-bottom { display: flex; justify-content: flex-end; padding-top: 6px; }
.filter-reset-link { font-size: 12px; color: #ee0a24; cursor: pointer; }
.inventory-page :deep(.van-cell) {
  margin: 8px 12px; border-radius: 8px; background: white; padding: 12px 16px;
}
.inventory-page :deep(.van-cell__value) {
  flex: none;
  text-align: right;
}
.inventory-page :deep(.van-swipe-cell) { margin: 0 12px; }
.inventory-page :deep(.van-swipe-cell__right) { border-radius: 8px; }
.delete-btn { border-radius: 0 8px 8px 0; }
.inventory-page :deep(.van-nav-bar) { background: white; }
.item-right { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; min-width: 80px; }
.item-tags { display: flex; gap: 4px; }
.qty { font-size: 16px; font-weight: bold; color: #1989fa; }
.qty-alert { font-size: 16px; font-weight: bold; color: #ee0a24; }
.batch-tag { flex-shrink: 0; }
.inventory-page :deep(.van-list) { margin-top: 8px; }
.inventory-page :deep(.van-empty) { padding: 60px 0; }
</style>
