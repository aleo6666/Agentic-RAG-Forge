<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'
import { fmtTime } from '../format.js'

const items = ref([])
const loading = ref(false)
const error = ref('')
const resolving = ref(null) // 正在标记解决的工单 id
const actionError = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.tickets()
    items.value = res.tickets || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function resolve(t) {
  if (resolving.value) return
  resolving.value = t.id
  actionError.value = ''
  try {
    await api.resolveTicket(t.id)
    await refresh()
  } catch (e) {
    actionError.value = `工单 #${t.id} 操作失败：${e.message}`
  } finally {
    resolving.value = null
  }
}

onMounted(refresh)
</script>

<template>
  <div class="section-title">🎫 工单管理 <span style="font-weight:400; color:var(--text-dim); font-size:13px;">转人工的咨询，处理完点“标记已解决”关闭闭环</span></div>

  <div v-if="error" class="card" style="color: var(--red); margin-bottom: 16px;">
    {{ error }}
    <button class="btn sm" style="margin-left: 10px;" @click="refresh">重试</button>
  </div>
  <div v-if="actionError" class="card" style="color: var(--red); margin-bottom: 16px;">{{ actionError }}</div>

  <div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
      <div style="font-weight:600;">全部工单（{{ items.length }}）</div>
      <button class="btn sm" @click="refresh">🔄 刷新</button>
    </div>

    <div v-if="loading" class="empty"><span class="spinner"></span> 加载中…</div>
    <div v-else-if="!items.length && !error" class="empty">暂无工单，没有用户请求转人工</div>

    <table v-else-if="items.length">
      <thead>
        <tr><th style="width: 42%;">问题</th><th>联系方式</th><th>状态</th><th>时间</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="t in items" :key="t.id">
          <td>{{ t.question }}</td>
          <td>{{ t.contact || '—' }}</td>
          <td>
            <span class="badge" :class="t.status === 'open' ? 'warn' : 'ok'">
              {{ t.status === 'open' ? '待处理' : '已解决' }}
            </span>
          </td>
          <td>{{ fmtTime(t.created_at) }}</td>
          <td>
            <button
              v-if="t.status === 'open'"
              class="btn sm primary"
              :disabled="resolving === t.id"
              @click="resolve(t)"
            >
              <span v-if="resolving === t.id" class="spinner"></span>
              {{ resolving === t.id ? ' 处理中…' : '标记已解决' }}
            </button>
            <button v-else class="btn sm" disabled>已完成</button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
