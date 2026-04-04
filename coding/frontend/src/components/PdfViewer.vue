<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useCodebookStore } from '@/stores/codebook'
import { usePdf } from '@/composables/usePdf'
import PdfToolbar from './PdfToolbar.vue'
import CodeSelector from './CodeSelector.vue'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const codebook = useCodebookStore()
const pdf = usePdf()

const pdfContainer = ref(null)
const pdfPages = ref(null)
const dragOver = ref(false)
const toolbarSearchInput = ref(null)
const focusedCodeIndex = ref(-1)

// PDF search
const pdfSearchQuery = ref('')
const pdfSearchInput = ref(null)
const searchMatches = ref([])
const currentMatchIndex = ref(-1)
const showSearch = ref(false)

function performSearch() {
  // Clear previous highlights
  document.querySelectorAll('.pdf-search-match').forEach(el => el.classList.remove('pdf-search-match'))
  searchMatches.value = []
  currentMatchIndex.value = -1

  const query = pdfSearchQuery.value.trim().toLowerCase()
  if (!query) return

  const spans = document.querySelectorAll('.textLayer span')
  const matches = []
  spans.forEach(span => {
    if (span.textContent.toLowerCase().includes(query)) {
      span.classList.add('pdf-search-match')
      matches.push(span)
    }
  })
  searchMatches.value = matches
  if (matches.length > 0) {
    currentMatchIndex.value = 0
    scrollToMatch(0)
  }
}

