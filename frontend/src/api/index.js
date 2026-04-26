import axios from 'axios'
import { showToast } from 'vant'

const api = axios.create({
  baseURL: import.meta.env.BASE_URL + 'api',
  timeout: 60000,
})

// 请求拦截：自动附加 JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 响应拦截：401 时清除登录态并跳转授权
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      showToast('登录已过期，请重新登录')
      // 让路由守卫处理跳转
      window.location.reload()
    }
    return Promise.reject(err)
  }
)

// ── 认证相关 ──

export async function getWecomAuthUrl(redirect = '/') {
  const { data } = await api.get('/auth/wecom/url', { params: { redirect } })
  return data
}

export async function wecomLogin(code) {
  const { data } = await api.post('/auth/wecom/login', { code })
  return data
}

export async function getAuthMe() {
  const { data } = await api.get('/auth/me')
  return data
}

export async function passwordLogin(password) {
  const { data } = await api.post('/auth/login', { password })
  return data
}

export async function getJsapiConfig(url) {
  const { data } = await api.get('/auth/wecom/jsapi-config', { params: { url } })
  return data
}

// ── 业务接口 ──

export async function ocrRecognize(file) {
  const formData = new FormData()
  formData.append('file', file)
  const { data } = await api.post('/ocr', formData)
  return data
}

export async function getInventoryList(search = '', page = 1) {
  const { data } = await api.get('/inventory', { params: { search, page } })
  return data
}

export async function getInventory(id) {
  const { data } = await api.get(`/inventory/${id}`)
  return data
}

export async function stockIn(item) {
  const { data } = await api.post('/stock-in', item)
  return data
}

export async function stockOut(inventoryId, quantity, note = '') {
  const { data } = await api.post('/stock-out', { inventory_id: inventoryId, quantity, note })
  return data
}

export async function updateInventory(id, updates) {
  const { data } = await api.put(`/inventory/${id}`, updates)
  return data
}

export async function deleteInventory(id) {
  const { data } = await api.delete(`/inventory/${id}`)
  return data
}

export async function getStockLogs(inventoryId = null, page = 1) {
  const { data } = await api.get('/stock-logs', { params: { inventory_id: inventoryId, page } })
  return data
}

export async function getMaterialCodeSuggest(spec) {
  const { data } = await api.get('/material-code-suggest', { params: { spec } })
  return data
}

export async function getInventoryAlerts() {
  const { data } = await api.get('/inventory/alerts')
  return data
}

export async function getAuditLogs(params = {}) {
  const { data } = await api.get('/audit-logs', { params })
  return data
}

export async function exportInventory(search = '') {
  const response = await api.get('/inventory/export', {
    params: search ? { search } : {},
    responseType: 'blob',
  })
  const url = window.URL.createObjectURL(new Blob([response.data]))
  const link = document.createElement('a')
  link.href = url
  const disposition = response.headers['content-disposition']
  const filename = disposition
    ? disposition.match(/filename=(.+)/)?.[1]
    : 'inventory.xlsx'
  link.setAttribute('download', filename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}
