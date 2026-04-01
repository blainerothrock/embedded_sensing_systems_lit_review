<script setup>
import { onMounted, watch } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useCodebookStore } from '@/stores/codebook'
import { useMatrixStore } from '@/stores/matrix'
import { useKeyboard } from '@/composables/useKeyboard'
import AppNavbar from '@/components/AppNavbar.vue'
import WorkspaceLayout from '@/components/WorkspaceLayout.vue'
import MatrixView from '@/components/MatrixView.vue'
import ThemesView from '@/components/ThemesView.vue'
import CodeBuilderModal from '@/components/CodeBuilderModal.vue'
import ColumnEditorModal from '@/components/ColumnEditorModal.vue'
import ToastContainer from '@/components/ToastContainer.vue'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const codebook = useCodebookStore()
const matrix = useMatrixStore()

useKeyboard()

onMounted(async () => {
  await Promise.all([
    workspace.loadPapers(),
    workspace.loadExclusionCodes(),
    workspace.loadStats(),
    codebook.loadCodes(),
    codebook.loadUsageCounts(),
    matrix.loadColumns(),
  ])
})

watch(() => ui.theme, (theme) => {
  document.documentElement.setAttribute('data-theme', theme)
}, { immediate: true })
</script>

<template>
  <div
    :class="{
      'mode-hand': ui.pdfMode === 'hand',
      'mode-text': ui.pdfMode === 'text',
      'mode-box': ui.pdfMode === 'box',
      'resizing': ui.resizing,
    }"
  >
    <AppNavbar />
    <WorkspaceLayout v-if="ui.view === 'papers'" />
    <MatrixView v-else-if="ui.view === 'matrix'" />
    <ThemesView v-else-if="ui.view === 'themes'" />
    <CodeBuilderModal />
    <ColumnEditorModal />
    <ToastContainer />
  </div>
</template>
