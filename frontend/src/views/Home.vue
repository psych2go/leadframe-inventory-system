<template>
  <div class="home">
    <van-nav-bar title="引线框架库存管理" fixed placeholder>
      <template #right>
        <div class="nav-right" @click="$router.push('/audit-logs')">
          <van-icon name="shield-o" size="18" color="white" />
          <span class="nav-right-text">操作记录</span>
        </div>
      </template>
    </van-nav-bar>

    <!-- 统计卡片 -->
    <div class="stats-section">
      <div class="stats-grid">
        <div class="stat-card stat-total">
          <div class="stat-icon">
            <van-icon name="bag-o" size="24" color="#1989fa" />
          </div>
          <div class="stat-content">
            <span class="stat-value">{{ totalItems }}</span>
            <span class="stat-label">库存种类</span>
          </div>
        </div>
        <div class="stat-card stat-alert" v-if="alertItems.length">
          <div class="stat-icon">
            <van-icon name="warning-o" size="24" color="#ee0a24" />
          </div>
          <div class="stat-content">
            <span class="stat-value">{{ alertItems.length }}</span>
            <span class="stat-label">库存预警</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 功能按钮 -->
    <div class="actions-section">
      <div class="section-title-bar">
        <span class="section-title-text">快捷操作</span>
      </div>
      <div class="actions-grid">
        <div class="action-card action-out" @click="$router.push('/camera-out')">
          <div class="action-icon">
            <van-icon name="photograph" size="28" color="#ee0a24" />
          </div>
          <span class="action-text">拍照出库</span>
          <span class="action-desc">扫描标签快速出库</span>
        </div>
        <div class="action-card action-in" @click="$router.push('/camera')">
          <div class="action-icon">
            <van-icon name="photograph" size="28" color="#07c160" />
          </div>
          <span class="action-text">拍照入库</span>
          <span class="action-desc">扫描标签快速入库</span>
        </div>
        <div class="action-card action-export" @click="$router.push('/inventory')">
          <div class="action-icon">
            <van-icon name="description" size="28" color="#1989fa" />
          </div>
          <span class="action-text">库存查询</span>
          <span class="action-desc">查看库存明细</span>
        </div>
        <div class="action-card action-logs" @click="showLogs = true">
          <div class="action-icon">
            <van-icon name="notes-o" size="28" color="#ff976a" />
          </div>
          <span class="action-text">出入库记录</span>
          <span class="action-desc">查看历史记录</span>
        </div>
      </div>
    </div>

    <!-- 库存预警 -->
    <div class="alert-section" v-if="alertItems.length">
      <div class="section-title-bar alert-title-bar">
        <van-icon name="warning-o" color="#ee0a24" size="18" />
        <span class="section-title-text alert-text">库存预警</span>
        <span class="alert-count">{{ alertItems.length }} 项低于 {{ threshold }}K</span>
        <van-icon
          :name="alertExpanded ? 'arrow-up' : 'arrow-down'"
          size="16"
          color="#999"
          class="alert-toggle"
          @click="alertExpanded = !alertExpanded"
        />
      </div>
      <div class="alert-list" v-if="alertExpanded">
        <div
          class="alert-item"
          v-for="(item, idx) in alertItems.slice(0, 5)"
          :key="'alert-'+idx"
          @click="goAlertDetail(item)"
        >
          <div class="alert-item-main">
            <span class="alert-item-title">{{ [item.package_type, item.spec, item.plating_zone, item.surface_treatment].filter(Boolean).join('-') || '-' }}</span>
            <span class="alert-item-info">{{ item.manufacturer || '-' }}</span>
          </div>
          <div class="alert-item-qty">
            <span class="alert-qty-value">{{ item.total_quantity }}K</span>
            <van-icon name="arrow" size="12" color="#ee0a24" />
          </div>
        </div>
        <div
          class="alert-item alert-more"
          v-if="alertItems.length > 5"
          @click="$router.push('/inventory?alert=1')"
        >
          <span>查看更多低库存项...</span>
          <van-icon name="arrow" size="12" color="#999" />
        </div>
      </div>
    </div>

    <!-- 出入库记录弹窗 -->
    <van-popup v-model:show="showLogs" position="bottom" :style="{ height: '70%' }" round>
      <div class="logs-popup">
        <div class="logs-header">
          <span class="logs-title">出入库记录</span>
          <van-icon name="cross" size="20" color="#999" @click="showLogs = false" class="logs-close" />
        </div>
        <div class="logs-list">
          <van-swipe-cell v-for="log in stockLogs" :key="log.id">
            <div class="log-item">
              <div class="log-icon">
                <van-icon
                  :name="log.type === 'in' ? 'down' : 'upgrade'"
                  :color="log.type === 'in' ? '#07c160' : '#ee0a24'"
                  size="22"
                />
              </div>
              <div class="log-main">
                <span class="log-title">{{ [log.package_type, log.spec, log.plating_zone, log.surface_treatment].filter(Boolean).join('-') || '-' }}</span>
                <span class="log-time">{{ log.created_at }}</span>
              </div>
              <div class="log-qty" :class="log.type === 'in' ? 'text-green' : 'text-red'">
                {{ log.type === 'in' ? '+' : '-' }}{{ log.quantity }}K
              </div>
            </div>
            <template #right>
              <van-button square type="danger" text="删除" class="log-delete-btn" @click="onDeleteLog(log)" />
            </template>
          </van-swipe-cell>
          <van-empty v-if="!stockLogs.length" description="暂无记录" image="default" />
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { useRouter, onBeforeRouteUpdate } from 'vue-router'
import { getInventoryGrouped, getStockLogs, getInventoryAlerts, deleteStockLog } from '../api'
import { isLowStock } from '../utils/qty'
import { showConfirmDialog, showSuccessToast, showToast } from 'vant'

