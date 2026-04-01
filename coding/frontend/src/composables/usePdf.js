import { shallowRef, ref } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'

let pdfjsLib = null

async function ensurePdfJs() {
  if (pdfjsLib) return pdfjsLib
  pdfjsLib = await import('pdfjs-dist')
  pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
    'pdfjs-dist/build/pdf.worker.min.mjs',
    import.meta.url
  ).href
  return pdfjsLib
}

export function usePdf() {
  const pdfDoc = shallowRef(null)
  const pageViewports = shallowRef({})
  const pageCount = ref(0)
  const currentPage = ref(1)
  const rendering = ref(false)

  let zoomRenderTimer = null
  let zoomAnchor = null

  async function loadPdf(docId, containerEl) {
    if (!containerEl) return
    containerEl.innerHTML = ''
    pdfDoc.value = null
    pageCount.value = 0
    currentPage.value = 1
    rendering.value = false

    try {
      const pdfjs = await ensurePdfJs()
      const loadingTask = pdfjs.getDocument(`/api/papers/${docId}/pdf`)
      pdfDoc.value = await loadingTask.promise
      pageCount.value = pdfDoc.value.numPages
    } catch (err) {
      console.error('Failed to load PDF:', err)
      const ui = useUiStore()
      ui.showToast('Failed to load PDF', 'error')
    }
  }

  function clearPdf(containerEl) {
    if (containerEl) containerEl.innerHTML = ''
    pdfDoc.value = null
    pageViewports.value = {}
    pageCount.value = 0
    currentPage.value = 1
  }

  async function renderAllPages(containerEl) {
    const ui = useUiStore()
    if (!pdfDoc.value || rendering.value) return
    rendering.value = true

    containerEl.innerHTML = ''
    const newViewports = {}

    for (let i = 1; i <= pdfDoc.value.numPages; i++) {
      const page = await pdfDoc.value.getPage(i)
      const viewport = page.getViewport({ scale: ui.pdfScale })
      newViewports[i] = viewport

      const pageDiv = document.createElement('div')
      pageDiv.className = 'pdf-page mb-2 shadow-lg'
      pageDiv.dataset.page = i
      pageDiv.style.width = viewport.width + 'px'
      pageDiv.style.height = viewport.height + 'px'
      pageDiv.style.position = 'relative'

      const canvas = document.createElement('canvas')
      canvas.width = viewport.width * window.devicePixelRatio
      canvas.height = viewport.height * window.devicePixelRatio
      canvas.style.width = viewport.width + 'px'
      canvas.style.height = viewport.height + 'px'

      const ctx = canvas.getContext('2d')
      ctx.scale(window.devicePixelRatio, window.devicePixelRatio)

      pageDiv.appendChild(canvas)
      containerEl.appendChild(pageDiv)

      await page.render({ canvasContext: ctx, viewport }).promise

      // Text layer
      const textContent = await page.getTextContent()
      const textLayerDiv = document.createElement('div')
      textLayerDiv.className = 'textLayer'
      textLayerDiv.style.setProperty('--scale-factor', viewport.scale)
      textLayerDiv.style.setProperty('--total-scale-factor', viewport.scale)
      textLayerDiv.style.setProperty('--scale-round-x', '1px')
      textLayerDiv.style.setProperty('--scale-round-y', '1px')
      pageDiv.appendChild(textLayerDiv)

      const textLayer = new pdfjsLib.TextLayer({
        textContentSource: textContent,
        container: textLayerDiv,
        viewport,
      })
      textLayer.render()

      // Annotation overlay
      const annotOverlay = document.createElement('div')
      annotOverlay.className = 'pdf-annotation-layer'
      annotOverlay.style.width = viewport.width + 'px'
      annotOverlay.style.height = viewport.height + 'px'
      pageDiv.appendChild(annotOverlay)
    }

    pageViewports.value = newViewports
    rendering.value = false
  }

  function renderAnnotationOverlays(annotations) {
    document.querySelectorAll('.pdf-annotation-layer').forEach(el => el.innerHTML = '')

    for (const ann of annotations) {
      const rects = JSON.parse(ann.rects_json || '[]')
      const color = ann.codes?.[0]?.color || '#FFEB3B'
      const isArea = ann.annotation_type === 'area'

      for (const rect of rects) {
        const pageNum = rect.page || ann.page_number
        const viewport = pageViewports.value[pageNum]
        if (!viewport) continue
        const overlay = document.querySelector(
          `.pdf-page[data-page="${pageNum}"] .pdf-annotation-layer`
        )
        if (!overlay) continue

        const [vx1, vy1] = viewport.convertToViewportPoint(rect.x, rect.y)
        const [vx2, vy2] = viewport.convertToViewportPoint(rect.x + rect.w, rect.y + rect.h)

        const el = document.createElement('div')
        el.className = isArea ? 'pdf-area' : 'pdf-highlight'
        el.dataset.annotationId = ann.id
        el.style.left = Math.min(vx1, vx2) + 'px'
        el.style.top = Math.min(vy1, vy2) + 'px'
        el.style.width = Math.abs(vx2 - vx1) + 'px'
        el.style.height = Math.abs(vy2 - vy1) + 'px'

        if (isArea) {
          el.style.border = `2px dashed ${color}`
          el.style.backgroundColor = color + '10'
        } else {
          el.style.backgroundColor = color + '30'
          el.style.borderBottom = `1px solid ${color}80`
        }
        el.title = ann.selected_text?.substring(0, 80) || ann.note?.substring(0, 80) || ''
        overlay.appendChild(el)
      }
    }
  }

  async function fitWidth(containerEl) {
    if (!pdfDoc.value) return
    const ui = useUiStore()
    const page = await pdfDoc.value.getPage(1)
    const containerWidth = containerEl.clientWidth - 40
    const viewport = page.getViewport({ scale: 1.0 })
    ui.pdfScale = containerWidth / viewport.width
  }

  function onScroll(containerEl) {
    const pages = containerEl.querySelectorAll('.pdf-page')
    const scrollTop = containerEl.scrollTop + containerEl.clientHeight / 3
    for (const page of pages) {
      if (page.offsetTop + page.offsetHeight > scrollTop) {
        currentPage.value = parseInt(page.dataset.page)
        break
      }
    }
  }

  function onWheel(event, containerEl) {
    const ui = useUiStore()
    if (!pdfDoc.value) return
    const delta = event.deltaY > 0 ? -0.1 : 0.1
    const oldScale = ui.pdfScale
    const newScale = Math.min(Math.max(oldScale + delta, 0.5), 4.0)
    if (newScale === oldScale) return

    if (!zoomAnchor) {
      const rect = containerEl.getBoundingClientRect()
      const cursorX = event.clientX - rect.left
      const cursorY = event.clientY - rect.top
      zoomAnchor = {
        contentX: (containerEl.scrollLeft + cursorX) / oldScale,
        contentY: (containerEl.scrollTop + cursorY) / oldScale,
        cursorX,
        cursorY,
      }
    }

    ui.pdfScale = newScale
    clearTimeout(zoomRenderTimer)
    zoomRenderTimer = setTimeout(async () => {
      const anchor = zoomAnchor
      zoomAnchor = null
      await renderAllPages(containerEl)
      const workspace = useWorkspaceStore()
      renderAnnotationOverlays(workspace.annotations)
      if (anchor) {
        containerEl.scrollLeft = anchor.contentX * ui.pdfScale - anchor.cursorX
        containerEl.scrollTop = anchor.contentY * ui.pdfScale - anchor.cursorY
      }
    }, 100)
  }

  function getViewport(pageNum) {
    return pageViewports.value[pageNum]
  }

  function scrollToPage(pageNum) {
    const pageDiv = document.querySelector(`.pdf-page[data-page="${pageNum}"]`)
    if (pageDiv) pageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  function scrollToAnnotation(ann) {
    const pageDiv = document.querySelector(`.pdf-page[data-page="${ann.page_number}"]`)
    if (pageDiv) pageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return {
    pdfDoc, pageViewports, pageCount, currentPage, rendering,
    loadPdf, clearPdf, renderAllPages, renderAnnotationOverlays,
    fitWidth, onScroll, onWheel, getViewport,
    scrollToPage, scrollToAnnotation,
  }
}
