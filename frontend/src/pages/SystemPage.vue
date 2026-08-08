<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const health = ref(null)
const cfg = ref(null)
const error = ref('')

onMounted(async () => {
  try {
    health.value = await api.health()
    cfg.value = await api.config()
  } catch (e) {
    error.value = e.message
  }
})
</script>

<template>
  <div class="section-title">⚙️ 系统状态</div>

  <div v-if="error" class="card" style="color: var(--red); margin-bottom: 16px;">{{ error }}</div>

  <div class="sys-grid">
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
        <div style="font-weight:600;">服务健康</div>
        <span class="badge" :class="health?.status === 'ok' ? 'ok' : 'bad'">
          ● {{ health?.status || '未知' }}
        </span>
      </div>
      <div class="kv"><span class="k">版本</span><span class="v">{{ health?.version || '—' }}</span></div>
      <div class="kv"><span class="k">地址</span><span class="v">127.0.0.1:8777</span></div>
    </div>

    <div class="card">
      <div style="font-weight:600; margin-bottom: 12px;">LLM 配置</div>
      <div class="kv"><span class="k">Provider</span><span class="v">{{ cfg?.llm_provider || '—' }}</span></div>
      <div class="kv"><span class="k">模型</span><span class="v">{{ cfg?.llm_model || '—' }}</span></div>
      <div class="kv"><span class="k">端点</span><span class="v">{{ cfg?.llm_endpoint || '—' }}</span></div>
      <div class="kv">
        <span class="k">API Key</span>
        <span class="v" :style="{ color: cfg?.llm_key_configured ? 'var(--green)' : 'var(--red)' }">
          {{ cfg?.llm_key_configured ? '已配置' : '未配置' }}
        </span>
      </div>
    </div>

    <div class="card">
      <div style="font-weight:600; margin-bottom: 12px;">Embedding 配置</div>
      <div class="kv"><span class="k">Provider</span><span class="v">{{ cfg?.embedding_provider || '—' }}</span></div>
      <div class="kv"><span class="k">模型</span><span class="v">{{ cfg?.embedding_model || '—' }}</span></div>
      <div class="kv"><span class="k">Reranker</span><span class="v">{{ cfg?.reranker_model || '—' }}</span></div>
      <div class="kv">
        <span class="k">API Key</span>
        <span class="v" :style="{ color: cfg?.embedding_key_configured ? 'var(--green)' : 'var(--text-dim)' }">
          {{ cfg?.embedding_key_configured ? '已配置' : '本地模型（无需 Key）' }}
        </span>
      </div>
    </div>

    <div class="card">
      <div style="font-weight:600; margin-bottom: 12px;">Agentic RAG</div>
      <div class="kv"><span class="k">意图路由</span><span class="v">route → direct/clarify/retrieve</span></div>
      <div class="kv"><span class="k">自反思</span><span class="v">grade_docs + grade_answer</span></div>
      <div class="kv"><span class="k">改写循环</span><span class="v">最多 3 轮</span></div>
      <div class="kv"><span class="k">决策轨迹</span><span class="v">trace 全程可审计</span></div>
    </div>
  </div>

  <div class="card" style="margin-top: 16px; font-size: 12px; color: var(--text-dim);">
    💡 API Key 存放在浏览器 localStorage，仅用于请求头 X-API-Key，不会上传到任何第三方。
    生产部署请在服务端环境变量配置 <code>RAGFORGE_API_KEY</code>。
  </div>
</template>