const router = useRouter()

const stockLogs = ref([])
const showLogs = ref(false)
const alertItems = ref([])
const threshold = ref(2)
const alertExpanded = ref(true)
const totalItems = ref(0)

onMounted(loadInitData)
onBeforeRouteUpdate(loadInitData)

async function loadInitData() {
  try {
    const data = await getInventoryGrouped('', 1, 1)
    totalItems.value = data.total
  } catch (e) {}
  loadLogs()
  loadAlerts()
}

async function loadLogs() {
  try {
    const data = await getStockLogs(null, 1, 50)
    stockLogs.value = data.items
  } catch (e) {}
}

async function loadAlerts() {
  try {
    const data = await getInventoryAlerts()
    alertItems.value = data.items
    threshold.value = data.threshold
  } catch (e) {}
}

function goAlertDetail(item) {
  router.push({
    name: 'InventoryGroupedDetail',
    query: {
      package_type: item.package_type || '',
      spec: item.spec || '',
      plating_zone: item.plating_zone || '',
      surface_treatment: item.surface_treatment || '',
      manufacturer: item.manufacturer || '',
    },
  })
}

async function onDeleteLog(log) {
  const actionText = log.type === 'in' ? '入库' : '出库'
  try {
    await showConfirmDialog({
      title: '确认删除',
      message: `确定要撤销这条${actionText}记录吗？将${log.type === 'in' ? '从库存中扣减' : '归还到库存'} ${log.quantity}K。`,
      confirmButtonColor: '#ee0a24',
    })
  } catch {
    return
  }
  try {
    await deleteStockLog(log.id)
    showSuccessToast('删除成功')
    stockLogs.value = stockLogs.value.filter(l => l.id !== log.id)
    // 刷新统计
    const invData = await getInventoryGrouped('', 1, 1)
    totalItems.value = invData.total
    loadAlerts()
  } catch (e) {
    showToast(e.response?.data?.detail || '删除失败')
  }
}
</script>

