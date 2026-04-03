import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '@/api'
import { useUiStore } from './ui'

export const useMatrixStore = defineStore('matrix', () => {
  const matrixColumns = ref([])
  const matrixData = ref(null)
  const paperMatrixCells = ref({})
  const codingCompleteness = ref({})

  // Column editor form state
  const matrixStatusFilter = ref('included')
  const newColumnName = ref('')
  const newColumnType = ref('enum_single')
  const newOptionValues = ref({})

  // Debounce timers
  const saveTimers = {}

  // Actions
  async function loadColumns() {
    matrixColumns.value = await api.matrixColumns.list()
  }

  async function loadMatrixData() {
    const params = {}
    if (matrixStatusFilter.value !== 'all') params.status = matrixStatusFilter.value
    matrixData.value = await api.matrix.data(params)
  }

  async function loadPaperCells(paperId) {
    paperMatrixCells.value = {}
    if (paperId) {
      paperMatrixCells.value = await api.matrix.paperCells(paperId)
    }
  }

  async function loadCompleteness() {
    codingCompleteness.value = await api.matrix.completeness()
  }

  function saveMatrixCell(docId, colId, value) {
    // Update local state immediately
    if (!matrixData.value.cells[docId]) matrixData.value.cells[docId] = {}
    matrixData.value.cells[docId][colId] = { value, notes: null }
    // Debounce API call
    const key = `${docId}-${colId}`
    clearTimeout(saveTimers[key])
    saveTimers[key] = setTimeout(() => {
      api.matrix.saveCell({ document_id: docId, column_id: colId, value })
      delete saveTimers[key]
    }, 500)
  }

  function savePaperMatrixCell(docId, colId, value) {
    if (!paperMatrixCells.value[colId]) paperMatrixCells.value[colId] = {}
    paperMatrixCells.value[colId].value = value
    const key = `p-${docId}-${colId}`
    clearTimeout(saveTimers[key])
    saveTimers[key] = setTimeout(() => {
      api.matrix.saveCell({ document_id: docId, column_id: colId, value })
      delete saveTimers[key]
    }, 500)
  }

  function toggleMultiValue(colId, optValue, docId) {
    let current = []
    try {
      const raw = paperMatrixCells.value[colId]?.value || '[]'
      current = JSON.parse(raw)
    } catch { current = [] }
    const idx = current.indexOf(optValue)
    if (idx >= 0) current.splice(idx, 1)
    else current.push(optValue)
    savePaperMatrixCell(docId, colId, JSON.stringify(current))
  }

  function parseMultiValue(val) {
    try { return JSON.parse(val || '[]') } catch { return [] }
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

  // Column CRUD
  async function createColumn() {
    const ui = useUiStore()
    if (!newColumnName.value.trim()) return
    await api.matrixColumns.create({
      name: newColumnName.value.trim(),
      column_type: newColumnType.value,
      color: randomColor(),
    })
    newColumnName.value = ''
    await loadColumns()
    ui.showToast('Column created', 'success')
  }

  async function updateColumn(colId, updates) {
    await api.matrixColumns.update(colId, updates)
    await loadColumns()
  }

  async function deleteColumn(colId) {
    const ui = useUiStore()
    await api.matrixColumns.delete(colId)
    await loadColumns()
    ui.showToast('Column deleted', 'success')
  }

  async function addOption(colId) {
    const value = newOptionValues.value[colId]?.trim()
    if (!value) return
    await api.matrixColumns.addOption(colId, { value })
    newOptionValues.value[colId] = ''
    await loadColumns()
  }

  async function updateOption(optId, data) {
    await api.matrixColumns.updateOption(optId, data)
    await loadColumns()
  }

  async function deleteOption(optId) {
    await api.matrixColumns.deleteOption(optId)
    await loadColumns()
  }

  async function reorderOption(colId, optId, direction) {
    const col = matrixColumns.value.find(c => c.id === colId)
    if (!col) return
    const opts = col.options
    const idx = opts.findIndex(o => o.id === optId)
    const swapIdx = idx + direction
    if (swapIdx < 0 || swapIdx >= opts.length) return
    await Promise.all([
      api.matrixColumns.updateOption(opts[idx].id, { sort_order: swapIdx }),
      api.matrixColumns.updateOption(opts[swapIdx].id, { sort_order: idx }),
    ])
    await loadColumns()
  }

  async function linkCode(colId, codeId) {
    await api.matrixColumns.linkCode(colId, codeId)
    await loadColumns()
  }

  async function unlinkCode(colId, codeId) {
    await api.matrixColumns.unlinkCode(colId, codeId)
    await loadColumns()
  }

  return {
    matrixColumns, matrixData, matrixStatusFilter, paperMatrixCells, codingCompleteness,
    newColumnName, newColumnType, newOptionValues,
    loadColumns, loadMatrixData, loadPaperCells, loadCompleteness,
    saveMatrixCell, savePaperMatrixCell, toggleMultiValue, parseMultiValue,
    createColumn, updateColumn, deleteColumn,
    addOption, updateOption, reorderOption, deleteOption, linkCode, unlinkCode,
  }
})
