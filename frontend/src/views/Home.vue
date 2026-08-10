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
            <van-icon name="bag-o" size="22" color="white" />
          </div>
          <div class="stat-content">
            <span class="stat-value">{{ totalItems }}</span>
            <span class="stat-label">库存种类</span>
          </div>
        </div>
        <div class="stat-card stat-alert" v-if="alertItems.length">
          <div class="stat-icon">
            <van-icon name="warning-o" size="22" color="white" />
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
            <van-icon name="photograph" size="24" color="white" />
          </div>
          <span class="action-text">拍照出库</span>
          <span class="action-desc">扫描标签快速出库</span>
        </div>
        <div class="action-card action-in" @click="$router.push('/camera')">
          <div class="action-icon">
            <van-icon name="photograph" size="24" color="white" />
          </div>
          <span class="action-text">拍照入库</span>
          <span class="action-desc">扫描标签快速入库</span>
        </div>
        <div class="action-card action-export" @click="$router.push('/inventory')">
          <div class="action-icon">
            <van-icon name="description" size="24" color="white" />
          </div>
          <span class="action-text">库存查询</span>
          <span class="action-desc">查看库存明细</span>
        </div>
        <div class="action-card action-logs" @click="showLogs = true">
          <div class="action-icon">
            <van-icon name="notes-o" size="24" color="white" />
          </div>
          <span class="action-text">出入库记录</span>
          <span class="action-desc">查看历史记录</span>
        </div>
      </div>
    </div>

    <!-- 库存预警 -->
    <div class="alert-section" v-if="alertItems.length">
      <div class="section-title-bar alert-title-bar">
        <van-icon name="warning-o" color="var(--lf-out)" size="18" />
        <span class="section-title-text alert-text">库存预警</span>
        <span class="alert-count">{{ alertItems.length }} 项低于 {{ threshold }}K</span>
        <van-icon
          :name="alertExpanded ? 'arrow-up' : 'arrow-down'"
          size="16"
          color="var(--lf-text-muted)"
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
            <van-icon name="arrow" size="12" color="var(--lf-out)" />
          </div>
        </div>
        <div
          class="alert-item alert-more"
          v-if="alertItems.length > 5"
          @click="$router.push('/inventory?alert=1')"
        >
          <span>查看更多低库存项...</span>
          <van-icon name="arrow" size="12" color="var(--lf-text-muted)" />
        </div>
      </div>
    </div>

    <!-- 出入库记录弹窗 -->
    <van-popup v-model:show="showLogs" position="bottom" :style="{ height: '70%' }" round>
      <div class="logs-popup">
        <div class="logs-header">
          <span class="logs-title">出入库记录</span>
          <van-icon name="cross" size="20" color="var(--lf-text-muted)" @click="showLogs = false" class="logs-close" />
        </div>
        <div class="logs-list">
          <van-swipe-cell v-for="log in stockLogs" :key="log.id">
            <div class="log-item">
              <div class="log-icon">
                <van-icon
                  :name="log.type === 'in' ? 'down' : 'upgrade'"
                  :color="log.type === 'in' ? 'var(--lf-in)' : 'var(--lf-out)'"
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
      confirmButtonColor: '#f05b68',
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
  padding-bottom: 48px;
  background: var(--lf-bg);
  min-height: 100vh;
}

.home :deep(.van-nav-bar) {
  background: var(--lf-primary-dark);
  border-bottom-color: var(--lf-primary-dark);
}
.home :deep(.van-nav-bar__title) {
  color: white;
  font-size: 16px;
  font-weight: 700;
}
.nav-right {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
}
.nav-right-text {
  font-size: 12px;
  font-weight: 600;
  color: white;
}

.stats-section {
  padding: 16px 16px 0;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}
.stat-card {
  display: flex;
  align-items: center;
  min-height: 86px;
  padding: 14px;
  background: var(--lf-primary-soft);
  border: 1px solid var(--lf-border);
  border-radius: 8px;
}
.stat-card.stat-total {
  border-color: #a9dcf4;
}
.stat-card.stat-alert {
  background: var(--lf-out-soft);
  border-color: #ffc4cb;
}
.stat-icon {
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--lf-primary);
  border-radius: 6px;
  margin-right: 10px;
}
.stat-card.stat-alert .stat-icon {
  background: var(--lf-out);
}
.stat-content {
  display: flex;
  flex-direction: column;
}
.stat-value {
  font-family: var(--lf-data-font);
  font-size: 22px;
  font-weight: 750;
  color: var(--lf-text);
}
.stat-label {
  font-size: 11px;
  color: var(--lf-text-muted);
  margin-top: 2px;
}

