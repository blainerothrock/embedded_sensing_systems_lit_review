import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api } from '@/api'

let saveTimer = null
let loading = false

export const useUiStore = defineStore('ui', () => {
  // View
  const view = ref('papers') // 'papers' | 'matrix' | 'themes'
  const rightTab = ref('details') // 'details' | 'annotations' | 'summary' | 'matrix'

  // Theme
  const theme = ref('dark')

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  // Layout
  const sidebarOpen = ref(true)
  const leftWidth = ref(280)
  const rightWidth = ref(320)
  const resizing = ref(false)

  // Chat panel (persistent bottom split)
  const chatOpen = ref(true)
  const chatHeight = ref(300)

  function toggleChat() {
    chatOpen.value = !chatOpen.value
  }

  // PDF mode
  const pdfMode = ref('hand') // 'hand' | 'text' | 'box'
  const pdfScale = ref(1.5)
  const userSetZoom = ref(false)

  function setPdfMode(mode) {
    pdfMode.value = mode
  }

  // Modals
  const showCodeManager = ref(false)
  const showColumnEditor = ref(false)

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

  // Persistent settings keys
  const SETTINGS_KEYS = ['theme', 'sidebarOpen', 'leftWidth', 'rightWidth', 'pdfMode', 'pdfScale', 'rightTab', 'chatOpen', 'chatHeight']

  function debouncedSave() {
    if (loading) return
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      const data = {}
      for (const key of SETTINGS_KEYS) {
        const val = { theme, sidebarOpen, leftWidth, rightWidth, pdfMode, pdfScale, rightTab, chatOpen, chatHeight }[key]
        data[key] = String(val.value)
      }
      api.settings.save(data).catch(() => {})
    }, 500)
  }

  // Watch all persisted settings and debounce-save to backend
  for (const key of SETTINGS_KEYS) {
    const val = { theme, sidebarOpen, leftWidth, rightWidth, pdfMode, pdfScale, rightTab, chatOpen, chatHeight }[key]
    watch(val, () => debouncedSave())
  }

  async function loadSettings() {
    loading = true
    try {
      const settings = await api.settings.get()
      if (settings.theme) theme.value = settings.theme
      if (settings.sidebarOpen !== undefined) sidebarOpen.value = settings.sidebarOpen !== 'false'
      if (settings.leftWidth) leftWidth.value = parseInt(settings.leftWidth) || 280
      if (settings.rightWidth) rightWidth.value = parseInt(settings.rightWidth) || 320
      if (settings.pdfMode) pdfMode.value = settings.pdfMode
      if (settings.pdfScale) {
        pdfScale.value = parseFloat(settings.pdfScale) || 1.5
        userSetZoom.value = true
      }
      if (settings.rightTab) rightTab.value = settings.rightTab
      if (settings.chatOpen !== undefined) chatOpen.value = settings.chatOpen !== 'false'
      if (settings.chatHeight) chatHeight.value = parseInt(settings.chatHeight) || 300
    } catch {
      // Settings not available yet, use defaults
    }
    loading = false
  }

  return {
    view, rightTab,
    theme, toggleTheme,
    sidebarOpen, leftWidth, rightWidth, resizing,
    chatOpen, chatHeight, toggleChat,
    pdfMode, pdfScale, userSetZoom, setPdfMode,
    showCodeManager, showColumnEditor,
    toasts, showToast,
    setView, loadSettings,
  }
})
