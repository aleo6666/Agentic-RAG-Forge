<script setup>
import { ref, nextTick } from 'vue'
import { marked } from 'marked'
import { api } from '../api.js'

const mode = ref('agent')
const question = ref('')
const sending = ref(false)
const messages = ref([])
const chatBox = ref(null)

const STEP_LABEL = {
  route: '意图路由',
  retrieve: '混合检索',
  grade_docs: '相关性评分',
  rewrite: '查询改写',
  generate: '生成回答',
  grade_answer: '答案自检',
  direct: '直接回答',
  clarify: '澄清追问',
}

function md(text) {
  return marked.parse(text || '')
}

async function scrollBottom() {
  await nextTick()
  chatBox.value?.scrollTo({ top: chatBox.value.scrollHeight, behavior: 'smooth' })
}

async function send() {
  const q = question.value.trim()
  if (!q || sending.value) return
  question.value = ''

  messages.value.push({ role: 'user', content: q })
  const bot = { role: 'assistant', content: '', loading: true, trace: [], citations: [], grounded: null, error: null }
  messages.value.push(bot)
  sending.value = true
  scrollBottom()

  try {
    const res = await api.ask(q, mode.value)
    bot.content = res.answer || ''
    bot.trace = res.trace || []
    bot.citations = res.citations || []
    bot.grounded = res.grounded
    bot.loading = false
  } catch (e) {
    bot.loading = false
    bot.error = e.message
  } finally {
    sending.value = false
    scrollBottom()
  }
}

function traceIcon(step) {
  return { route: '🧭', retrieve: '🔍', grade_docs: '⚖️', rewrite: '✏️', generate: '✨', grade_answer: '🛡️', direct: '💬', clarify: '❓' }[step] || '•'
}
</script>

<template>
  <div class="chat-head">
    <div class="mode-switch">
      <button :class="{ active: mode === 'agent' }" @click="mode = 'agent'">🤖 Agentic</button>
      <button :class="{ active: mode === 'standard' }" @click="mode = 'standard'">📄 标准</button>
    </div>
    <span class="chat-status">
      {{ mode === 'agent' ? '路由 → 检索 → 评分 → 生成 → 自检，自动改写循环' : '一次性检索 → 生成' }}
    </span>
  </div>

  <div ref="chatBox" style="flex:1; overflow-y:auto; min-height: 420px; max-height: 62vh;">
    <div v-if="!messages.length" class="empty">
      <div style="font-size: 40px; margin-bottom: 10px;">🔨</div>
      <div style="color: var(--text-dim);">向 RAG Forge 提问，体验 Agentic RAG 决策过程</div>
      <div style="color: var(--text-dim); font-size: 12px; margin-top: 6px;">例如：RAG Forge 支持哪些企业级特性？</div>
    </div>

    <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
      <div class="avatar" :class="m.role">{{ m.role === 'user' ? '👤' : '🤖' }}</div>
      <div class="msg-body">
        <div class="bubble">
          <div v-if="m.loading" style="display:flex; align-items:center; gap:10px; color: var(--text-dim);">
            <span class="spinner"></span> Agent 正在分析…
          </div>
          <div v-else-if="m.error" style="color: var(--red);">{{ m.error }}</div>
          <pre v-else-if="m.role === 'user'">{{ m.content }}</pre>
          <div v-else v-html="md(m.content)"></div>
        </div>

        <template v-if="m.role === 'assistant' && !m.loading && !m.error">
          <span v-if="m.grounded === true" class="grounded yes">✅ 已通过答案自检</span>
          <span v-else-if="m.grounded === false" class="grounded no">⚠️ 自检未完全通过</span>

          <details v-if="m.trace && m.trace.length" class="trace">
            <summary>🧭 决策轨迹（{{ m.trace.length }} 步）</summary>
            <ol>
              <li v-for="(t, j) in m.trace" :key="j">
                <span class="step-name" :class="'step-' + t.step">{{ traceIcon(t.step) }} {{ STEP_LABEL[t.step] || t.step }}</span>
                <span class="step-detail">
                  <template v-if="t.step === 'route'">{{ t.decision }} — {{ t.reason }}</template>
                  <template v-else-if="t.step === 'retrieve'">{{ t.hits }} 个结果（查询: {{ (t.query || '').slice(0, 40) }}）</template>
                  <template v-else-if="t.step === 'grade_docs'">{{ t.relevant }}/{{ t.total }} 相关</template>
                  <template v-else-if="t.step === 'rewrite'">{{ (t.rewritten || '').slice(0, 40) }}</template>
                  <template v-else-if="t.step === 'generate'">{{ t.context_chunks }} 个上下文片段</template>
                  <template v-else-if="t.step === 'grade_answer'">grounded = {{ t.grounded }} — {{ t.reason }}</template>
                  <template v-else-if="t.step === 'clarify'">{{ t.best_effort ? '尽力回答' : '等待澄清' }}</template>
                </span>
              </li>
            </ol>
          </details>

          <div v-if="m.citations && m.citations.length" class="cites">
            <div v-for="(c, j) in m.citations" :key="j" class="cite">📎 {{ c.snippet }}</div>
          </div>
        </template>
      </div>
    </div>
  </div>

  <div class="chat-input">
    <textarea
      v-model="question"
      placeholder="输入问题，Enter 发送，Shift+Enter 换行"
      @keydown.enter.exact.prevent="send"
    ></textarea>
    <button class="btn primary send-btn" :disabled="sending || !question.trim()" @click="send">
      {{ sending ? '…' : '发送' }}
    </button>
  </div>
</template>