<style scoped>
.home {
  padding-bottom: 80px;
  background: linear-gradient(180deg, #f0f5ff 0%, #f7f8fa 100%);
  min-height: 100vh;
}

/* 导航栏 */
.home :deep(.van-nav-bar) {
  background: linear-gradient(135deg, #4a90e2 0%, #1989fa 100%);
}
.home :deep(.van-nav-bar__title) {
  color: white;
  font-size: 18px;
  font-weight: 600;
}
.nav-right {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.nav-right-text {
  font-size: 13px;
  color: white;
}

/* 统计卡片 */
.stats-section {
  padding: 16px 16px 0;
}
.stats-grid {
  display: flex;
  gap: 12px;
}
.stat-card {
  flex: 1;
  display: flex;
  align-items: center;
  padding: 16px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.stat-icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f0f5ff;
  border-radius: 12px;
  margin-right: 12px;
}
.stat-card.stat-alert .stat-icon {
  background: #fff1f0;
}
.stat-content {
  display: flex;
  flex-direction: column;
}
.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: #333;
}
.stat-label {
  font-size: 12px;
  color: #999;
  margin-top: 2px;
}

/* 功能按钮 */
.actions-section {
  padding: 16px 16px 0;
}
.section-title-bar {
  display: flex;
  align-items: center;
  padding: 0 0 12px;
}
.section-title-text {
  font-size: 15px;
  font-weight: 600;
  color: #333;
}
.actions-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
}
.action-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 16px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  transition: all 0.3s ease;
  cursor: pointer;
}
.action-card:active {
  transform: scale(0.96);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
}
.action-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 16px;
  margin-bottom: 12px;
}
.action-out .action-icon {
  background: linear-gradient(135deg, #fff1f0 0%, #ffebe8 100%);
}
.action-in .action-icon {
  background: linear-gradient(135deg, #e8f5e9 0%, #d4edda 100%);
}
.action-export .action-icon {
  background: linear-gradient(135deg, #f0f5ff 0%, #e3f2fd 100%);
}
.action-logs .action-icon {
  background: linear-gradient(135deg, #fff7e6 0%, #ffe8cc 100%);
}
.action-text {
  font-size: 15px;
  font-weight: 600;
  color: #333;
  margin-bottom: 4px;
}
.action-desc {
  font-size: 12px;
  color: #999;
}

/* 库存预警 */
.alert-section {
  padding: 16px 16px 0;
}
.alert-title-bar {
  background: linear-gradient(135deg, #fff1f0 0%, #ffebe8 100%);
  padding: 12px 16px;
  border-radius: 12px 12px 0 0;
  display: flex;
  align-items: center;
}
.alert-text {
  color: #ee0a24;
  margin-left: 6px;
}
.alert-count {
  font-size: 13px;
  color: #ee0a24;
  margin-left: auto;
  margin-right: 8px;
}
.alert-toggle {
  cursor: pointer;
}
.alert-list {
  background: white;
  border-radius: 0 0 12px 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.alert-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #f5f5f5;
  cursor: pointer;
}
.alert-item:last-child {
  border-bottom: none;
}
.alert-item-main {
  display: flex;
  flex-direction: column;
}
.alert-item-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
}
.alert-item-info {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.alert-item-qty {
  display: flex;
  align-items: center;
  gap: 8px;
}
.alert-qty-value {
  font-size: 16px;
  font-weight: 700;
  color: #ee0a24;
}
.alert-more {
  justify-content: center;
  color: #999;
  font-size: 13px;
}

/* 出入库记录弹窗 */
.logs-popup {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f7f8fa;
}
.logs-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: white;
  border-bottom: 1px solid #eee;
  position: relative;
}
.logs-title {
  font-size: 16px;
  font-weight: 600;
  color: #333;
}
.logs-close {
  position: absolute;
  right: 16px;
  cursor: pointer;
}
.logs-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}
.log-item {
  display: flex;
  align-items: center;
  padding: 14px 16px;
  background: white;
  border-radius: 12px;
  margin-bottom: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}
.log-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  margin-right: 12px;
  background: #f7f8fa;
}
.log-main {
  display: flex;
  flex-direction: column;
  flex: 1;
}
.log-title {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}
.log-time {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}
.log-qty {
  font-size: 16px;
  font-weight: 700;
}
.log-delete-btn {
  height: 100%;
}
.text-green {
  color: #07c160;
}
.text-red {
  color: #ee0a24;
}

/* 空状态 */
.home :deep(.van-empty) {
  padding: 80px 0;
}
</style>