<template>
  <div class="inventory-page">
    <van-nav-bar title="库存导出" left-arrow @click-left="$router.back()">
      <template #right>
        <van-button size="small" type="success" icon="down" @click="doExport" :loading="exporting" class="export-nav-btn">导出Excel</van-button>
      </template>
    </van-nav-bar>

    <div class="search-bar">
      <van-search v-model="searchText" placeholder="搜索规格/批号/厂家" @search="loadData" />
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="onRefresh">
      <van-list v-model:loading="loading" :finished="finished" @load="loadMore">
        <van-swipe-cell v-for="item in items" :key="item.id">
          <van-cell
            :title="item.material_code || item.spec"
            :label="`${item.spec} | ${item.manufacturer || '-'} | 批号: ${item.batch_no || '-'}${item.note ? ' | ' + item.note : ''}`"
            is-link
            @click="$router.push(`/inventory/${item.id}`)"
          >
            <template #value>
              <span :class="isLowStock(item) ? 'qty-alert' : 'qty'">
                {{ item.quantity }}
                <van-tag v-if="isLowStock(item)" type="danger" size="medium">预警</van-tag>
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
import { ref } from 'vue'
import { showToast, showSuccessToast, showDialog } from 'vant'
import { getInventoryList, deleteInventory, exportInventory } from '../api'
import { isLowStock } from '../utils/qty'

const LOW_STOCK_THRESHOLD = 2  // 单位: K（2K = 2000 只）

const searchText = ref('')
const items = ref([])
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const exporting = ref(false)
let page = 1

async function loadData() {
  page = 1
  finished.value = false
  items.value = []
  await loadMore()
}

async function loadMore() {
  try {
    const data = await getInventoryList(searchText.value, page)
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
    await exportInventory(searchText.value)
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
  padding: 8px 12px;
}
.search-bar :deep(.van-search) {
  padding: 0;
  background: white;
  border-radius: 8px;
}
.search-bar :deep(.van-search__content) {
  border-radius: 8px;
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
