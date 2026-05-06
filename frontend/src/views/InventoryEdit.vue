<template>
  <div class="edit-page">
    <van-nav-bar title="编辑库存" left-arrow @click-left="$router.back()" />

    <van-cell-group>
      <van-field v-model="form.material_code" label="物料编码" placeholder="请输入物料编码" required />
      <van-field v-model="form.spec" label="厂家规格" placeholder="请输入厂家规格" required />
      <van-field v-model="form.manufacturer" label="生产厂家" placeholder="请输入厂家" />
      <van-field v-model="form.batch_no" label="批号" placeholder="请输入批号" />
      <van-field v-model="form.production_date" label="生产日期" placeholder="YYYY-MM-DD" />
      <van-field v-model="form.expiry_date" label="有效日期" placeholder="YYYY-MM-DD" />
    </van-cell-group>

    <div class="submit-bar">
      <van-button type="primary" block size="large" @click="submit" :loading="submitting">
        保存修改
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { getInventory, updateInventory } from '../api'

const route = useRoute()
const router = useRouter()
const submitting = ref(false)
const form = reactive({
  material_code: '', spec: '', manufacturer: '', batch_no: '',
  production_date: '', expiry_date: '',
})

onMounted(async () => {
  try {
    const item = await getInventory(route.params.id)
    form.material_code = item.material_code || ''
    form.spec = item.spec || ''
    form.manufacturer = item.manufacturer || ''
    form.batch_no = item.batch_no || ''
    form.production_date = item.production_date || ''
    form.expiry_date = item.expiry_date || ''
  } catch (e) {
    showToast('获取信息失败')
  }
})

async function submit() {
  if (!form.material_code.trim()) return showToast('请填写物料编码')
  if (!form.spec.trim()) return showToast('请填写厂家规格')
  submitting.value = true
  try {
    await updateInventory(route.params.id, {
      material_code: form.material_code.trim(),
      spec: form.spec.trim(),
      manufacturer: form.manufacturer.trim(),
      batch_no: form.batch_no.trim(),
      production_date: form.production_date.trim(),
      expiry_date: form.expiry_date.trim(),
    })
    showSuccessToast('保存成功')
    router.back()
  } catch (e) {
    showToast({ message: '保存失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.submit-bar { padding: 16px; }
</style>
