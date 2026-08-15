<script setup>
import { ref, onMounted } from 'vue'
import { api, getApiKey, setApiKey } from './api.js'
import ChatPage from './pages/ChatPage.vue'
import KnowledgePage from './pages/KnowledgePage.vue'
import SessionsPage from './pages/SessionsPage.vue'
import MissedPage from './pages/MissedPage.vue'
import TicketsPage from './pages/TicketsPage.vue'
import SystemPage from './pages/SystemPage.vue'

const tab = ref('chat')
const apiKey = ref(getApiKey())
const keyOk = ref(false)

function saveKey() {
  setApiKey(apiKey.value)
  checkHealth()
}

async function checkHealth() {
  try {
    await api.health()
    keyOk.value = true
  } catch {
    keyOk.value = false
  }
}

onMounted(checkHealth)
</script>

<template>
  <header class="topbar">
    <div class="logo">🔨 RAG <span class="forge">Forge</span></div>
    <nav class="tabs">
      <button class="tab" :class="{ active: tab === 'chat' }" @click="tab = 'chat'">💬 对话</button>
      <button class="tab" :class="{ active: tab === 'kb' }" @click="tab = 'kb'">📚 知识库</button>
      <button class="tab" :class="{ active: tab === 'sessions' }" @click="tab = 'sessions'">🗂 会话</button>
      <button class="tab" :class="{ active: tab === 'missed' }" @click="tab = 'missed'">❓ 未命中</button>
      <button class="tab" :class="{ active: tab === 'tickets' }" @click="tab = 'tickets'">🎫 工单</button>
      <button class="tab" :class="{ active: tab === 'sys' }" @click="tab = 'sys'">⚙️ 系统</button>
    </nav>
    <div class="keybox">
      <input
        v-model="apiKey"
        type="password"
        placeholder="API Key"
        @change="saveKey"
        @keyup.enter="saveKey"
      />
      <span v-if="keyOk" class="key-ok">● 已连接</span>
      <span v-else class="hint">Key 存在浏览器本地</span>
    </div>
  </header>

  <main>
    <ChatPage v-if="tab === 'chat'" />
    <KnowledgePage v-else-if="tab === 'kb'" />
    <SessionsPage v-else-if="tab === 'sessions'" />
    <MissedPage v-else-if="tab === 'missed'" />
    <TicketsPage v-else-if="tab === 'tickets'" />
    <SystemPage v-else />
  </main>
</template>
