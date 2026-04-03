import { onMounted, onUnmounted } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'

export function useKeyboard() {
  const ui = useUiStore()
  const workspace = useWorkspaceStore()

  function handler(e) {
    const tag = e.target.tagName
    const isTyping = tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
      || e.target.isContentEditable || e.target.closest('[contenteditable="true"]')

    // Escape cascade
    if (e.key === 'Escape') {
      if (workspace.showCodePicker) { workspace.showCodePicker = false; return }
      if (workspace.showAnnotationToolbar) { workspace.cancelAnnotation(); return }
      if (workspace.activeAnnotationId) { workspace.activeAnnotationId = null; return }
      if (ui.showCodeManager) { ui.showCodeManager = false; return }
      if (ui.showColumnEditor) { ui.showColumnEditor = false; return }
    }

    // Ctrl+S / Cmd+S
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
      e.preventDefault()
      workspace.saveReview()
      return
    }

    // Ctrl+F / Cmd+F — PDF search
    if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
      e.preventDefault()
      document.dispatchEvent(new CustomEvent('pdf-search-open'))
      return
    }

    if (isTyping) return

    // Mode shortcuts
    if (e.key === 'h' || e.key === 'H') { ui.setPdfMode('hand'); e.preventDefault() }
    if (e.key === 't' || e.key === 'T') { ui.setPdfMode('text'); e.preventDefault() }
    if (e.key === 'b' || e.key === 'B') { ui.setPdfMode('box'); e.preventDefault() }

    // Paper navigation
    if (e.key === 'ArrowLeft' || e.key === 'j' || e.key === 'J') { workspace.prevPaper(); e.preventDefault() }
    if (e.key === 'ArrowRight' || e.key === 'k' || e.key === 'K') { workspace.nextPaper(); e.preventDefault() }
  }

  onMounted(() => document.addEventListener('keydown', handler))
  onUnmounted(() => document.removeEventListener('keydown', handler))
}
