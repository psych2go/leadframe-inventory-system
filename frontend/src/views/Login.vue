<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-icon">
        <van-icon name="shield-o" size="42" color="var(--lf-primary)" />
      </div>
      <div class="login-title">引线框架库存管理</div>
      <div class="login-subtitle">请输入密码登录</div>
      <van-field
        v-model="password"
        type="password"
        placeholder="请输入密码"
        :error-message="errorMsg"
        @keyup.enter="handleLogin"
      />
      <van-button
        type="primary"
        block
        :loading="loading"
        @click="handleLogin"
        class="login-btn"
      >
        登录
      </van-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { passwordLogin } from '../api'

const router = useRouter()
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')

async function handleLogin() {
  if (!password.value.trim()) {
    errorMsg.value = '请输入密码'
    return
  }
  errorMsg.value = ''
  loading.value = true
  try {
    const res = await passwordLogin(password.value)
    localStorage.setItem('token', res.token)
    localStorage.setItem('user', JSON.stringify({ user_id: res.user_id, name: res.name }))
    router.replace('/')
  } catch (e) {
    if (e.response?.status === 401) {
      errorMsg.value = '密码错误'
    } else {
      errorMsg.value = e.response?.data?.detail || '登录失败'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--lf-bg);
  padding: 24px;
}
.login-card {
  width: 100%;
  max-width: 360px;
  background: white;
  border: 1px solid var(--lf-border);
  border-top: 4px solid var(--lf-primary);
  border-radius: 8px;
  padding: 36px 24px 28px;
  box-shadow: 0 8px 24px rgba(23, 52, 59, 0.08);
  text-align: center;
}
.login-icon {
  margin-bottom: 20px;
}
.login-title {
  font-size: 19px;
  font-weight: 750;
  color: var(--lf-text);
  margin-bottom: 8px;
}
.login-subtitle {
  font-size: 14px;
  color: var(--lf-text-muted);
  margin-bottom: 28px;
}
.login-card :deep(.van-field) {
  border: 1px solid var(--lf-border);
  border-radius: 6px;
  margin-bottom: 8px;
}
.login-btn {
  margin-top: 16px;
  border-radius: 6px;
  height: 44px;
  font-size: 16px;
}
</style>
