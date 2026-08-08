// RAG Forge API client — 同源（生产）或 http://127.0.0.1:8777（开发）
const API_BASE = import.meta.env.DEV ? 'http://127.0.0.1:8777' : ''

export function getApiKey() {
  return localStorage.getItem('ragforge_api_key') || ''
}

export function setApiKey(key) {
  localStorage.setItem('ragforge_api_key', key.trim())
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) }
  const key = getApiKey()
  if (key) headers['X-API-Key'] = key
  if (options.body && !(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
  }
  let resp
  try {
    resp = await fetch(`${API_BASE}${path}`, { ...options, headers })
  } catch {
    throw new Error('无法连接服务，请确认后端已启动 (127.0.0.1:8777)')
  }
  if (resp.status === 401 || resp.status === 403) {
    throw new Error('API Key 无效，请在右上角设置正确的 Key')
  }
  if (!resp.ok) {
    let detail = resp.statusText
    try { detail = (await resp.json()).detail || detail } catch { /* ignore */ }
    throw new Error(detail)
  }
  return resp.json()
}

export const api = {
  health: () => request('/health'),
  config: () => request('/config'),
  ask: (question, mode) =>
    request(mode === 'agent' ? '/agent-ask' : '/ask', {
      method: 'POST',
      body: JSON.stringify({ question, tenant_id: 'default' }),
    }),
  upload: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/upload', { method: 'POST', body: fd })
  },
  documents: () => request('/documents'),
  clearDocuments: () => request('/documents', { method: 'DELETE' }),
}
