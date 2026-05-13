<template>
  <div class="detail-page">
    <van-nav-bar title="库存详情" left-arrow @click-left="$router.back()">
      <template #right>
        <van-icon name="edit" size="18" @click="$router.push(`/inventory/${item.id}/edit`)" />
      </template>
    </van-nav-bar>

    <van-cell-group title="基本信息">
      <van-cell title="封装形式" :value="item.package_type || '-'" />
      <van-cell title="规格" :value="item.spec || '-'" />
      <van-cell title="镀银区域" :value="item.plating_zone || '-'" />
      <van-cell title="表面粗化处理" :value="item.surface_treatment || '-'" />
      <van-cell title="生产厂家" :value="item.manufacturer || '-'" />
      <van-cell title="批号" :value="item.batch_no || '-'" />
    </van-cell-group>

    <van-cell-group title="数量信息">
      <van-cell title="数量(K)" :value="`${item.quantity}K`" />
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
import { ref, onMounted, watch } from 'vue'
import { useRoute, useRouter, onBeforeRouteUpdate } from 'vue-router'
import { showToast } from 'vant'
import { getInventory } from '../api'

const route = useRoute()
const router = useRouter()
const item = ref({})

async function loadData(id) {
  try {
    item.value = await getInventory(id)
  } catch (e) {
    if (e.response?.status === 404) {
      showToast('该记录已被合并或删除')
      router.replace('/inventory')
    } else {
      showToast('获取详情失败')
    }
  }
}

onMounted(() => loadData(route.params.id))

// 路由参数变化时（不同 id）
watch(() => route.params.id, (id) => { if (id) loadData(id) })

// 同 id 从编辑页返回时（router.replace 同一路由），onBeforeRouteUpdate 捕获
onBeforeRouteUpdate((to) => {
  if (to.params.id) loadData(to.params.id)
})
</script>

<style scoped>
.detail-page { padding-bottom: 20px; }
.actions { padding: 16px; }
</style>
