<script setup>
import { useUiStore } from '@/stores/ui'

const ui = useUiStore()

const emit = defineEmits(['zoom-in', 'zoom-out', 'fit-width'])

defineProps({
  pageCount: { type: Number, default: 0 },
  currentPage: { type: Number, default: 1 },
})
</script>

<template>
  <div
    v-show="pageCount > 0"
    class="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 bg-base-300 rounded-lg border border-base-200 flex items-center gap-1 px-2 py-1.5 shadow-lg"
  >
    <!-- Mode buttons -->
    <button
      class="btn btn-xs gap-1"
      :class="ui.pdfMode === 'hand' ? 'btn-primary' : 'btn-ghost opacity-60'"
      @click="ui.setPdfMode('hand')"
      title="Hand mode (H)"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0m0 0V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v4"/><path d="M6 14v1a6 6 0 0 0 12 0v-4"/>
      </svg>
      Hand
    </button>
    <button
      class="btn btn-xs gap-1"
      :class="ui.pdfMode === 'text' ? 'btn-primary' : 'btn-ghost opacity-60'"
      @click="ui.setPdfMode('text')"
      title="Text select (T)"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/>
      </svg>
      Text
    </button>
    <button
      class="btn btn-xs gap-1"
      :class="ui.pdfMode === 'box' ? 'btn-primary' : 'btn-ghost opacity-60'"
      @click="ui.setPdfMode('box')"
      title="Box select (B)"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <rect x="3" y="3" width="18" height="18" rx="2"/>
      </svg>
      Box
    </button>

    <div class="w-px h-5 bg-base-content/10 mx-1"></div>

    <!-- Zoom -->
    <button class="btn btn-xs btn-ghost btn-square opacity-60" @click="emit('zoom-out')">−</button>
    <span class="text-xs opacity-60 w-10 text-center font-mono">{{ Math.round(ui.pdfScale * 100) }}%</span>
    <button class="btn btn-xs btn-ghost btn-square opacity-60" @click="emit('zoom-in')">+</button>
    <button class="btn btn-xs btn-ghost btn-square opacity-60" @click="emit('fit-width')" title="Fit width">
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/>
      </svg>
    </button>

    <div class="w-px h-5 bg-base-content/10 mx-1"></div>

    <!-- Page indicator -->
    <span class="text-xs opacity-40 font-mono">p.{{ currentPage }}/{{ pageCount }}</span>
  </div>
</template>
