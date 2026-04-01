<script setup>
import { ref, computed, watch } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useCodebookStore } from '@/stores/codebook'
import { useMatrixStore } from '@/stores/matrix'
import { api } from '@/api'
import { marked } from 'marked'
import DetailPanel from './DetailPanel.vue'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const codebook = useCodebookStore()
const matrix = useMatrixStore()

const selectedCodeId = ref(null)
const themesAnnotations = ref([])
const selectedAnnId = ref(null)
const rightWidth = ref(350)

const selectedAnn = computed(() => {
  if (!selectedAnnId.value) return null
  return themesAnnotations.value.find(a => a.id === selectedAnnId.value) || null
})

async function loadThemes(codeId) {
  selectedCodeId.value = codeId
  themesAnnotations.value = await api.themes(codeId)
}

async function selectAnnotation(ann) {
  selectedAnnId.value = ann.id
  // Load the paper in the workspace store so DetailPanel can show it
  if (!workspace.activePaperId || workspace.activePaperId !== ann.document_id) {
    await workspace.selectPaper(ann.document_id, true)
  }
  // Open the annotation in detail panel
  workspace.activeAnnotationId = ann.id
  ui.rightTab = 'annotations'
}

function renderMd(text) {
  if (!text) return ''
  return marked.parse(text)
}

// Resize
function startResize(event) {
  const startX = event.clientX
  const startW = rightWidth.value
  const onMove = (e) => {
    rightWidth.value = Math.max(250, Math.min(600, startW - (e.clientX - startX)))
  }
  const onUp = () => {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
  }
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}
</script>

<template>
  <div class="flex h-[calc(100vh-3rem)]">
    <!-- Left: Code tree -->
    <div class="w-64 bg-base-200 border-r border-base-300 overflow-y-auto p-3 space-y-1 shrink-0">
      <h3 class="text-sm font-semibold uppercase opacity-70 mb-2">Codes</h3>
      <template v-for="code in codebook.codes" :key="code.id">
        <div
          class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer hover:bg-base-300"
          :class="{ 'bg-base-300': selectedCodeId === code.id }"
          @click="loadThemes(code.id)"
        >
          <div class="w-3 h-3 rounded-full flex-shrink-0" :style="{ background: code.color }"></div>
          <span class="text-sm flex-1">{{ code.name }}</span>
          <span class="badge badge-xs badge-ghost">{{ codebook.codeUsageCounts[code.id] || 0 }}</span>
        </div>
        <div
          v-for="sub in code.children || []"
          :key="sub.id"
          class="flex items-center gap-2 px-2 py-1 rounded cursor-pointer hover:bg-base-300 ml-4"
          :class="{ 'bg-base-300': selectedCodeId === sub.id }"
          @click="loadThemes(sub.id)"
        >
          <div class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: sub.color }"></div>
          <span class="text-xs flex-1">{{ sub.name }}</span>
          <span class="badge badge-xs badge-ghost">{{ codebook.codeUsageCounts[sub.id] || 0 }}</span>
        </div>
      </template>
    </div>

    <!-- Center: Annotations for selected code -->
    <div class="flex-1 min-w-0 overflow-y-auto p-4 space-y-3">
      <div v-if="!selectedCodeId" class="flex items-center justify-center h-full">
        <p class="text-sm opacity-50">Select a code to view annotations across all papers</p>
      </div>
      <template v-else>
        <h3 class="text-sm font-semibold uppercase opacity-70">
          {{ themesAnnotations.length }} annotations
        </h3>
        <div
          v-for="ann in themesAnnotations"
          :key="ann.id"
          class="p-3 bg-base-200 rounded-lg space-y-2 cursor-pointer hover:bg-base-300 transition-colors"
          :class="{ 'ring-1 ring-primary/30': selectedAnnId === ann.id }"
          @click="selectAnnotation(ann)"
        >
          <!-- Header: paper title + metadata -->
          <div class="flex items-start justify-between gap-2">
            <div>
              <p class="text-sm font-medium leading-snug">{{ ann.paper_title }}</p>
              <p class="text-xs opacity-50">{{ ann.paper_year }} · p.{{ ann.page_number }}</p>
            </div>
          </div>

          <!-- Selected text -->
          <p v-if="ann.selected_text" class="text-xs italic opacity-80 leading-relaxed">{{ ann.selected_text }}</p>

          <!-- Annotation note (rendered markdown, inline) -->
          <div
            v-if="ann.note"
            class="rounded-md px-2 py-1.5 border border-base-content/8 bg-base-100/50"
          >
            <p class="text-xs opacity-40 font-semibold uppercase mb-0.5">Note</p>
            <div class="rendered-markdown text-xs leading-relaxed opacity-80" v-html="renderMd(ann.note)"></div>
          </div>

          <!-- Code notes (rendered markdown, per code) -->
          <template v-for="c in ann.codes" :key="'cn-' + c.id">
            <div
              v-if="c.ac_note"
              class="rounded-md px-2 py-1.5 border border-base-content/8 bg-base-100/50"
            >
              <p class="text-xs opacity-40 mb-0.5">
                <span class="w-1.5 h-1.5 rounded-full inline-block mr-1" :style="{ background: c.color }"></span>
                <span class="font-semibold uppercase">{{ c.name }}</span>
              </p>
              <div class="rendered-markdown text-xs leading-relaxed opacity-80" v-html="renderMd(c.ac_note)"></div>
            </div>
          </template>

          <!-- Code badges -->
          <div class="flex flex-wrap gap-1">
            <span
              v-for="c in ann.codes"
              :key="c.id"
              class="badge badge-xs"
              :style="{ background: c.color + '33', color: c.color, borderColor: c.color }"
            >{{ c.name }}</span>
          </div>
        </div>
      </template>
    </div>

    <!-- Right resize handle -->
    <div
      v-if="workspace.activePaper"
      class="resize-handle"
      @mousedown="startResize"
    />

    <!-- Right: Paper detail panel (same as papers view) -->
    <div
      v-if="workspace.activePaper"
      class="bg-base-200 border-l border-base-300 flex flex-col overflow-y-auto shrink-0"
      :style="`width:${rightWidth}px`"
    >
      <DetailPanel />
    </div>
  </div>
</template>
