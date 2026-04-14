import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { api } from '@/api'
import { useUiStore } from './ui'

export const useWorkspaceStore = defineStore('workspace', () => {
  // Papers
  const papers = ref([])
  const activePaperId = ref(null)
  const activePaper = ref(null)
  const searchQuery = ref('')
  const statusFilter = ref(localStorage.getItem('statusFilter') || 'all')
  const sortBy = ref(localStorage.getItem('sortBy') || 'title')

  watch(statusFilter, (v) => localStorage.setItem('statusFilter', v))
  watch(sortBy, (v) => localStorage.setItem('sortBy', v))
  const exclusionCodes = ref([])
  const stats = ref(null)

  // Review form
  const reviewForm = ref({ decision: null, notes: '', exclusion_code_ids: [] })
  let reviewFormClean = null

  // Annotations
  const annotations = ref([])
  const activeAnnotationId = ref(null)
  const pendingSelection = ref(null) // { text, rects, pageNumber }
  const selectedAnnotationCodes = ref([])
  const addingRegionTo = ref(null)
  const annotationToolbarSearch = ref('')
  const showAnnotationToolbar = ref(false)
  const showCodePicker = ref(false)
  const codePickerSearch = ref('')

  // Paper notes
  const paperNote = ref('')

  // Summary
  const paperSummary = ref([])

  // Getters
  const activeAnnotation = computed(() => {
    if (!activeAnnotationId.value) return null
    return annotations.value.find(a => a.id === activeAnnotationId.value) || null
  })

  const isReviewDirty = computed(() => {
    if (!reviewFormClean) return false
    return JSON.stringify(reviewForm.value) !== reviewFormClean
  })

  const currentPaperIndex = computed(() => {
    if (!activePaperId.value) return -1
    return papers.value.findIndex(p => p.id === activePaperId.value)
  })

  const annotationRegions = computed(() => {
    const ann = activeAnnotation.value
    if (!ann) return []
    const rects = JSON.parse(ann.rects_json || '[]')
    const isArea = ann.annotation_type === 'area'

    // Group rects by region index. Rects without `region` are legacy —
    // fall back to grouping by page (one group per unique page).
    const hasRegionField = rects.some(r => r.region != null)
    const groups = {}
    const groupOrder = []
    for (const r of rects) {
      const key = hasRegionField
        ? (r.region ?? 0)
        : (r.page || ann.page_number)
      if (!groups[key]) { groups[key] = []; groupOrder.push(key) }
      groups[key].push(r)
    }
    if (hasRegionField) groupOrder.sort((a, b) => a - b)
    else groupOrder.sort((a, b) => a - b) // legacy: sort by page

    const texts = (ann.selected_text || '').split(' ... ').map(t => t.trim())

    return groupOrder.map((key, i) => {
      const groupRects = groups[key]
      const page = groupRects[0]?.page || ann.page_number
      const text = isArea ? null : (texts[i] || null)
      return {
        page,
        type: isArea ? 'area' : (text ? 'text' : 'area'),
        text,
        groupKey: key,
      }
    })
  })

  // Actions
  async function loadPapers() {
    const params = {}
    if (searchQuery.value) params.search = searchQuery.value
    if (statusFilter.value !== 'all') params.status = statusFilter.value
    if (sortBy.value !== 'title') params.sort = sortBy.value
    papers.value = await api.papers.list(params)
  }

  function shufflePapers() {
    const arr = [...papers.value]
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[arr[i], arr[j]] = [arr[j], arr[i]]
    }
    papers.value = arr
  }

  async function loadExclusionCodes() {
    exclusionCodes.value = await api.exclusionCodes()
  }

  async function loadStats() {
    stats.value = await api.stats()
  }

  async function selectPaper(id, force = false) {
    if (!force && isReviewDirty.value) {
      if (!confirm('You have unsaved review changes. Discard?')) return
    }

    activePaperId.value = id
    localStorage.setItem('activePaperId', id)
    const paper = await api.papers.get(id)
    activePaper.value = paper

    // Populate review form
    reviewForm.value = {
      decision: paper.phase3_decision || null,
      notes: paper.phase3_notes || '',
      exclusion_code_ids: (paper.exclusion_codes || []).map(c => c.id),
    }
    reviewFormClean = JSON.stringify(reviewForm.value)

    // Reset annotation state
    activeAnnotationId.value = null
    showAnnotationToolbar.value = false
    pendingSelection.value = null

    // Load annotations, summary, and notes
    await Promise.all([
      loadAnnotations(),
      loadPaperSummary(),
      loadPaperNote(),
    ])
  }

  async function nextPaper() {
    if (papers.value.length === 0) return
    const idx = currentPaperIndex.value
    const nextIdx = idx < papers.value.length - 1 ? idx + 1 : 0
    await selectPaper(papers.value[nextIdx].id)
  }

  async function prevPaper() {
    if (papers.value.length === 0) return
    const idx = currentPaperIndex.value
    const prevIdx = idx > 0 ? idx - 1 : papers.value.length - 1
    await selectPaper(papers.value[prevIdx].id)
  }

  async function saveReview() {
    const ui = useUiStore()
    if (!activePaperId.value || !reviewForm.value.decision) return
    const data = await api.papers.review(activePaperId.value, reviewForm.value)
    if (data.success) {
      ui.showToast('Review saved', 'success')
      reviewFormClean = JSON.stringify(reviewForm.value)
      await loadPapers()
      await loadStats()
      activePaper.value.phase3_decision = reviewForm.value.decision
      activePaper.value.phase3_notes = reviewForm.value.notes
    } else {
      ui.showToast(data.error || 'Save failed', 'error')
    }
  }

  async function setCodingStatus(status) {
    const ui = useUiStore()
    if (!activePaperId.value) return
    await api.papers.setCodingStatus(activePaperId.value, status)
    if (activePaper.value) activePaper.value.coding_status = status
    await loadPapers()
    ui.showToast(`Status: ${status || 'included'}`, 'success')
  }

  function toggleExclusionCode(id) {
    const idx = reviewForm.value.exclusion_code_ids.indexOf(id)
    if (idx >= 0) {
      reviewForm.value.exclusion_code_ids.splice(idx, 1)
    } else {
      reviewForm.value.exclusion_code_ids.push(id)
    }
  }

  // Annotations
  async function loadAnnotations() {
    if (!activePaperId.value) return
    annotations.value = await api.annotations.list(activePaperId.value)
  }

  async function createAnnotation(data) {
    const ui = useUiStore()
    await api.annotations.create(activePaperId.value, data)
    await loadAnnotations()
    // Select the newest annotation (highest id, not last in page-sorted array)
    if (annotations.value.length > 0) {
      const newest = annotations.value.reduce((a, b) => a.id > b.id ? a : b)
      ui.rightTab = 'annotations'
      activeAnnotationId.value = newest.id
    }
    ui.showToast('Annotation created', 'success')
  }

  async function deleteAnnotation(annId) {
    await api.annotations.delete(annId)
    if (activeAnnotationId.value === annId) activeAnnotationId.value = null
    await loadAnnotations()
  }

  async function updateAnnotation(annId, data) {
    await api.annotations.update(annId, data)
    await loadAnnotations()
  }

  async function addAnnotationCode(annId, codeId) {
    await api.annotations.addCode(annId, codeId)
    await loadAnnotations()
  }

  async function removeAnnotationCode(annId, codeId) {
    await api.annotations.removeCode(annId, codeId)
    await loadAnnotations()
  }

  async function saveAnnotationCodeNote(annId, codeId, note) {
    await api.annotations.updateCodeNote(annId, codeId, note)
    const ann = annotations.value.find(a => a.id === annId)
    if (ann) {
      const c = ann.codes.find(c => c.id === codeId)
      if (c) c.ac_note = note
    }
  }

  async function saveAnnotationNote(annId, note) {
    await api.annotations.update(annId, { note })
    const ann = annotations.value.find(a => a.id === annId)
    if (ann) ann.note = note
  }

  async function appendRegionToAnnotation(annId, newRects, pageNumber, newText) {
    const ann = annotations.value.find(a => a.id === annId)
    if (!ann) return
    const existingRects = JSON.parse(ann.rects_json || '[]')
    // Ensure existing rects have a region index (legacy rects: group by page)
    const hasRegion = existingRects.some(r => r.region != null)
    let taggedExisting
    let nextRegion
    if (hasRegion) {
      taggedExisting = existingRects.map(r => ({
        ...r,
        page: r.page || ann.page_number,
        region: r.region ?? 0,
      }))
      nextRegion = Math.max(...taggedExisting.map(r => r.region)) + 1
    } else {
      // Legacy: assign region indices by unique page in order
      const pageToRegion = {}
      const pageOrder = []
      for (const r of existingRects) {
        const page = r.page || ann.page_number
        if (!(page in pageToRegion)) {
          pageToRegion[page] = pageOrder.length
          pageOrder.push(page)
        }
      }
      taggedExisting = existingRects.map(r => {
        const page = r.page || ann.page_number
        return { ...r, page, region: pageToRegion[page] }
      })
      nextRegion = pageOrder.length
    }
    const taggedNewRects = newRects.map(r => ({ ...r, page: pageNumber, region: nextRegion }))
    const mergedRects = [...taggedExisting, ...taggedNewRects]
    // Append text segment (empty string for box regions keeps text-to-region alignment)
    const mergedText = ann.selected_text != null
      ? ann.selected_text + ' ... ' + (newText || '')
      : (newText || '')
    await api.annotations.update(annId, {
      rects_json: JSON.stringify(mergedRects),
      selected_text: mergedText,
    })
    addingRegionTo.value = null
    await loadAnnotations()
    activeAnnotationId.value = annId
  }

  async function deleteRegion(regionIndex) {
    const ann = activeAnnotation.value
    if (!ann) return
    const regions = annotationRegions.value
    if (regionIndex < 0 || regionIndex >= regions.length) return
    if (regions.length <= 1) {
      await deleteAnnotation(ann.id)
      return
    }
    const keyToRemove = regions[regionIndex].groupKey
    const rects = JSON.parse(ann.rects_json || '[]')
    const hasRegion = rects.some(r => r.region != null)

    let newRects
    if (hasRegion) {
      newRects = rects.filter(r => (r.region ?? 0) !== keyToRemove)
      // Re-index remaining regions to be contiguous
      const oldToNew = {}
      let next = 0
      for (const r of newRects) {
        const old = r.region ?? 0
        if (!(old in oldToNew)) { oldToNew[old] = next++ }
      }
      newRects = newRects.map(r => ({ ...r, region: oldToNew[r.region ?? 0] }))
    } else {
      // Legacy: groupKey is a page number
      newRects = rects.filter(r => (r.page || ann.page_number) !== keyToRemove)
    }

    if (newRects.length === 0) {
      await deleteAnnotation(ann.id)
      return
    }

    // Update text segments to match remaining regions
    const texts = (ann.selected_text || '').split(' ... ').map(t => t.trim())
    texts.splice(regionIndex, 1)
    const newText = texts.join(' ... ')

    await updateAnnotation(ann.id, {
      rects_json: JSON.stringify(newRects),
      selected_text: newText,
    })
  }

  function toggleAnnotationCode(codeId) {
    const idx = selectedAnnotationCodes.value.indexOf(codeId)
    if (idx >= 0) {
      selectedAnnotationCodes.value = selectedAnnotationCodes.value.filter(id => id !== codeId)
    } else {
      selectedAnnotationCodes.value = [...selectedAnnotationCodes.value, codeId]
    }
  }

  function cancelAnnotation() {
    window.getSelection()?.removeAllRanges()
    showAnnotationToolbar.value = false
    pendingSelection.value = null
  }

  async function confirmAnnotation() {
    const ui = useUiStore()
    if (!pendingSelection.value || !activePaperId.value) return
    const { text, rects, pageNumber } = pendingSelection.value

    if (addingRegionTo.value) {
      await appendRegionToAnnotation(addingRegionTo.value, rects, pageNumber, text)
      window.getSelection()?.removeAllRanges()
      showAnnotationToolbar.value = false
      pendingSelection.value = null
      ui.showToast('Region added', 'success')
      return
    }

    const taggedRects = rects.map(r => ({ ...r, page: pageNumber }))
    const annType = text ? 'highlight' : 'area'
    const codeIds = [...selectedAnnotationCodes.value]

    await createAnnotation({
      annotation_type: annType,
      page_number: pageNumber,
      selected_text: text,
      rects_json: JSON.stringify(taggedRects),
      code_ids: codeIds,
    })
    window.getSelection()?.removeAllRanges()
    showAnnotationToolbar.value = false
    annotationToolbarSearch.value = ''
    pendingSelection.value = null
  }

  function startAddRegion() {
    if (!activeAnnotation.value) return
    addingRegionTo.value = activeAnnotation.value.id
    const ui = useUiStore()
    ui.showToast('Select text or draw a box to add a region', 'info')
  }

  // Summary
  async function loadPaperSummary() {
    if (!activePaperId.value) return
    paperSummary.value = await api.paperSummary(activePaperId.value)
  }

  // Paper notes
  async function loadPaperNote() {
    if (!activePaperId.value) return
    const data = await api.papers.getNotes(activePaperId.value)
    paperNote.value = data.content || ''
  }

  async function savePaperNote() {
    const ui = useUiStore()
    if (!activePaperId.value) return
    await api.papers.saveNotes(activePaperId.value, paperNote.value)
    ui.showToast('Paper note saved', 'success')
  }

  // PDF upload
  async function uploadPdf(file) {
    const ui = useUiStore()
    if (!file || !activePaperId.value) return
    const formData = new FormData()
    formData.append('pdf', file)
    const data = await api.pdf.upload(activePaperId.value, formData)
    if (data.success) {
      ui.showToast('PDF uploaded', 'success')
      await selectPaper(activePaperId.value)
      await loadPapers()
      await loadStats()
    } else {
      ui.showToast(data.error || 'Upload failed', 'error')
    }
  }

  async function deletePdf() {
    const ui = useUiStore()
    if (!activePaperId.value) return
    await api.pdf.delete(activePaperId.value)
    ui.showToast('PDF deleted', 'success')
    await selectPaper(activePaperId.value)
    await loadPapers()
    await loadStats()
  }

  return {
    // State
    papers, activePaperId, activePaper,
    searchQuery, statusFilter, sortBy, exclusionCodes, stats,
    reviewForm, isReviewDirty,
    annotations, activeAnnotationId, activeAnnotation, annotationRegions,
    pendingSelection, selectedAnnotationCodes, addingRegionTo,
    annotationToolbarSearch, showAnnotationToolbar,
    showCodePicker, codePickerSearch,
    paperNote, paperSummary, currentPaperIndex,
    // Actions
    loadPapers, shufflePapers, loadExclusionCodes, loadStats,
    selectPaper, nextPaper, prevPaper,
    saveReview, setCodingStatus, toggleExclusionCode,
    loadAnnotations, createAnnotation, deleteAnnotation, updateAnnotation,
    addAnnotationCode, removeAnnotationCode,
    saveAnnotationCodeNote, saveAnnotationNote,
    appendRegionToAnnotation, deleteRegion, toggleAnnotationCode,
    cancelAnnotation, confirmAnnotation, startAddRegion,
    loadPaperSummary, loadPaperNote, savePaperNote, uploadPdf, deletePdf,
  }
})
