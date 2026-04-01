import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api'
import { useUiStore } from './ui'

export const useCodebookStore = defineStore('codebook', () => {
  const codes = ref([])
  const codeUsageCounts = ref({})
  const newCodeName = ref('')
  const newSubCodeNames = ref({})

  // Getters
  const topLevelCodes = computed(() => codes.value)

  const allCodesFlat = computed(() => {
    const flat = []
    for (const code of codes.value) {
      flat.push(code)
      for (const child of code.children || []) {
        flat.push(child)
      }
    }
    return flat
  })

  // Actions
  async function loadCodes() {
    codes.value = await api.codes.list()
  }

  async function loadUsageCounts() {
    codeUsageCounts.value = await api.codes.usage()
  }

  async function createTopCode() {
    const ui = useUiStore()
    if (!newCodeName.value.trim()) return
    await api.codes.create({ name: newCodeName.value.trim() })
    newCodeName.value = ''
    await loadCodes()
    ui.showToast('Code created', 'success')
  }

  async function createSubCode(parentId) {
    const name = newSubCodeNames.value[parentId]?.trim()
    if (!name) return
    await api.codes.create({ name, parent_id: parentId })
    newSubCodeNames.value[parentId] = ''
    await loadCodes()
  }

  async function updateCode(codeId, updates) {
    await api.codes.update(codeId, updates)
    await loadCodes()
  }

  async function deleteCode(codeId) {
    const ui = useUiStore()
    try {
      await api.codes.delete(codeId)
      await loadCodes()
      await loadUsageCounts()
    } catch {
      ui.showToast('Code has annotations or sub-codes', 'error')
    }
  }

  async function reorderCode(codeId, direction) {
    let siblings, idx
    for (const code of codes.value) {
      if (code.id === codeId) {
        siblings = codes.value
        idx = siblings.indexOf(code)
        break
      }
      const childIdx = (code.children || []).findIndex(c => c.id === codeId)
      if (childIdx >= 0) {
        siblings = code.children
        idx = childIdx
        break
      }
    }
    if (!siblings || idx === undefined) return
    const swapIdx = idx + direction
    if (swapIdx < 0 || swapIdx >= siblings.length) return
    const a = siblings[idx], b = siblings[swapIdx]
    await Promise.all([
      updateCode(a.id, { sort_order: swapIdx }),
      updateCode(b.id, { sort_order: idx }),
    ])
  }

  function codeMatchesSearch(topCode, query) {
    const q = query.toLowerCase()
    if (!q) return true
    if (topCode.name.toLowerCase().includes(q)) return true
    if (topCode.description?.toLowerCase().includes(q)) return true
    return (topCode.children || []).some(c => c.name.toLowerCase().includes(q))
  }

  function subCodeMatchesSearch(sub, topCode, query) {
    const q = query.toLowerCase()
    if (!q) return true
    return sub.name.toLowerCase().includes(q) || topCode.name.toLowerCase().includes(q)
  }

  return {
    codes, codeUsageCounts, newCodeName, newSubCodeNames,
    topLevelCodes, allCodesFlat,
    loadCodes, loadUsageCounts,
    createTopCode, createSubCode, updateCode, deleteCode, reorderCode,
    codeMatchesSearch, subCodeMatchesSearch,
  }
})
