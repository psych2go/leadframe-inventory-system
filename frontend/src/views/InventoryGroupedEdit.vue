<template>
  <div class="edit-page">
    <van-nav-bar title="编辑基本信息" left-arrow @click-left="$router.back()" />

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
    </van-cell-group>

    <van-popup v-model:show="showPlatingPicker" round position="bottom">
      <van-picker :columns="platingOptions" @confirm="onPlatingConfirm" @cancel="showPlatingPicker = false" />
    </van-popup>
    <van-popup v-model:show="showSurfacePicker" round position="bottom">
      <van-picker :columns="surfaceOptions" @confirm="onSurfaceConfirm" @cancel="showSurfacePicker = false" />
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
import { updateInventoryGrouped } from '../api'

const route = useRoute()
const router = useRouter()
const submitting = ref(false)
const showPlatingPicker = ref(false)
const showSurfacePicker = ref(false)

const platingOptions = [{ text: '单环镀', value: '单环镀' }, { text: '双环镀', value: '双环镀' }, { text: '无', value: '' }]
const surfaceOptions = [{ text: 'CRC', value: 'CRC' }, { text: 'SRC', value: 'SRC' }, { text: 'ERC', value: 'ERC' }, { text: '无', value: '' }]

const oldFields = reactive({
  package_type: '', spec: '', plating_zone: '', surface_treatment: '', manufacturer: '',
})
const form = reactive({
  package_type: '', spec: '', plating_zone: '', surface_treatment: '', manufacturer: '',
})

function onPlatingConfirm({ selectedValues }) {
  form.plating_zone = selectedValues[0] || ''
  showPlatingPicker.value = false
}
function onSurfaceConfirm({ selectedValues }) {
  form.surface_treatment = selectedValues[0] || ''
  showSurfacePicker.value = false
}

onMounted(() => {
  const q = route.query
  const fields = ['package_type', 'spec', 'plating_zone', 'surface_treatment', 'manufacturer']
  fields.forEach(k => {
    oldFields[k] = q[k] || ''
    form[k] = q[k] || ''
  })
})

async function submit() {
  if (!form.package_type.trim()) return showToast('请填写封装形式')
  if (!form.spec.trim()) return showToast('请填写规格')
  submitting.value = true
  try {
    await updateInventoryGrouped(
      { ...oldFields },
      {
        package_type: form.package_type.trim(),
        spec: form.spec.trim(),
        plating_zone: form.plating_zone.trim(),
        surface_treatment: form.surface_treatment.trim(),
        manufacturer: form.manufacturer.trim(),
      },
    )
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
