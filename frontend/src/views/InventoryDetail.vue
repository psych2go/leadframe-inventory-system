<template>
  <div class="detail-page">
    <van-nav-bar title="库存详情" left-arrow @click-left="$router.back()" />

    <van-cell-group title="基本信息">
      <van-cell title="物料编码" :value="item.material_code || '-'" />
      <van-cell title="厂家规格" :value="item.spec" />
      <van-cell title="生产厂家" :value="item.manufacturer || '-'" />
      <van-cell title="批号" :value="item.batch_no || '-'" />
    </van-cell-group>

    <van-cell-group title="数量信息">
      <van-cell title="数量(K)" :value="String(item.quantity)" />
    </van-cell-group>

    <van-cell-group title="日期信息">
      <van-cell title="生产日期" :value="item.production_date || '-'" />
      <van-cell title="有效日期" :value="item.expiry_date || '-'" />
    </van-cell-group>

    <van-cell-group v-if="item.note" title="备注">
      <van-cell :value="item.note" />
    </van-cell-group>

    <van-cell-group title="其他信息">
      <van-cell title="入库时间" :value="item.created_at || '-'" />
      <van-cell title="更新时间" :value="item.updated_at || '-'" />
    </van-cell-group>

    <div class="actions">
      <van-button type="primary" block @click="$router.push(`/stock-out/${item.id}`)">出库</van-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { showToast } from 'vant'
import { getInventory } from '../api'

const route = useRoute()
const item = ref({})

onMounted(async () => {
  try {
    item.value = await getInventory(route.params.id)
  } catch (e) {
    showToast('获取详情失败')
  }
})
</script>

<style scoped>
.detail-page { padding-bottom: 20px; }
.actions { padding: 16px; }
</style>
