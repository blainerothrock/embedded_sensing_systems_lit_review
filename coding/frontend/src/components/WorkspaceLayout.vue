<script setup>
import { useUiStore } from '@/stores/ui'
import PaperList from './PaperList.vue'
import PdfViewer from './PdfViewer.vue'
import DetailPanel from './DetailPanel.vue'

const ui = useUiStore()

function startResize(side, event) {
  const startX = event.clientX
  const startWidth = side === 'left' ? ui.leftWidth : ui.rightWidth
  ui.resizing = true

  const onMouseMove = (e) => {
    const dx = e.clientX - startX
    if (side === 'left') {
      ui.leftWidth = Math.max(200, Math.min(600, startWidth + dx))
    } else {
      ui.rightWidth = Math.max(250, Math.min(700, startWidth - dx))
    }
  }

  const onMouseUp = () => {
    ui.resizing = false
    document.removeEventListener('mousemove', onMouseMove)
    document.removeEventListener('mouseup', onMouseUp)
  }

  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup', onMouseUp)
}
</script>

<template>
  <div class="flex h-[calc(100vh-3rem)]">
    <!-- Left Sidebar: Paper List -->
    <div
      class="border-r border-base-300 flex flex-col transition-all duration-200 overflow-hidden"
      :style="ui.sidebarOpen
        ? `width:${ui.leftWidth}px;min-width:200px;max-width:600px`
        : 'width:0px;min-width:0px;border:none'"
    >
      <PaperList />
    </div>

    <!-- Left Resize Handle -->
    <div
      class="resize-handle"
      v-show="ui.sidebarOpen"
      @mousedown="startResize('left', $event)"
    />

    <!-- Center: PDF Viewer -->
    <div class="flex-1 min-w-0 overflow-hidden">
      <PdfViewer />
    </div>

    <!-- Right Resize Handle -->
    <div
      class="resize-handle"
      @mousedown="startResize('right', $event)"
    />

    <!-- Right Sidebar: Detail Panel -->
    <div
      class="bg-base-200 border-l border-base-300 flex flex-col overflow-hidden"
      :style="`width:${ui.rightWidth}px;min-width:250px;max-width:700px`"
    >
      <DetailPanel />
    </div>
  </div>
</template>
