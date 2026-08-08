<script setup>
import { ref, onMounted } from 'vue'
import { api } from '../api.js'

const docs = ref([])
const loading = ref(false)
const drag = ref(false)
const fileInput = ref(null)
const uploads = ref([]) // { name, state: 'uploading'|'ok'|'err', detail }

async function refresh() {
  loading.value = true
  try {
    const res = await api.documents()
    docs.value = res.documents || []
  } catch (e) {
    uploads.value.push({ name: '⚠️ 加载列表失败', state: 'err', detail: e.message })
  } finally {
    loading.value = false
  }
}

async function uploadFiles(files) {
  for (const f of files) {
    const item = { name: f.name, state: 'uploading', detail: '上传中…' }
    uploads.value.push(item)
    try {
      const res = await api.upload(f)
      item.state = 'ok'
      item.detail = `✅ ${res.chunks} chunks / ${res.chars} 字符`
    } catch (e) {
      item.state = 'err'
      item.detail = `❌ ${e.message}`
    }
  }
  refresh()
}

function onDrop(e) {
  drag.value = false
  uploadFiles([...e.dataTransfer.files])
}

async function clearAll() {
  if (!confirm('确定清空整个知识库？此操作不可恢复。')) return
  try {
    const res = await api.clearDocuments()
    uploads.value.push({ name: '🧹 已清空', state: 'ok', detail: `删除 ${res.removed_chunks} 个 chunk` })
    refresh()
  } catch (e) {
    uploads.value.push({ name: '清空失败', state: 'err', detail: e.message })
  }
}

onMounted(refresh)
</script>

<template>
  <div class="section-title">📚 知识库 <span style="font-weight:400; color:var(--text-dim); font-size:13px;">上传文档，Agent 将基于这些内容回答问题</span></div>

  <div
    class="dropzone"
    :class="{ drag }"
    @click="fileInput.click()"
    @dragover.prevent="drag = true"
    @dragleave="drag = false"
    @drop.prevent="onDrop"
  >
    <div style="font-size: 34px;">📂</div>
    <div>点击选择或拖拽文件到此处（支持 .md / .txt / .pdf 等）</div>
    <div style="font-size: 12px; margin-top: 6px;">可多选，上传后自动解析、切分、向量化并入库</div>
    <input ref="fileInput" type="file" multiple hidden @change="e => uploadFiles([...e.target.files])" />
  </div>

  <div v-for="(u, i) in uploads" :key="'u' + i" class="upload-status" :class="u.state">
    <span v-if="u.state === 'uploading'" class="spinner"></span>
    {{ u.name }} — {{ u.detail }}
  </div>

  <div class="card" style="margin-top: 16px;">
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px;">
      <div style="font-weight:600;">已入库文档（{{ docs.length }}）</div>
      <div style="display:flex; gap: 8px;">
        <button class="btn sm" @click="refresh">🔄 刷新</button>
        <button class="btn sm danger" @click="clearAll" :disabled="!docs.length">🗑 清空</button>
      </div>
    </div>
    <table v-if="docs.length">
      <thead>
        <tr><th>文件名</th><th>Chunks</th><th>字符数</th></tr>
      </thead>
      <tbody>
        <tr v-for="d in docs" :key="d.doc_id">
          <td>📄 {{ d.filename }}</td>
          <td>{{ d.chunks }}</td>
          <td>{{ d.chars.toLocaleString() }}</td>
        </tr>
      </tbody>
    </table>
    <div v-else class="empty">{{ loading ? '加载中…' : '知识库为空，先上传文档吧' }}</div>
  </div>
</template>
