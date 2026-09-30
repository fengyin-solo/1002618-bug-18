<template>
  <section class="page" data-module="pushback">
    <header class="page-head">
      <div>
        <h2>推出开车管理</h2>
        <p class="page-desc">推出记录一次签名确认：确认时一并写入推出方向、牵引车编号与实际时段，确认后列表、详情与刷新读到的都是同一份内容。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记推出任务</button>
        <button class="btn" type="button" @click="exportRows">导出推出开车清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>推出编号</span>
        <input v-model="keyword" placeholder="按推出编号检索" />
      </label>
      <label class="filter-item">
        <span>推出状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="item in statuses" :key="item" :value="item">{{ item }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ cellText(row, column) }}</td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <button
              v-if="row.status === '待推出'"
              class="link"
              type="button"
              @click="openConfirm(row)"
            >
              签名确认
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无推出开车数据，可先登记推出任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条推出开车记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detailEntry" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <h3>推出任务详情（{{ detailEntry['推出编号'] }}）</h3>
        <dl class="detail-grid">
          <template v-for="field in detailFields" :key="field">
            <dt>{{ field }}</dt>
            <dd>{{ detailText(field) }}</dd>
          </template>
        </dl>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeDetail">关闭</button>
        </div>
      </div>
    </div>

    <div v-if="confirmTarget" class="modal-mask" @click.self="closeConfirm">
      <form class="modal-card" @submit.prevent="submitConfirm">
        <h3>签名确认（{{ confirmTarget['推出编号'] }} / {{ confirmTarget['对应航班'] }}）</h3>
        <p class="modal-hint">确认后状态由待推出单向变为已推出，不可回退；方向或车号留空则保留原值并写明原因。</p>
        <label class="modal-field">
          <span>推出方向</span>
          <input v-model="confirmForm['推出方向']" placeholder="留空则保留原值" />
        </label>
        <label class="modal-field">
          <span>牵引车编号</span>
          <input v-model="confirmForm['牵引车编号']" placeholder="留空则保留原值" />
        </label>
        <label class="modal-field">
          <span>实际推出时段</span>
          <input v-model="confirmForm['实际推出时段']" placeholder="留空则取当前时间" />
        </label>
        <label class="modal-field">
          <span>确认人（签名）</span>
          <input v-model="confirmForm['确认人']" placeholder="必填" />
        </label>
        <p v-if="confirmError" class="error-text">{{ confirmError }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="submit" :disabled="confirming">
            {{ confirming ? '提交中…' : '签名确认' }}
          </button>
          <button class="btn ghost" type="button" @click="closeConfirm">取消</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/pushback'
const columns = ["推出编号", "对应航班", "推出方向", "牵引车编号", "牵引车司机", "通信频道", "推出时段", "实际推出时段", "确认人", "推出状态"]
const statuses = ["待推出", "已推出", "已取消"]
const detailFields = ["推出编号", "对应航班", "推出方向", "牵引车编号", "牵引车司机", "通信频道", "推出时段", "实际推出时段", "确认人", "确认时间", "确认备注", "推出状态"]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')
const stats = ref([
  { label: '待推出航班', value: 0 },
  { label: '已推出航班', value: 0 },
  { label: '已取消航班', value: 0 },
])

const detailEntry = ref<Row | null>(null)
const confirmTarget = ref<Row | null>(null)
const confirmForm = reactive<Record<string, string>>({ 推出方向: '', 牵引车编号: '', 实际推出时段: '', 确认人: '' })
const confirmError = ref('')
const confirming = ref(false)

function cellText(row: Row, column: string) {
  const value = column === '推出状态' ? row.status : row[column]
  return value === null || value === undefined || value === '' ? '—' : value
}

function detailText(field: string) {
  if (!detailEntry.value) {
    return '—'
  }
  return String(cellText(detailEntry.value, field))
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '推出任务登记入口尚未接入审批流'
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('推出任务详情读取失败')
    }
    detailEntry.value = (await response.json()) as Row
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '推出任务详情读取失败'
  }
}

function closeDetail() {
  detailEntry.value = null
}

function openConfirm(row: Row) {
  confirmTarget.value = row
  confirmForm['推出方向'] = String(row['推出方向'] ?? '')
  confirmForm['牵引车编号'] = String(row['牵引车编号'] ?? '')
  confirmForm['实际推出时段'] = ''
  confirmForm['确认人'] = ''
  confirmError.value = ''
}

function closeConfirm() {
  confirmTarget.value = null
  confirmError.value = ''
}

async function submitConfirm() {
  if (!confirmTarget.value) {
    return
  }
  confirming.value = true
  confirmError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${confirmTarget.value.id}/confirm`, {
      method: 'POST',
      body: JSON.stringify({ values: { ...confirmForm } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      confirmError.value = payload.message || '签名确认未生效，请核对后重试'
      return
    }
    noticeMessage.value = payload.message || '推出任务已签名确认'
    closeConfirm()
    await Promise.all([reload(), reloadStats()])
  } catch (error) {
    confirmError.value = error instanceof Error ? error.message : '签名确认提交失败'
  } finally {
    confirming.value = false
  }
}

async function reload() {
  errorMessage.value = ''
  noticeMessage.value = ''
  const query = new URLSearchParams()
  if (keyword.value) {
    query.set('keyword', keyword.value)
  }
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('推出任务列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '推出开车列表读取失败'
  }
}

async function reloadStats() {
  try {
    const response = await request(`${ENDPOINT}/stats`)
    if (!response.ok) {
      throw new Error('推出状态统计读取失败')
    }
    const payload = await response.json()
    stats.value = [
      { label: '待推出航班', value: payload['待推出'] ?? 0 },
      { label: '已推出航班', value: payload['已推出'] ?? 0 },
      { label: '已取消航班', value: payload['已取消'] ?? 0 },
    ]
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '推出状态统计读取失败'
  }
}

onMounted(() => {
  void reload()
  void reloadStats()
})
</script>

<style scoped>
.notice-text { color: #067647; }
.filter-item select { padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: #fff; }
.modal-mask { position: fixed; inset: 0; background: rgba(15, 23, 42, 0.45); display: flex; align-items: center; justify-content: center; z-index: 20; }
.modal-card { background: #fff; border-radius: 8px; padding: 16px 20px; width: 420px; max-width: 90vw; }
.modal-card h3 { margin: 0 0 8px; font-size: 15px; }
.modal-hint { color: var(--muted); font-size: 12px; margin: 0 0 10px; }
.modal-field { display: block; margin-bottom: 10px; }
.modal-field span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }
.modal-field input { width: 100%; padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
.detail-grid { display: grid; grid-template-columns: 96px 1fr; gap: 6px 12px; margin: 0; font-size: 13px; }
.detail-grid dt { color: var(--muted); }
.detail-grid dd { margin: 0; }
</style>