.actions-section {
  padding: 22px 16px 0;
}
.section-title-bar {
  display: flex;
  align-items: center;
  padding: 0 0 10px;
}
.section-title-text {
  font-size: 13px;
  font-weight: 750;
  color: var(--lf-text);
}
.actions-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.action-card {
  display: grid;
  grid-template-columns: 42px 1fr;
  grid-template-rows: auto auto;
  column-gap: 10px;
  align-items: center;
  min-height: 84px;
  padding: 12px;
  background: white;
  border: 1px solid var(--lf-border);
  border-radius: 8px;
  transition: border-color 0.16s, transform 0.16s;
  cursor: pointer;
}
.action-card:active {
  transform: translateY(1px);
}
.action-icon {
  grid-row: 1 / 3;
  width: 42px;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--lf-primary);
}
.action-out {
  border-color: #ffc4cb;
  background: var(--lf-out-soft);
}
.action-out .action-icon { background: var(--lf-out); }
.action-in {
  border-color: #a9e8c8;
  background: var(--lf-in-soft);
}
.action-in .action-icon { background: var(--lf-in); }
.action-export {
  border-color: #a9dcf4;
  background: var(--lf-primary-soft);
}
.action-export .action-icon { background: var(--lf-primary); }
.action-logs {
  border-color: #ffdda0;
  background: var(--lf-warning-soft);
}
.action-logs .action-icon { background: var(--lf-warning); }
.action-text {
  align-self: end;
  font-size: 13px;
  font-weight: 700;
  color: var(--lf-text);
}
.action-desc {
  align-self: start;
  margin-top: 2px;
  font-size: 10px;
  color: var(--lf-text-muted);
}

.alert-section {
  padding: 22px 16px 0;
}
.alert-title-bar {
  background: var(--lf-out-soft);
  padding: 11px 14px;
  border: 1px solid #ffc4cb;
  border-radius: 8px 8px 0 0;
  display: flex;
  align-items: center;
}
.alert-text {
  color: var(--lf-out);
  margin-left: 6px;
}
.alert-count {
  font-size: 11px;
  color: var(--lf-out);
  margin-left: auto;
  margin-right: 8px;
}
.alert-toggle {
  cursor: pointer;
}
.alert-list {
  background: white;
  border: 1px solid #ffc4cb;
  border-top: 0;
  border-radius: 0 0 8px 8px;
}
.alert-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--lf-border);
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
  font-weight: 650;
  color: var(--lf-text);
}
.alert-item-info {
  font-size: 11px;
  color: var(--lf-text-muted);
  margin-top: 4px;
}
.alert-item-qty {
  display: flex;
  align-items: center;
  gap: 8px;
}
.alert-qty-value {
  font-family: var(--lf-data-font);
  font-size: 15px;
  font-weight: 750;
  color: var(--lf-out);
}
.alert-more {
  justify-content: center;
  color: var(--lf-text-muted);
  font-size: 12px;
}

.logs-popup {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--lf-bg);
}
.logs-header {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: white;
  border-bottom: 1px solid var(--lf-border);
  position: relative;
}
.logs-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--lf-text);
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
  padding: 12px 14px;
  background: white;
  border: 1px solid var(--lf-border);
  border-radius: 8px;
  margin-bottom: 8px;
}
.log-icon {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  margin-right: 12px;
  background: var(--lf-primary-soft);
}
.log-main {
  display: flex;
  flex-direction: column;
  flex: 1;
}
.log-title {
  font-size: 14px;
  font-weight: 650;
  color: var(--lf-text);
}
.log-time {
  font-family: var(--lf-data-font);
  font-size: 11px;
  color: var(--lf-text-muted);
  margin-top: 4px;
}
.log-qty {
  font-family: var(--lf-data-font);
  font-size: 15px;
  font-weight: 750;
}
.log-delete-btn {
  height: 100%;
}
.text-green {
  color: var(--lf-in);
}
.text-red {
  color: var(--lf-out);
}

.home :deep(.van-empty) {
  padding: 80px 0;
}

@media (max-width: 360px) {
  .actions-grid {
    grid-template-columns: 1fr;
  }
}
</style>
