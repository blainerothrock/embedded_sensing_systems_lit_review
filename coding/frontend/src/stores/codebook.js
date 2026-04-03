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

  function randomColor() {
    const hue = Math.floor(Math.random() * 360)
    const s = 65, l = 55
    const a = (s / 100) * Math.min(l / 100, 1 - l / 100)
    const f = n => {
      const k = (n + hue / 30) % 12
      const c = l / 100 - a * Math.max(Math.min(k - 3, 9 - k, 1), -1)
      return Math.round(255 * c).toString(16).padStart(2, '0')
    }
    return `#${f(0)}${f(8)}${f(4)}`
  }

  async function createTopCode() {
    const ui = useUiStore()
    if (!newCodeName.value.trim()) return
    await api.codes.create({ name: newCodeName.value.trim(), color: randomColor() })
    newCodeName.value = ''
    await loadCodes()
    ui.showToast('Code created', 'success')
  }

  async function createSubCode(parentId) {
    const name = newSubCodeNames.value[parentId]?.trim()
    if (!name) return
    await api.codes.create({ name, parent_id: parentId, color: randomColor() })
    newSubCodeNames.value[parentId] = ''
    await loadCodes()
  }

  async function createSubCodeAndReturn(parentId, name) {
    if (!name?.trim()) return null
    const code = await api.codes.create({ name: name.trim(), parent_id: parentId, color: randomColor() })
    await loadCodes()
    return code
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

  async function shuffleColors() {
    if (!confirm('Reassign all code colors? This cannot be undone.')) return
    const ui = useUiStore()
    const allCodes = allCodesFlat.value
    const n = allCodes.length
    // Generate evenly-spaced hues with consistent saturation/lightness
    const shuffled = [...Array(n).keys()]
    // Fisher-Yates shuffle the hue indices for variety
    for (let i = shuffled.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]]
    }
    const promises = allCodes.map((code, i) => {
      const hue = (shuffled[i] * 360) / n
      const color = `hsl(${Math.round(hue)}, 65%, 55%)`
      // Convert HSL to hex for storage
      const hex = hslToHex(hue, 65, 55)
      return api.codes.update(code.id, { color: hex })
    })
    await Promise.all(promises)
    await loadCodes()
    ui.showToast('Colors shuffled', 'success')
  }

  function hslToHex(h, s, l) {
    s /= 100; l /= 100
    const a = s * Math.min(l, 1 - l)
    const f = n => {
      const k = (n + h / 30) % 12
      const color = l - a * Math.max(Math.min(k - 3, 9 - k, 1), -1)
      return Math.round(255 * color).toString(16).padStart(2, '0')
    }
    return `#${f(0)}${f(8)}${f(4)}`
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
    createTopCode, createSubCode, createSubCodeAndReturn, updateCode, deleteCode, reorderCode,
    shuffleColors,
    codeMatchesSearch, subCodeMatchesSearch,
  }
})
