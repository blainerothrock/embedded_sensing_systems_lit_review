import { useUiStore } from '@/stores/ui'

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const ui = useUiStore()
    const text = await res.text().catch(() => res.statusText)
    ui.showToast(`API error: ${text}`, 'error')
    throw new Error(`API ${res.status}: ${text}`)
  }
  if (res.status === 204) return null
  return res.json()
}

function get(path) {
  return request(path)
}

function post(path, body) {
  return request(path, { method: 'POST', body: JSON.stringify(body) })
}

function put(path, body) {
  return request(path, { method: 'PUT', body: JSON.stringify(body) })
}

function del(path) {
  return request(path, { method: 'DELETE' })
}

function upload(path, formData) {
  return request(path, {
    method: 'POST',
    headers: {},
    body: formData,
  })
}

export const api = {
  // Papers & Screening
  papers: {
    list: (params = {}) => get(`/api/papers?${new URLSearchParams(params)}`),
    get: (id) => get(`/api/papers/${id}`),
    review: (id, data) => post(`/api/papers/${id}/review`, data),
    setCodingStatus: (id, coding_status) => post(`/api/papers/${id}/coding-status`, { coding_status }),
    getNotes: (id) => get(`/api/papers/${id}/notes`),
    saveNotes: (id, content) => put(`/api/papers/${id}/notes`, { content }),
  },
  exclusionCodes: () => get('/api/exclusion-codes'),
  stats: () => get('/api/stats'),

  // PDF
  pdf: {
    upload: (id, formData) => upload(`/api/papers/${id}/upload-pdf`, formData),
    url: (id) => `/api/papers/${id}/pdf`,
    delete: (id) => del(`/api/papers/${id}/pdf`),
  },

  // Codes
  codes: {
    list: () => get('/api/codes'),
    create: (data) => post('/api/codes', data),
    update: (id, data) => put(`/api/codes/${id}`, data),
    delete: (id) => del(`/api/codes/${id}`),
    usage: () => get('/api/codes/usage'),
  },

  // Annotations
  annotations: {
    list: (paperId) => get(`/api/papers/${paperId}/annotations`),
    create: (paperId, data) => post(`/api/papers/${paperId}/annotations`, data),
    update: (id, data) => put(`/api/annotations/${id}`, data),
    delete: (id) => del(`/api/annotations/${id}`),
    addCode: (annId, codeId) => post(`/api/annotations/${annId}/codes/${codeId}`),
    updateCodeNote: (annId, codeId, note) => put(`/api/annotations/${annId}/codes/${codeId}/note`, { note }),
    removeCode: (annId, codeId) => del(`/api/annotations/${annId}/codes/${codeId}`),
  },

  // Matrix Columns
  matrixColumns: {
    list: () => get('/api/matrix-columns'),
    create: (data) => post('/api/matrix-columns', data),
    update: (id, data) => put(`/api/matrix-columns/${id}`, data),
    delete: (id) => del(`/api/matrix-columns/${id}`),
    addOption: (id, data) => post(`/api/matrix-columns/${id}/options`, data),
    updateOption: (optId, data) => put(`/api/matrix-column-options/${optId}`, data),
    deleteOption: (optId) => del(`/api/matrix-column-options/${optId}`),
    linkCode: (colId, codeId) => post(`/api/matrix-columns/${colId}/codes/${codeId}`),
    unlinkCode: (colId, codeId) => del(`/api/matrix-columns/${colId}/codes/${codeId}`),
  },

  // Matrix Data
  matrix: {
    data: (params = {}) => get(`/api/matrix?${new URLSearchParams(params)}`),
    saveCell: (data) => post('/api/matrix/cell', data),
    paperCells: (paperId) => get(`/api/papers/${paperId}/matrix-cells`),
    completeness: () => get('/api/coding/completeness'),
  },

  // Themes & Summary
  themes: (codeId) => get(`/api/themes/${codeId}`),
  paperSummary: (paperId) => get(`/api/papers/${paperId}/summary`),

  // Chat
  chat: {
    list: (paperId) => get(`/api/papers/${paperId}/chats`),
    create: (paperId, data) => post(`/api/papers/${paperId}/chats`, data),
    messages: (chatId) => get(`/api/chats/${chatId}/messages`),
    delete: (chatId) => del(`/api/chats/${chatId}`),
    update: (chatId, data) => put(`/api/chats/${chatId}`, data),
    streamUrl: (chatId) => `/api/chats/${chatId}/messages/stream`,
  },

  // Settings
  settings: {
    get: () => get('/api/settings'),
    save: (data) => put('/api/settings', data),
  },

  // LLM
  llmModels: () => get('/api/llm/models'),
  promptSize: (paperId) => get(`/api/papers/${paperId}/prompt-size`),
}