function scrollToMatch(idx) {
  // Remove active highlight from previous
  document.querySelectorAll('.pdf-search-active').forEach(el => el.classList.remove('pdf-search-active'))
  if (idx >= 0 && idx < searchMatches.value.length) {
    const span = searchMatches.value[idx]
    span.classList.add('pdf-search-active')
    span.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

function nextMatch() {
  if (searchMatches.value.length === 0) return
  currentMatchIndex.value = (currentMatchIndex.value + 1) % searchMatches.value.length
  scrollToMatch(currentMatchIndex.value)
}

function prevMatch() {
  if (searchMatches.value.length === 0) return
  currentMatchIndex.value = (currentMatchIndex.value - 1 + searchMatches.value.length) % searchMatches.value.length
  scrollToMatch(currentMatchIndex.value)
}

function clearSearch() {
  pdfSearchQuery.value = ''
  document.querySelectorAll('.pdf-search-match, .pdf-search-active').forEach(el => {
    el.classList.remove('pdf-search-match', 'pdf-search-active')
  })
  searchMatches.value = []
  currentMatchIndex.value = -1
  showSearch.value = false
}

function onSearchKeydown(e) {
  if (e.key === 'Enter' && e.shiftKey) { e.preventDefault(); prevMatch() }
  else if (e.key === 'Enter') { e.preventDefault(); nextMatch() }
  else if (e.key === 'Escape') { clearSearch() }
}

function openSearch() {
  showSearch.value = true
  nextTick(() => pdfSearchInput.value?.focus())
}

onMounted(() => document.addEventListener('pdf-search-open', openSearch))
onUnmounted(() => document.removeEventListener('pdf-search-open', openSearch))

// Flat list of visible codes for keyboard navigation
const visibleCodes = computed(() => {
  const list = []
  for (const code of codebook.codes) {
    if (!codebook.codeMatchesSearch(code, workspace.annotationToolbarSearch)) continue
    list.push({ id: code.id, name: code.name, isParent: true })
    for (const sub of code.children || []) {
      if (codebook.subCodeMatchesSearch(sub, code, workspace.annotationToolbarSearch)) {
        list.push({ id: sub.id, name: sub.name, isParent: false })
      }
    }
  }
  return list
})

// Auto-focus search when toolbar opens
watch(() => workspace.showAnnotationToolbar, (show) => {
  if (show) {
    focusedCodeIndex.value = -1
    nextTick(() => toolbarSearchInput.value?.focus())
  }
})

function onToolbarKeydown(e) {
  const codes = visibleCodes.value
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    focusedCodeIndex.value = Math.min(focusedCodeIndex.value + 1, codes.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    focusedCodeIndex.value = Math.max(focusedCodeIndex.value - 1, -1)
  } else if (e.key === ' ' && focusedCodeIndex.value >= 0) {
    e.preventDefault()
    workspace.toggleAnnotationCode(codes[focusedCodeIndex.value].id)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    workspace.confirmAnnotation()
  }
}

// Watch for paper changes (watches the object so re-fetch after upload triggers it)
watch(() => workspace.activePaper, async (paper) => {
  if (!paper) return
  await nextTick()
  if (!pdfPages.value) return
  if (paper.pdf_path) {
    await pdf.loadPdf(paper.id, pdfPages.value)
    if (!ui.userSetZoom) await pdf.fitWidth(pdfContainer.value)
    await pdf.renderAllPages(pdfPages.value)
    pdf.renderAnnotationOverlays(workspace.annotations)
  } else {
    pdf.clearPdf(pdfPages.value)
  }
})

// Re-render annotation overlays when annotations change
watch(() => workspace.annotations, () => {
  if (Object.keys(pdf.pageViewports.value).length > 0) {
    pdf.renderAnnotationOverlays(workspace.annotations)
  }
}, { deep: true })

function onMouseDown(event) {
  if (ui.pdfMode === 'hand') {
    startHandPan(event)
  } else if (ui.pdfMode === 'box') {
    onBoxMouseDown(event)
  }
}

function startHandPan(event) {
  if (!pdfContainer.value) return
  const container = pdfContainer.value
  const startX = event.clientX
  const startY = event.clientY
  const startScrollLeft = container.scrollLeft
  const startScrollTop = container.scrollTop
  let moved = false

  const onMove = (e) => {
    const dx = Math.abs(e.clientX - startX)
    const dy = Math.abs(e.clientY - startY)
    if (dx > 3 || dy > 3) moved = true
    container.scrollLeft = startScrollLeft - (e.clientX - startX)
    container.scrollTop = startScrollTop - (e.clientY - startY)
  }
  const onUp = (e) => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    if (!moved) checkAnnotationClick(e)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  event.preventDefault()
}

function onTextSelection(event) {
  if (ui.pdfMode !== 'text') return
  if (workspace.showAnnotationToolbar) return

  const sel = window.getSelection()
  if (!sel || sel.isCollapsed || !sel.toString().trim()) {
    checkAnnotationClick(event)
    return
  }

  const text = sel.toString().trim()
  const range = sel.getRangeAt(0)
  const clientRects = range.getClientRects()
  if (clientRects.length === 0) return

  const pageDiv = sel.anchorNode?.parentElement?.closest('.pdf-page')
  if (!pageDiv) return
  const pageNumber = parseInt(pageDiv.dataset.page)
  const viewport = pdf.getViewport(pageNumber)
  if (!viewport) return

  const pageBounds = pageDiv.getBoundingClientRect()
  const pdfRects = []
  for (const cr of clientRects) {
    const relX = cr.left - pageBounds.left
    const relY = cr.top - pageBounds.top
    const [px1, py1] = viewport.convertToPdfPoint(relX, relY)
    const [px2, py2] = viewport.convertToPdfPoint(relX + cr.width, relY + cr.height)
    pdfRects.push({
      x: Math.min(px1, px2),
      y: Math.min(py1, py2),
      w: Math.abs(px2 - px1),
      h: Math.abs(py2 - py1),
    })
  }

  // If adding region to existing annotation, skip the code picker
  if (workspace.addingRegionTo) {
    workspace.appendRegionToAnnotation(workspace.addingRegionTo, pdfRects, pageNumber, text)
    window.getSelection()?.removeAllRanges()
    return
  }

  workspace.pendingSelection = { text, rects: pdfRects, pageNumber }
  workspace.selectedAnnotationCodes = []
  workspace.showAnnotationToolbar = true
}

function checkAnnotationClick(event) {
  const pageDiv = event.target.closest('.pdf-page')
  if (!pageDiv) return
  const pageNumber = parseInt(pageDiv.dataset.page)
  const viewport = pdf.getViewport(pageNumber)
  if (!viewport) return

  const pageBounds = pageDiv.getBoundingClientRect()
  const clickX = event.clientX - pageBounds.left
  const clickY = event.clientY - pageBounds.top
  const [pdfX, pdfY] = viewport.convertToPdfPoint(clickX, clickY)

  for (const ann of workspace.annotations) {
    const rects = JSON.parse(ann.rects_json || '[]')
    for (const rect of rects) {
      const rPage = rect.page || ann.page_number
      if (rPage !== pageNumber) continue
      const minX = rect.x, maxX = rect.x + rect.w
      const minY = Math.min(rect.y, rect.y + rect.h)
      const maxY = Math.max(rect.y, rect.y + rect.h)
      if (pdfX >= minX && pdfX <= maxX && pdfY >= minY && pdfY <= maxY) {
        ui.rightTab = 'annotations'
        workspace.activeAnnotationId = ann.id
        pdf.scrollToAnnotation(ann)
        return
      }
    }
  }
}

function onBoxMouseDown(event) {
  const pageDiv = event.target.closest('.pdf-page')
  if (!pageDiv) return

  const pageBounds = pageDiv.getBoundingClientRect()
  const startX = event.clientX - pageBounds.left
  const startY = event.clientY - pageBounds.top
  const pageNumber = parseInt(pageDiv.dataset.page)

  const box = document.createElement('div')
  box.className = 'pdf-box-drawing'
  box.style.left = startX + 'px'
  box.style.top = startY + 'px'
  const overlay = pageDiv.querySelector('.pdf-annotation-layer')
  if (overlay) overlay.appendChild(box)

  const onMove = (e) => {
    const curX = e.clientX - pageBounds.left
    const curY = e.clientY - pageBounds.top
    box.style.left = Math.min(startX, curX) + 'px'
    box.style.top = Math.min(startY, curY) + 'px'
    box.style.width = Math.abs(curX - startX) + 'px'
    box.style.height = Math.abs(curY - startY) + 'px'
  }

  const onUp = (e) => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    box.remove()

    const endX = e.clientX - pageBounds.left
    const endY = e.clientY - pageBounds.top
    if (Math.abs(endX - startX) < 10 || Math.abs(endY - startY) < 10) {
      ui.setPdfMode('text')
      return
    }

    const viewport = pdf.getViewport(pageNumber)
    if (!viewport) return

    const [px1, py1] = viewport.convertToPdfPoint(Math.min(startX, endX), Math.min(startY, endY))
    const [px2, py2] = viewport.convertToPdfPoint(Math.max(startX, endX), Math.max(startY, endY))

    const pdfRects = [{
      page: pageNumber,
      x: Math.min(px1, px2),
      y: Math.min(py1, py2),
      w: Math.abs(px2 - px1),
      h: Math.abs(py2 - py1),
    }]

    if (workspace.addingRegionTo) {
      workspace.appendRegionToAnnotation(workspace.addingRegionTo, pdfRects, pageNumber, null)
    } else {
      workspace.pendingSelection = { text: null, rects: pdfRects, pageNumber }
      workspace.selectedAnnotationCodes = []
      workspace.showAnnotationToolbar = true
    }
    ui.setPdfMode('text')
  }

  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
  event.preventDefault()
}

function onWheel(event) {
  if (event.ctrlKey || event.metaKey) {
    event.preventDefault()
    pdf.onWheel(event, pdfContainer.value)
  }
}

function onScroll() {
  pdf.onScroll(pdfContainer.value)
}

function captureViewCenter() {
  const c = pdfContainer.value
  if (!c) return null
  return {
    contentX: (c.scrollLeft + c.clientWidth / 2) / ui.pdfScale,
    contentY: (c.scrollTop + c.clientHeight / 2) / ui.pdfScale,
  }
}

function restoreViewCenter(anchor) {
  if (!anchor || !pdfContainer.value) return
  const c = pdfContainer.value
  c.scrollLeft = anchor.contentX * ui.pdfScale - c.clientWidth / 2
  c.scrollTop = anchor.contentY * ui.pdfScale - c.clientHeight / 2
}

async function zoomIn() {
  ui.userSetZoom = true
  const anchor = captureViewCenter()
  ui.pdfScale = Math.min(ui.pdfScale + 0.25, 4.0)
  await pdf.renderAllPages(pdfPages.value)
  pdf.renderAnnotationOverlays(workspace.annotations)
  restoreViewCenter(anchor)
}

async function zoomOut() {
  ui.userSetZoom = true
  const anchor = captureViewCenter()
  ui.pdfScale = Math.max(ui.pdfScale - 0.25, 0.5)
  await pdf.renderAllPages(pdfPages.value)
  pdf.renderAnnotationOverlays(workspace.annotations)
  restoreViewCenter(anchor)
}

async function fitWidth() {
  await pdf.fitWidth(pdfContainer.value)
  await pdf.renderAllPages(pdfPages.value)
  pdf.renderAnnotationOverlays(workspace.annotations)
}

function handleDrop(event) {
  dragOver.value = false
  const files = event.dataTransfer.files
  if (files.length > 0 && workspace.activePaperId) {
    workspace.uploadPdf(files[0])
  }
}

function handleFileInput(event) {
  const file = event.target.files[0]
  if (file) workspace.uploadPdf(file)
}
</script>

<template>
  <div class="relative h-full flex flex-col">
    <!-- Adding region banner -->
    <div
      v-if="workspace.addingRegionTo"
      class="bg-warning text-warning-content px-3 py-1.5 text-xs font-medium flex items-center justify-center gap-2 shrink-0 z-20"
    >
      Adding region — select text or draw a box
      <button class="btn btn-xs btn-ghost" @click="workspace.addingRegionTo = null">Cancel</button>
    </div>

    <!-- PDF Search bar -->
    <div v-if="showSearch" class="flex items-center gap-2 px-3 py-1.5 bg-base-200 border-b border-base-300 shrink-0">
      <input
        ref="pdfSearchInput"
        type="text"
        class="input input-xs flex-1"
        placeholder="Search in PDF..."
        v-model="pdfSearchQuery"
        @input="performSearch()"
        @keydown="onSearchKeydown"
      >
      <span class="text-xs opacity-50 min-w-12 text-center">
        {{ searchMatches.length > 0 ? `${currentMatchIndex + 1}/${searchMatches.length}` : '0/0' }}
      </span>
      <button class="btn btn-ghost btn-xs btn-square" @click="prevMatch()" title="Previous (Shift+Enter)">▲</button>
      <button class="btn btn-ghost btn-xs btn-square" @click="nextMatch()" title="Next (Enter)">▼</button>
      <button class="btn btn-ghost btn-xs btn-square" @click="clearSearch()">✕</button>
    </div>

    <!-- PDF Container -->
    <div
      v-if="workspace.activePaper"
      ref="pdfContainer"
      class="flex-1 overflow-auto bg-base-300 p-4"
      :class="{ 'cursor-grab': ui.pdfMode === 'hand', 'cursor-copy': workspace.addingRegionTo }"
      @mousedown="onMouseDown"
      @mouseup="onTextSelection"
      @wheel="onWheel"
      @scroll="onScroll"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="handleDrop"
    >
      <div ref="pdfPages"></div>

      <!-- No PDF state -->
      <div
        v-if="workspace.activePaper && !workspace.activePaper.pdf_path"
        class="flex flex-col items-center justify-center h-full gap-4"
      >
        <p class="text-lg opacity-50">No PDF uploaded</p>
        <label class="btn btn-primary btn-sm gap-2">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-9L12 3m0 0 4.5 4.5M12 3v13.5"/>
          </svg>
          Upload PDF
          <input type="file" accept=".pdf" class="hidden" @change="handleFileInput">
        </label>
        <p class="text-xs opacity-40">or drag & drop a PDF file</p>
      </div>

      <!-- Drop overlay -->
      <div
        v-if="dragOver"
        class="absolute inset-0 bg-primary/10 border-2 border-dashed border-primary rounded flex items-center justify-center z-30"
      >
        <p class="text-primary font-medium">Drop PDF here</p>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="flex-1 flex items-center justify-center bg-base-300">
      <p class="text-lg opacity-50">Select a paper to view</p>
    </div>

    <!-- Annotation toolbar (code picker for new annotation) -->
    <div
      v-if="workspace.showAnnotationToolbar"
      class="absolute top-4 left-1/2 -translate-x-1/2 z-30 bg-base-200 rounded-lg border border-base-300 shadow-xl p-3 w-72"
      @keydown="onToolbarKeydown"
    >
      <p class="text-xs font-medium mb-2">Tag annotation with codes:</p>
      <input
        ref="toolbarSearchInput"
        type="text"
        placeholder="Search codes... (↑↓ navigate, space toggle, enter save)"
        class="input input-xs input-bordered w-full mb-2"
        v-model="workspace.annotationToolbarSearch"
      >
      <div class="max-h-48 overflow-y-auto space-y-1">
        <template v-for="code in codebook.codes" :key="code.id">
          <div v-if="codebook.codeMatchesSearch(code, workspace.annotationToolbarSearch)">
            <label
              class="flex items-center gap-2 px-1 pt-1 rounded cursor-pointer hover:bg-base-300"
              :class="{ 'bg-base-300': visibleCodes[focusedCodeIndex]?.id === code.id }"
            >
              <input
                type="checkbox"
                class="checkbox checkbox-xs"
                :checked="workspace.selectedAnnotationCodes.includes(code.id)"
                @change="workspace.toggleAnnotationCode(code.id)"
              >
              <span
                class="w-2 h-2 rounded-full"
                :style="{ background: code.color || '#888' }"
              ></span>
              <span class="text-xs font-medium">{{ code.name }}</span>
            </label>
            <template v-for="sub in code.children || []" :key="sub.id">
              <label
                v-if="codebook.subCodeMatchesSearch(sub, code, workspace.annotationToolbarSearch)"
                class="flex items-center gap-2 px-2 py-1 pl-6 rounded cursor-pointer hover:bg-base-300"
                :class="{ 'bg-base-300': visibleCodes[focusedCodeIndex]?.id === sub.id }"
              >
                <input
                  type="checkbox"
                  class="checkbox checkbox-xs"
                  :checked="workspace.selectedAnnotationCodes.includes(sub.id)"
                  @change="workspace.toggleAnnotationCode(sub.id)"
                >
                <span
                  class="w-2 h-2 rounded-full"
                  :style="{ background: sub.color || '#888' }"
                ></span>
                <span class="text-xs">{{ sub.name }}</span>
              </label>
            </template>
          </div>
        </template>
      </div>
      <div class="flex gap-2 mt-2">
        <button class="btn btn-xs btn-primary flex-1" @click="workspace.confirmAnnotation()">Save</button>
        <button class="btn btn-xs btn-ghost flex-1" @click="workspace.cancelAnnotation()">Cancel</button>
      </div>
    </div>

    <!-- PDF Toolbar -->
    <PdfToolbar
      :page-count="pdf.pageCount.value"
      :current-page="pdf.currentPage.value"
      @zoom-in="zoomIn"
      @zoom-out="zoomOut"
      @fit-width="fitWidth"
    />
  </div>
</template>
