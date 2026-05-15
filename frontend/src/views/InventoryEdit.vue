<template>
  <div class="edit-page">
    <van-nav-bar title="编辑库存" left-arrow @click-left="$router.back()" />

    <van-cell-group>
      <van-field v-model="form.package_type" label="封装形式" placeholder="如 SOP、QFP、DIP" required />
      <van-field v-model="form.spec" label="规格" placeholder="请输入规格" required />
      <van-field
        v-model="form.plating_zone"
        is-link
        readonly
        label="镀银区域"
        placeholder="请选择"
        @click="showPlatingPicker = true"
      />
      <van-field
        v-model="form.surface_treatment"
        is-link
        readonly
        label="表面粗化处理"
        placeholder="请选择"
        @click="showSurfacePicker = true"
      />
      <van-field v-model="form.manufacturer" label="生产厂家" placeholder="请输入厂家" />
      <van-field v-model="form.batch_no" label="批号" placeholder="请输入批号" />
      <van-field v-model="form.production_date" label="生产日期" placeholder="YYYY-MM-DD" />
      <van-field v-model="form.expiry_date" label="有效日期" placeholder="YYYY-MM-DD" />
    </van-cell-group>

    <van-popup v-model:show="showPlatingPicker" round position="bottom">
      <van-picker
        :columns="platingOptions"
        @confirm="onPlatingConfirm"
        @cancel="showPlatingPicker = false"
      />
    </van-popup>
    <van-popup v-model:show="showSurfacePicker" round position="bottom">
      <van-picker
        :columns="surfaceOptions"
        @confirm="onSurfaceConfirm"
        @cancel="showSurfacePicker = false"
      />
    </van-popup>

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
const showPlatingPicker = ref(false)
const showSurfacePicker = ref(false)

const platingOptions = [{ text: '单环镀', value: '单环镀' }, { text: '双环镀', value: '双环镀' }, { text: '无', value: '' }]
const surfaceOptions = [{ text: 'CRC', value: 'CRC' }, { text: 'SRC', value: 'SRC' }, { text: 'ERC', value: 'ERC' }, { text: '无', value: '' }]

const form = reactive({
  package_type: '', spec: '', plating_zone: '', surface_treatment: '',
  manufacturer: '', batch_no: '', production_date: '', expiry_date: '',
})

function onPlatingConfirm({ selectedValues }) {
  form.plating_zone = selectedValues[0] || ''
  showPlatingPicker.value = false
}
function onSurfaceConfirm({ selectedValues }) {
  form.surface_treatment = selectedValues[0] || ''
  showSurfacePicker.value = false
}

onMounted(async () => {
  try {
    const item = await getInventory(route.params.id)
    form.package_type = item.package_type || ''
    form.spec = item.spec || ''
    form.plating_zone = item.plating_zone || ''
    form.surface_treatment = item.surface_treatment || ''
    form.manufacturer = item.manufacturer || ''
    form.batch_no = item.batch_no || ''
    form.production_date = item.production_date || ''
    form.expiry_date = item.expiry_date || ''
  } catch (e) {
    showToast('获取信息失败')
  }
})

async function submit() {
  if (!form.package_type.trim()) return showToast('请填写封装形式')
  if (!form.spec.trim()) return showToast('请填写厂家规格')
  submitting.value = true
  try {
    const res = await updateInventory(route.params.id, {
      package_type: form.package_type.trim(),
      spec: form.spec.trim(),
      plating_zone: form.plating_zone.trim(),
      surface_treatment: form.surface_treatment.trim(),
      manufacturer: form.manufacturer.trim(),
      batch_no: form.batch_no.trim(),
      production_date: form.production_date.trim(),
      expiry_date: form.expiry_date.trim(),
    })
    showSuccessToast('保存成功')
    router.replace('/inventory')
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
