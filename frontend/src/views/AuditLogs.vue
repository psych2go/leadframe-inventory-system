<template>
  <div class="audit-page">
    <van-nav-bar title="操作记录" left-arrow @click-left="$router.back()" />

    <div class="filter-bar">
      <van-dropdown-menu>
        <van-dropdown-item v-model="filterAction" :options="actionOptions" @change="loadData" />
      </van-dropdown-menu>
    </div>

    <van-pull-refresh v-model="refreshing" @refresh="loadData">
      <van-list v-model:loading="loading" :finished="finished" @load="loadMore">
        <div class="audit-item" v-for="item in items" :key="item.id">
          <div class="audit-header">
            <span class="audit-action" :class="'action-' + item.action">{{ actionLabel(item.action) }}</span>
            <span class="audit-time">{{ formatTime(item.created_at) }}</span>
          </div>
          <div class="audit-body">
            <div class="audit-user">
              <van-icon name="user-o" size="14" color="#999" />
              <span>{{ item.user_name || item.user_id || '未知用户' }}</span>
            </div>
            <div class="audit-detail" v-if="item.detail">{{ item.detail }}</div>
            <div class="audit-changes" v-if="item.changes">
              <div v-for="(change, field) in parseChanges(item.changes)" :key="field" class="change-row">
                <span class="change-field">{{ field }}</span>
                <span class="change-old">{{ change.old || '-' }}</span>
                <van-icon name="arrow" size="12" color="#999" />
                <span class="change-new">{{ change.new || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
      </van-list>
      <van-empty v-if="!loading && !items.length" description="暂无审计记录" />
    </van-pull-refresh>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { getAuditLogs } from '../api'

const items = ref([])
const loading = ref(false)
const finished = ref(false)
const refreshing = ref(false)
const filterAction = ref('')
let page = 1

const actionOptions = [
  { text: '全部操作', value: '' },
  { text: '入库', value: 'stock_in' },
  { text: '出库', value: 'stock_out' },
  { text: '编辑', value: 'update' },
  { text: '删除', value: 'delete' },
]

function actionLabel(action) {
  const map = { stock_in: '入库', stock_out: '出库', update: '编辑', delete: '删除' }
  return map[action] || action
}

function formatTime(ts) {
  if (!ts) return ''
  return ts.replace('T', ' ').substring(0, 19)
}

function parseChanges(json) {
  try {
    return JSON.parse(json)
  } catch {
    return {}
  }
}

async function loadData() {
  page = 1
  finished.value = false
  items.value = []
  await loadMore()
}

async function loadMore() {
  try {
    const params = { page }
    if (filterAction.value) params.action = filterAction.value
    const data = await getAuditLogs(params)
    if (page === 1) {
      items.value = data.items
    } else {
      items.value.push(...data.items)
    }
    loading.value = false
    refreshing.value = false
    if (items.value.length >= data.total) {
      finished.value = true
    } else {
      page++
    }
  } catch (e) {
    loading.value = false
    refreshing.value = false
  }
}
</script>

<style scoped>
.audit-page {
  background: #f7f8fa;
  min-height: 100vh;
  padding-bottom: 20px;
}
.filter-bar {
  padding: 8px 12px;
}
.filter-bar :deep(.van-dropdown-menu) {
  border-radius: 8px;
  overflow: hidden;
}
.audit-item {
  margin: 8px 12px;
  padding: 12px 16px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
}
.audit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.audit-action {
  font-size: 13px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 4px;
  color: white;
}
.action-stock_in { background: #07c160; }
.action-stock_out { background: #ee0a24; }
.action-update { background: #1989fa; }
.action-delete { background: #999; }
.audit-time {
  font-size: 12px;
  color: #999;
}
.audit-body {
  font-size: 13px;
  color: #333;
}
.audit-user {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #666;
  margin-bottom: 4px;
}
.audit-detail {
  color: #666;
  margin-bottom: 4px;
}
.audit-changes {
  margin-top: 6px;
  padding: 8px;
  background: #f7f8fa;
  border-radius: 6px;
}
.change-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
}
.change-field {
  color: #1989fa;
  font-weight: 500;
  min-width: 60px;
}
.change-old {
  color: #999;
  text-decoration: line-through;
}
.change-new {
  color: #333;
  font-weight: 500;
}
.audit-page :deep(.van-nav-bar) {
  background: white;
}
.audit-page :deep(.van-empty) {
  padding: 60px 0;
}
</style>
