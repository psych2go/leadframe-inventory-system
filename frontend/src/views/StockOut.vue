<template>
  <div class="stock-out-page">
    <van-nav-bar title="出库" left-arrow @click-left="$router.back()" />

    <div v-if="!selectedItem" class="search-area">
      <van-search v-model="searchText" placeholder="搜索规格/批号" @search="doSearch" />
      <van-cell-group v-if="searchResults.length">
        <van-cell
          v-for="item in searchResults"
          :key="item.id"
          :title="item.material_code || item.spec"
          :label="`${item.spec} | ${item.manufacturer || ''} | 批号: ${item.batch_no || '-'}`"
          :value="`库存: ${item.quantity}K`"
          is-link
          @click="selectItem(item)"
        />
      </van-cell-group>
      <van-empty v-else-if="searched" description="未找到匹配的库存" />
    </div>

    <div v-else class="out-form">
      <van-cell-group title="库存信息">
        <van-cell title="物料编码" :value="selectedItem.material_code || '-'" />
        <van-cell title="厂家规格" :value="selectedItem.spec" />
        <van-cell title="生产厂家" :value="selectedItem.manufacturer || '-'" />
        <van-cell title="批号" :value="selectedItem.batch_no || '-'" />
        <van-cell title="当前库存(K)" :value="String(selectedItem.quantity)" />
        <van-cell v-if="selectedItem.note" title="备注" :value="selectedItem.note" />
      </van-cell-group>

      <van-cell-group title="出库信息">
        <van-field v-model="outQuantity" label="出库数量(K)" type="number" placeholder="请输入出库数量" />
      </van-cell-group>

      <div class="submit-bar">
        <van-button type="primary" block @click="doStockOut" :loading="submitting">确认出库</van-button>
        <van-button block @click="selectedItem = null" style="margin-top: 8px;">重新选择</van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { getInventoryList, getInventory, stockOut } from '../api'
import { parseQtyToK } from '../utils/qty'

const route = useRoute()

const searchText = ref('')
const searchResults = ref([])
const searched = ref(false)
const selectedItem = ref(null)
const outQuantity = ref('')
const submitting = ref(false)

onMounted(async () => {
  if (route.params.id) {
    try {
      selectedItem.value = await getInventory(route.params.id)
    } catch (e) {}
  }
})

async function doSearch() {
  if (!searchText.value.trim()) return
  try {
    const data = await getInventoryList(searchText.value.trim())
    searchResults.value = data.items
    searched.value = true
  } catch (e) {}
}

function selectItem(item) {
  selectedItem.value = item
  outQuantity.value = ''
}

async function doStockOut() {
  const qty = Number(outQuantity.value)
  if (!qty || qty <= 0) return showToast('请输入有效出库数量')
  const currentQty = parseQtyToK(selectedItem.value.quantity)
  if (qty > currentQty) return showToast('出库数量不能超过库存')
  submitting.value = true
  try {
    await stockOut(selectedItem.value.id, String(qty))
    showSuccessToast('出库成功')
    selectedItem.value = null
  } catch (e) {
    showToast({ message: '出库失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.search-area { padding: 0; }
.out-form { margin-top: 16px; }
.submit-bar { padding: 16px; }
</style>
