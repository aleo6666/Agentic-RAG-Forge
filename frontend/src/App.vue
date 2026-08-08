<script setup>
import { ref, onMounted } from 'vue'
import { api, getApiKey, setApiKey } from './api.js'
import ChatPage from './pages/ChatPage.vue'
import KnowledgePage from './pages/KnowledgePage.vue'
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
    <SystemPage v-else />
  </main>
</template>
