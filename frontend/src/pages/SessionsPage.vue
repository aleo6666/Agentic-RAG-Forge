<script setup>
import { ref, onMounted } from 'vue'
import { marked } from 'marked'
import { api } from '../api.js'
import { fmtTime } from '../format.js'

const sessions = ref([])
const loading = ref(false)
const error = ref('')

// 详情视图状态（null = 列表视图）
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')

async function refresh() {
  loading.value = true
  error.value = ''
  try {
    const res = await api.sessions()
    sessions.value = res.sessions || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function openDetail(s) {
  detail.value = { id: s.id, created_at: s.created_at, rounds: null, messages: [] }
  detailLoading.value = true
  detailError.value = ''
  try {
    const res = await api.sessionDetail(s.id)
    detail.value = { id: res.session_id, created_at: s.created_at, rounds: res.rounds, messages: res.messages || [] }
  } catch (e) {
    detailError.value = e.message
  } finally {
    detailLoading.value = false
  }
}

function backToList() {
  detail.value = null
  detailError.value = ''
  refresh()
}

function md(text) {
  return marked.parse(text || '')
}

onMounted(refresh)
</script>

<template>
  <!-- ── 会话详情 ── -->
  <template v-if="detail">
    <div class="chat-head">
      <button class="btn sm" @click="backToList">← 返回列表</button>
      <span class="chat-status mono">会话 {{ detail.id }}</span>
    </div>

    <div v-if="detailError" class="card" style="color: var(--red); margin-bottom: 16px;">
      {{ detailError }}
      <button class="btn sm" style="margin-left: 10px;" @click="openDetail(detail)">重试</button>
    </div>

    <div v-if="detailLoading" class="empty"><span class="spinner"></span> 加载对话内容…</div>

    <template v-else-if="!detailError">
      <div class="card" style="margin-bottom: 16px; display: flex; gap: 28px; flex-wrap: wrap;">
        <div class="kv" style="border:none; padding: 0; gap: 10px;"><span class="k">对话轮数</span><span class="v">{{ detail.rounds ?? '—' }}</span></div>
        <div class="kv" style="border:none; padding: 0; gap: 10px;"><span class="k">消息条数</span><span class="v">{{ detail.messages.length }}</span></div>
        <div class="kv" style="border:none; padding: 0; gap: 10px;"><span class="k">创建时间</span><span class="v">{{ fmtTime(detail.created_at) }}</span></div>
      </div>

      <div v-if="!detail.messages.length" class="empty">该会话暂无消息记录</div>

      <div v-for="(m, i) in detail.messages" :key="i" class="msg" :class="m.role">
        <div class="avatar" :class="m.role === 'user' ? 'user' : 'bot'">{{ m.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="msg-body">
          <div class="bubble">
            <pre v-if="m.role === 'user'">{{ m.content }}</pre>
            <div v-else v-html="md(m.content)"></div>
          </div>
          <div style="font-size: 11px; color: var(--text-dim); margin-top: 4px;">{{ fmtTime(m.created_at) }}</div>
        </div>
      </div>
    </template>
  </template>

  <!-- ── 会话列表 ── -->
  <template v-else>
    <div class="section-title">🗂 会话记录 <span style="font-weight:400; color:var(--text-dim); font-size:13px;">客服对话全量留痕，点击查看完整对话</span></div>

    <div v-if="error" class="card" style="color: var(--red); margin-bottom: 16px;">
      {{ error }}
      <button class="btn sm" style="margin-left: 10px;" @click="refresh">重试</button>
    </div>

    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
        <div style="font-weight:600;">全部会话（{{ sessions.length }}）</div>
        <button class="btn sm" @click="refresh">🔄 刷新</button>
      </div>

      <div v-if="loading" class="empty"><span class="spinner"></span> 加载中…</div>
      <div v-else-if="!sessions.length && !error" class="empty">暂无会话记录，先去对话页聊几句吧</div>

      <table v-else-if="sessions.length">
        <thead>
          <tr><th>会话 ID</th><th>创建时间</th><th>消息数</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in sessions" :key="s.id" class="clickable" @click="openDetail(s)">
            <td class="mono" :title="s.id">{{ s.id.slice(0, 8) }}…</td>
            <td>{{ fmtTime(s.created_at) }}</td>
            <td>{{ s.message_count }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </template>
</template>
