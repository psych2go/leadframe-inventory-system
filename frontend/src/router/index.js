import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Camera from '../views/Camera.vue'
import CameraOut from '../views/CameraOut.vue'
import StockIn from '../views/StockIn.vue'
import StockOut from '../views/StockOut.vue'
import InventoryList from '../views/InventoryList.vue'
import InventoryDetail from '../views/InventoryDetail.vue'
import AuditLogs from '../views/AuditLogs.vue'

const routes = [
  { path: '/', name: 'Home', component: Home },
  { path: '/camera', name: 'Camera', component: Camera },
  { path: '/camera-out', name: 'CameraOut', component: CameraOut },
  { path: '/stock-in', name: 'StockIn', component: StockIn },
  { path: '/stock-out/:id?', name: 'StockOut', component: StockOut },
  { path: '/inventory', name: 'InventoryList', component: InventoryList },
  { path: '/inventory/:id', name: 'InventoryDetail', component: InventoryDetail },
  { path: '/audit-logs', name: 'AuditLogs', component: AuditLogs },
]

const router = createRouter({
  history: createWebHistory('/inventory/'),
  routes,
})

// 企微是否启用，启动时自动从后端配置接口获取
let wecomEnabled = false
let authRequired = false
let configLoaded = false

// 从后端获取企微配置，判断是否启用 OAuth
async function loadConfig() {
  if (configLoaded) return
  try {
    const res = await fetch(import.meta.env.BASE_URL + 'api/config')
    const data = await res.json()
    wecomEnabled = !!data.wecom_configured
    authRequired = !!data.auth_required
  } catch (e) {
    console.warn('[router] 获取后端配置失败:', e)
  }
  configLoaded = true
}

// 启动加载配置
loadConfig()

// 检查是否在企微环境中
function isWecomBrowser() {
  return /wxwork/i.test(navigator.userAgent)
}

// 路由守卫
router.beforeEach(async (to) => {
  // 确保配置已加载
  if (!configLoaded) {
    await new Promise(r => setTimeout(r, 200))
  }

  const query = new URLSearchParams(window.location.search)

  // 1. 处理后端回调重定向带来的 token 参数
  const tokenParam = query.get('token')
  const nameParam = query.get('name')
  if (tokenParam) {
    localStorage.setItem('token', tokenParam)
    if (nameParam) {
      localStorage.setItem('user', JSON.stringify({ name: decodeURIComponent(nameParam) }))
    }
    query.delete('token')
    query.delete('name')
    const clean = query.toString()
    const newPath = to.path + (clean ? '?' + clean : '')
    window.history.replaceState({}, '', newPath)
    return
  }

  // 2. 处理企微授权回调中的 code 参数
  const code = query.get('code')
  if (code && isWecomBrowser()) {
    query.delete('code')
    query.delete('state')
    const clean = query.toString()
    const nextPath = to.path + (clean ? '?' + clean : '')

    try {
      const { wecomLogin } = await import('../api')
      const res = await wecomLogin(code)
      localStorage.setItem('token', res.token)
      localStorage.setItem('user', JSON.stringify({ user_id: res.user_id, name: res.name }))
      window.history.replaceState({}, '', nextPath)
    } catch (e) {
      console.error('企微登录失败:', e)
    }
    return
  }

  // 3. 需要认证但未登录
  if (wecomEnabled && authRequired && !localStorage.getItem('token')) {
    if (isWecomBrowser()) {
      // 企微内：跳转 OAuth 授权
      try {
        const { getWecomAuthUrl } = await import('../api')
        const res = await getWecomAuthUrl(to.fullPath)
        window.location.href = res.url
        return false
      } catch (e) {
        console.error('获取授权链接失败:', e)
      }
    } else {
      // 非企微浏览器：提示用户
      const confirmed = confirm('请在企业微信中打开此应用。\n\n点击"确定"了解如何操作，点击"取消"继续浏览（部分功能受限）。')
      if (confirmed) {
        alert('请打开企业微信 → 工作台 → 找到"库存管理"应用点击进入。')
      }
    }
  }
})

export function setWecomEnabled(val) {
  wecomEnabled = val
}

export default router
