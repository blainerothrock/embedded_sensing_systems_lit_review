import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useUiStore = defineStore('ui', () => {
  // View
  const view = ref('papers') // 'papers' | 'matrix' | 'themes'
  const rightTab = ref('details') // 'details' | 'annotations' | 'summary' | 'matrix'

  // Theme
  const theme = ref(localStorage.getItem('theme') || 'dark')
  watch(theme, (v) => localStorage.setItem('theme', v))

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  // Layout
  const sidebarOpen = ref(true)
  const leftWidth = ref(parseInt(localStorage.getItem('leftWidth')) || 280)
  const rightWidth = ref(parseInt(localStorage.getItem('rightWidth')) || 320)
  const resizing = ref(false)

  watch(leftWidth, (v) => localStorage.setItem('leftWidth', v))
  watch(rightWidth, (v) => localStorage.setItem('rightWidth', v))

  // PDF mode
  const pdfMode = ref('hand') // 'hand' | 'text' | 'box'
  const pdfScale = ref(1.5)

  function setPdfMode(mode) {
    pdfMode.value = mode
  }

  // Modals
  const showCodeManager = ref(false)
  const showColumnEditor = ref(false)
  const showChat = ref(false)

  // Toasts
  const toasts = ref([])
  let toastId = 0

  function showToast(message, type = 'info', duration = 3000) {
    const id = ++toastId
    toasts.value.push({ id, message, type })
    if (duration > 0) {
      setTimeout(() => {
        toasts.value = toasts.value.filter(t => t.id !== id)
      }, duration)
    }
  }

  function setView(v) {
    view.value = v
  }

  return {
    view, rightTab,
    theme, toggleTheme,
    sidebarOpen, leftWidth, rightWidth, resizing,
    pdfMode, pdfScale, setPdfMode,
    showCodeManager, showColumnEditor, showChat,
    toasts, showToast,
    setView,
  }
})
