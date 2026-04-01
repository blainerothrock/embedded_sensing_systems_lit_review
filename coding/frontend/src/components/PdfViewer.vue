<script setup>
import { ref, watch, nextTick, onMounted } from 'vue'
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

// Watch for paper selection changes
watch(() => workspace.activePaper, async (paper) => {
  if (!paper) return
  if (paper.pdf_path) {
    await nextTick()
    await pdf.loadPdf(paper.id, pdfPages.value)
    await pdf.fitWidth(pdfContainer.value)
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

  const onMove = (e) => {
    container.scrollLeft = startScrollLeft - (e.clientX - startX)
    container.scrollTop = startScrollTop - (e.clientY - startY)
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
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

async function zoomIn() {
  ui.pdfScale = Math.min(ui.pdfScale + 0.25, 4.0)
  await pdf.renderAllPages(pdfPages.value)
  pdf.renderAnnotationOverlays(workspace.annotations)
}

async function zoomOut() {
  ui.pdfScale = Math.max(ui.pdfScale - 0.25, 0.5)
  await pdf.renderAllPages(pdfPages.value)
  pdf.renderAnnotationOverlays(workspace.annotations)
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
    <!-- PDF Container -->
    <div
      v-if="workspace.activePaper"
      ref="pdfContainer"
      class="flex-1 overflow-auto bg-base-300 p-4"
      :class="{ 'cursor-grab': ui.pdfMode === 'hand' }"
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
    >
      <p class="text-xs font-medium mb-2">Tag annotation with codes:</p>
      <input
        type="text"
        placeholder="Search codes..."
        class="input input-xs input-bordered w-full mb-2"
        v-model="workspace.annotationToolbarSearch"
      >
      <div class="max-h-48 overflow-y-auto space-y-1">
        <template v-for="code in codebook.codes" :key="code.id">
          <div v-if="codebook.codeMatchesSearch(code, workspace.annotationToolbarSearch)">
            <div class="text-xs font-medium opacity-50 px-1 pt-1">{{ code.name }}</div>
            <template v-for="sub in code.children || []" :key="sub.id">
              <label
                v-if="codebook.subCodeMatchesSearch(sub, code, workspace.annotationToolbarSearch)"
                class="flex items-center gap-2 px-2 py-1 rounded cursor-pointer hover:bg-base-300"
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
