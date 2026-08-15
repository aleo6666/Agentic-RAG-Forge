<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'
import { fmtTime } from '../format.js'

const items = ref([])
const loading = ref(false)
const error = ref('')
const onlyNew = ref(true)

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.missedQuestions(onlyNew.value ? 'new' : null)
    items.value = res.missed_questions || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function toggleFilter() {
  onlyNew.value = !onlyNew.value
  refresh()
}

onMounted(refresh)
</script>

<template>
  <div class="section-title">❓ 未命中问题 <span style="font-weight:400; color:var(--text-dim); font-size:13px;">Agent 没答上来的问题，知识库补料的直接依据</span></div>

  <div v-if="error" class="card" style="color: var(--red); margin-bottom: 16px;">
    {{ error }}
    <button class="btn sm" style="margin-left: 10px;" @click="refresh">重试</button>
  </div>

  <div class="card">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
      <div style="font-weight:600;">{{ onlyNew ? '待处理问题' : '全部问题' }}（{{ items.length }}）</div>
      <div style="display:flex; gap: 8px;">
        <button class="btn sm" :class="{ primary: onlyNew }" @click="toggleFilter">
          {{ onlyNew ? '只看待处理' : '查看全部' }}
        </button>
        <button class="btn sm" @click="refresh">🔄 刷新</button>
      </div>
    </div>

    <div v-if="loading" class="empty"><span class="spinner"></span> 加载中…</div>
    <div v-else-if="!items.length && !error" class="empty">
      {{ onlyNew ? '暂无未命中问题，Agent 全部接住了 🎉' : '暂无记录' }}
    </div>

    <table v-else-if="items.length">
      <thead>
        <tr><th style="width: 55%;">问题</th><th>状态</th><th>时间</th></tr>
      </thead>
      <tbody>
        <tr v-for="q in items" :key="q.id">
          <td>{{ q.question }}</td>
          <td>
            <span class="badge" :class="q.status === 'new' ? 'warn' : 'ok'">
              {{ q.status === 'new' ? '待处理' : q.status }}
            </span>
          </td>
          <td>{{ fmtTime(q.created_at) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
