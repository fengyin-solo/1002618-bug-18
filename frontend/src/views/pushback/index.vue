<template>
  <section class="page" data-module="pushback">
    <header class="page-head">
      <div>
        <h2>推出开车管理</h2>
        <p class="page-desc">维护推出任务，围绕推出编号、对应航班、推出方向、牵引车编号做登记、筛选与状态流转。确认推出为一次签名确认，方向、牵引车编号与实际时段一并写入。</p>
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
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
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
          <td v-for="column in columns" :key="column">
            <button v-if="column === '推出编号'" class="link" type="button" @click="openDetail(row)">{{ row[column] ?? '—' }}</button>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(String(row.status))"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(String(row.status)).length">—</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无推出开车数据，可先登记推出任务</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条推出开车记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>推出任务明细 · {{ detail['推出编号'] }}</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-list">
          <div v-for="column in columns" :key="column" class="detail-row">
            <dt>{{ column }}</dt>
            <dd>{{ detail[column] ?? '—' }}</dd>
          </div>
          <div class="detail-row">
            <dt>签名状态</dt>
            <dd>{{ detail.signed ? '已签名确认' : '未签名' }}</dd>
          </div>
        </dl>
        <p v-if="detailError" class="error-text">{{ detailError }}</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/pushback'
const columns = ["推出编号", "对应航班", "推出方向", "牵引车编号", "牵引车司机", "通信频道", "推出时段", "推出状态"]
const statuses = ["待推出", "推出中", "已推出", "已取消"]
// 动作按状态收敛：终态（已推出/已取消）不再提供任何动作，已取消的不能再确认。
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  '待推出': ['安排推出'],
  '推出中': ['开始推出', '确认推出'],
  '已推出': [],
  '已取消': [],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const detail = ref<Row | null>(null)
const detailError = ref('')

// 待推出等条数始终跟当前明细重算，不再展示一份写死的零值。
const stats = computed(() => {
  const countOf = (status: string) => rows.value.filter((row) => String(row.status) === status).length
  return [
    { label: '待推出航班', value: countOf('待推出') },
    { label: '推出中航班', value: countOf('推出中') },
    { label: '已推出航班', value: countOf('已推出') },
  ]
})

function availableActions(status: string): string[] {
  return ACTIONS_BY_STATUS[status] ?? []
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '推出任务登记入口尚未接入审批流'
}

async function openDetail(row: Row) {
  detailError.value = ''
  detail.value = row
  try {
    // 明细以接口返回为准，与列表读到的是同一条后端记录。
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('推出任务明细读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    detailError.value = error instanceof Error ? error.message : '推出任务明细读取失败'
  }
}

function closeDetail() {
  detail.value = null
  detailError.value = ''
}

function promptSignValues(row: Row): Record<string, string> | null {
  // 签名确认：一并采集推出方向、牵引车编号与通信频道；实际时段由后端写入。
  const direction = window.prompt('签名确认：请输入推出方向', String(row['推出方向'] ?? ''))
  if (direction === null) return null
  const tractor = window.prompt('签名确认：请输入牵引车编号', String(row['牵引车编号'] ?? ''))
  if (tractor === null) return null
  const channel = window.prompt('签名确认：请输入通信频道（变更将同步到该航班相关记录）', String(row['通信频道'] ?? ''))
  if (channel === null) return null
  return { 推出方向: direction.trim(), 牵引车编号: tractor.trim(), 通信频道: channel.trim() }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  let values: Record<string, string> = { action }
  if (action === '确认推出') {
    const signed = promptSignValues(row)
    if (signed === null) return
    values = { action, ...signed }
  }
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || !payload?.ok) {
      throw new Error(payload?.message || '推出开车动作未生效，请稍后重试')
    }
    await reload()
    if (detail.value && String(detail.value.id) === String(row.id)) {
      closeDetail()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '推出开车操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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

onMounted(reload)
</script>
