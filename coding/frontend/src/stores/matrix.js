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
    matrixData.value = await api.matrix.data()
  }

  async function loadPaperCells(paperId) {
    paperMatrixCells.value = await api.matrix.paperCells(paperId)
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

  // Column CRUD
  async function createColumn() {
    const ui = useUiStore()
    if (!newColumnName.value.trim()) return
    await api.matrixColumns.create({
      name: newColumnName.value.trim(),
      column_type: newColumnType.value,
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

  async function deleteOption(optId) {
    await api.matrixColumns.deleteOption(optId)
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
    matrixColumns, matrixData, paperMatrixCells, codingCompleteness,
    newColumnName, newColumnType, newOptionValues,
    loadColumns, loadMatrixData, loadPaperCells, loadCompleteness,
    saveMatrixCell, savePaperMatrixCell, toggleMultiValue, parseMultiValue,
    createColumn, updateColumn, deleteColumn,
    addOption, deleteOption, linkCode, unlinkCode,
  }
})
