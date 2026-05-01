<template>
  <div class="stock-in-page">
    <van-nav-bar title="手动入库" left-arrow @click-left="$router.back()" />

    <van-cell-group>
      <van-field v-model="form.material_code" label="物料编码" placeholder="请输入物料编码" required />
      <van-field v-model="form.spec" label="厂家规格" placeholder="请输入厂家规格" required />
      <van-field v-model="form.batch_no" label="批号" placeholder="请输入批号" />
      <van-field v-model="form.quantity" label="数量(K)" type="number" placeholder="请输入数量" required />
      <van-field v-model="form.manufacturer" label="生产厂家" placeholder="请输入厂家" />
      <van-field v-model="form.note" label="备注" placeholder="备注" />
      <van-field v-model="form.production_date" label="生产日期" placeholder="YYYY-MM-DD" />
      <van-field v-model="form.expiry_date" label="有效日期" placeholder="YYYY-MM-DD" />
    </van-cell-group>

    <div class="submit-bar">
      <van-button type="primary" block size="large" @click="submit" :loading="submitting">
        确认入库
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import { stockIn } from '../api'

const router = useRouter()
const submitting = ref(false)
const form = reactive({
  material_code: '', spec: '', manufacturer: '', batch_no: '',
  quantity: '', note: '', production_date: '', expiry_date: '',
})

async function submit() {
  if (!form.material_code.trim()) return showToast('请填写物料编码')
  if (!form.spec.trim()) return showToast('请填写厂家规格')
  if (!form.quantity || Number(form.quantity) <= 0) return showToast('请填写有效数量')
  submitting.value = true
  try {
    await stockIn({
      material_code: form.material_code.trim(),
      spec: form.spec.trim(),
      manufacturer: form.manufacturer.trim(),
      batch_no: form.batch_no.trim(),
      quantity: form.quantity.trim(),
      note: form.note.trim(),
      production_date: form.production_date.trim(),
      expiry_date: form.expiry_date.trim(),
    })
    showSuccessToast('入库成功')
    router.push('/')
  } catch (e) {
    showToast({ message: '入库失败: ' + (e.response?.data?.detail || e.message), position: 'bottom' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.submit-bar { padding: 16px; }
</style>
