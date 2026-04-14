<script setup>
import { computed, watch } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useMatrixStore } from '@/stores/matrix'
import { useCodebookStore } from '@/stores/codebook'
import { useChatStore } from '@/stores/chat'
import PaperDetails from './PaperDetails.vue'
import ScreeningPanel from './ScreeningPanel.vue'
import AnnotationList from './AnnotationList.vue'
import ChatPanel from './ChatPanel.vue'
import RichTextEditor from './RichTextEditor.vue'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const matrix = useMatrixStore()
const codebook = useCodebookStore()
const chat = useChatStore()

const paper = computed(() => workspace.activePaper)

// Reload data when paper changes while on relevant tab
watch(() => workspace.activePaperId, (id) => {
  if (id && ui.rightTab === 'matrix') {
    matrix.loadPaperCells(id)
  }
})

function switchTab(tab) {
  ui.rightTab = tab
  if (tab === 'annotations') {
    workspace.loadAnnotations()
    workspace.activeAnnotationId = null
  } else if (tab === 'summary') {
    workspace.loadPaperSummary()
  } else if (tab === 'matrix') {
    matrix.loadPaperCells(workspace.activePaperId)
  }
}

function getEvidenceForColumn(column) {
  if (!column.linked_codes?.length) return []
  const codeIds = new Set()
  for (const lc of column.linked_codes) {
    codeIds.add(lc.id)
    for (const code of codebook.codes) {
      if (code.id === lc.id) {
        for (const ch of code.children || []) codeIds.add(ch.id)
      }
      for (const ch of code.children || []) {
        if (ch.id === lc.id) codeIds.add(ch.id)
      }
    }
  }
  return workspace.annotations.filter(ann => ann.codes.some(c => codeIds.has(c.id)))
}

function startChatResize(event) {
  const startY = event.clientY
  const startHeight = ui.chatHeight
  ui.resizing = true

  const onMouseMove = (e) => {
    const dy = startY - e.clientY
    ui.chatHeight = Math.max(150, Math.min(600, startHeight + dy))
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
  <div v-if="paper" class="flex flex-col h-full overflow-hidden">
    <!-- Top Section: Paper info + tabs -->
    <div class="flex flex-col flex-1 min-h-0 overflow-hidden">
      <!-- Paper Metadata (sticky) -->
      <div class="p-3 border-b border-base-300 space-y-1 shrink-0">
        <h3 class="font-semibold text-base leading-tight">{{ paper.title }}</h3>
        <p class="text-sm opacity-70 line-clamp-1">{{ paper.author }}</p>
        <p class="text-sm opacity-70">{{ paper.year }}</p>
        <a
          v-if="paper.doi || paper.url"
          class="link link-primary text-sm inline-flex items-center gap-1"
          :href="paper.doi ? 'https://doi.org/' + paper.doi : paper.url"
          target="_blank"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 19.5 15-15m0 0H8.25m11.25 0v11.25"/>
          </svg>
          {{ paper.doi || 'link' }}
        </a>
      </div>

      <!-- Paper Notes (collapsible) -->
      <div class="border-b border-base-300 relative shrink-0">
        <input :id="'paper-notes-' + paper.id" type="checkbox" class="compact-collapse-toggle">
        <label :for="'paper-notes-' + paper.id" class="compact-collapse-header flex items-center gap-1.5 px-3 py-2 cursor-pointer hover:bg-base-300/50">
          <svg class="w-3 h-3 opacity-40 compact-collapse-arrow shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7"/></svg>
          <span class="text-xs font-semibold uppercase opacity-60">Paper Notes</span>
          <span v-if="workspace.paperNote" class="text-xs font-normal opacity-30">· {{ workspace.paperNote.trim().split(/\s+/).filter(w => w).length }}w</span>
        </label>
        <div class="compact-collapse-body">
          <div>
            <div class="px-3 pb-2">
              <RichTextEditor
                v-model="workspace.paperNote"
                @save="workspace.savePaperNote()"
                placeholder="Notes about this paper..."
                min-height="2rem"
              />
            </div>
          </div>
        </div>
      </div>

      <!-- Tabs (icons) -->
      <div class="tabs tabs-border px-3 pt-1 shrink-0">
        <a class="tab tab-sm" :class="{ 'tab-active': ui.rightTab === 'details' }" @click="switchTab('details')" title="Details">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 0 1 1.063.852l-.708 2.836a.75.75 0 0 0 1.063.853l.041-.021M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9-3.75h.008v.008H12V8.25Z"/></svg>
        </a>
        <a class="tab tab-sm" :class="{ 'tab-active': ui.rightTab === 'screening' }" @click="switchTab('screening')" title="Screening">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"/></svg>
        </a>
        <a class="tab tab-sm" :class="{ 'tab-active': ui.rightTab === 'annotations' }" @click="switchTab('annotations')" title="Annotations">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="m16.862 4.487 1.687-1.688a1.875 1.875 0 1 1 2.652 2.652L6.832 19.82a4.5 4.5 0 0 1-1.897 1.13l-2.685.8.8-2.685a4.5 4.5 0 0 1 1.13-1.897L16.863 4.487Z"/></svg>
        </a>
        <a class="tab tab-sm" :class="{ 'tab-active': ui.rightTab === 'summary' }" @click="switchTab('summary')" title="Summary">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8.25 6.75h12M8.25 12h12m-12 5.25h12M3.75 6.75h.007v.008H3.75V6.75Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0ZM3.75 12h.007v.008H3.75V12Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm-.375 5.25h.007v.008H3.75v-.008Zm.375 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Z"/></svg>
        </a>
        <a class="tab tab-sm" :class="{ 'tab-active': ui.rightTab === 'matrix' }" @click="switchTab('matrix')" title="Matrix">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3.375 19.5h17.25m-17.25 0a1.125 1.125 0 0 1-1.125-1.125M3.375 19.5h7.5c.621 0 1.125-.504 1.125-1.125m-9.75 0V5.625m0 12.75v-1.5c0-.621.504-1.125 1.125-1.125m18.375 2.625V5.625m0 12.75c0 .621-.504 1.125-1.125 1.125m1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125m0 3.75h-7.5A1.125 1.125 0 0 1 12 18.375m9.75-12.75c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125m19.5 0v1.5c0 .621-.504 1.125-1.125 1.125M2.25 5.625v1.5c0 .621.504 1.125 1.125 1.125m0 0h17.25m-17.25 0h7.5c.621 0 1.125.504 1.125 1.125M3.375 8.25c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125m17.25-3.75h-7.5c-.621 0-1.125.504-1.125 1.125m8.625-1.125c.621 0 1.125.504 1.125 1.125v1.5c0 .621-.504 1.125-1.125 1.125m-17.25 0h7.5m-7.5 0c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125M12 10.875v-1.5m0 1.5c0 .621-.504 1.125-1.125 1.125M12 10.875c0 .621.504 1.125 1.125 1.125m-2.25 0c.621 0 1.125.504 1.125 1.125M10.875 12c-.621 0-1.125.504-1.125 1.125M12 10.875c-.621 0-1.125.504-1.125 1.125m0 1.5v-1.5m0 0c0-.621.504-1.125 1.125-1.125m-1.125 1.125c0 .621.504 1.125 1.125 1.125m0 0v-1.5m0 0c0-.621.504-1.125 1.125-1.125"/></svg>
        </a>
        <a class="tab tab-sm" :class="{ 'tab-active': ui.chatOpen }" @click="ui.toggleChat()" title="Toggle Chat">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z"/></svg>
        </a>
      </div>

      <!-- Tab Content -->
      <div class="flex-1 min-h-0 overflow-hidden flex flex-col">
        <!-- Details Tab -->
        <PaperDetails v-show="ui.rightTab === 'details'" :paper="paper" />

        <!-- Screening Tab -->
        <ScreeningPanel v-show="ui.rightTab === 'screening'" />

        <!-- Annotations Tab -->
        <AnnotationList v-show="ui.rightTab === 'annotations'" />

        <!-- Summary Tab -->
        <div class="flex-1 overflow-y-auto p-3 space-y-2" v-show="ui.rightTab === 'summary'">
          <template v-for="group in workspace.paperSummary" :key="'sum-' + group.code.id">
            <div class="collapse collapse-arrow bg-base-300 rounded-lg">
              <input type="checkbox" checked>
              <div class="collapse-title py-2 px-3 min-h-0 flex items-center gap-2 text-sm">
                <div class="w-3 h-3 rounded-full flex-shrink-0" :style="{ background: group.code.color }"></div>
                <span class="font-semibold flex-1">{{ group.code.name }}</span>
                <span class="badge badge-xs badge-ghost">{{ group.annotations.length }}</span>
              </div>
              <div class="collapse-content px-3 pb-3 space-y-1">
                <div
                  v-for="ann in group.annotations"
                  :key="'sa-' + ann.id"
                  class="p-1.5 bg-base-200 rounded text-xs cursor-pointer hover:bg-base-100 transition-colors"
                  @click="workspace.activeAnnotationId = ann.id; ui.rightTab = 'annotations'"
                >
                  <div class="flex items-center gap-1.5">
                    <span class="badge badge-xs badge-ghost flex-shrink-0">p.{{ ann.page_number }}</span>
                    <p class="flex-1 italic opacity-80 line-clamp-2">{{ ann.selected_text || ann.note || '(area)' }}</p>
                  </div>
                </div>
              </div>
            </div>
          </template>
          <div v-show="workspace.paperSummary.length === 0" class="text-sm opacity-50 text-center py-4">
            No annotations for this paper yet.
          </div>
        </div>

        <!-- Matrix Tab -->
        <div class="flex-1 overflow-y-auto p-3 space-y-2" v-show="ui.rightTab === 'matrix'">
          <template v-for="col in matrix.matrixColumns" :key="'mt-' + col.id">
            <div class="collapse collapse-arrow bg-base-300 rounded-lg">
              <input type="checkbox" checked>
              <div class="collapse-title py-2 px-3 min-h-0 flex items-center gap-2 text-sm">
                <div class="w-3 h-3 rounded-full flex-shrink-0" :style="{ background: col.color }"></div>
                <span class="font-semibold flex-1">{{ col.name }}</span>
                <span
                  v-show="getEvidenceForColumn(col).length > 0"
                  class="badge badge-xs badge-ghost"
                >{{ getEvidenceForColumn(col).length }} ev.</span>
              </div>
              <div class="collapse-content px-3 pb-3 space-y-2">
                <p v-if="col.description" class="text-xs opacity-40 -mt-1">{{ col.description }}</p>
                <!-- enum_single -->
                <select
                  v-if="col.column_type === 'enum_single'"
                  class="select select-sm w-full"
                  :value="matrix.paperMatrixCells[col.id]?.value || ''"
                  @change="matrix.savePaperMatrixCell(workspace.activePaperId, col.id, $event.target.value)"
                >
                  <option value="">-- select --</option>
                  <option v-for="opt in col.options" :key="opt.id" :value="opt.value">{{ opt.value }}</option>
                </select>
                <!-- enum_multi -->
                <div v-else-if="col.column_type === 'enum_multi'" class="space-y-1">
                  <label v-for="opt in col.options" :key="opt.id" class="flex items-center gap-2 cursor-pointer text-sm">
                    <input
                      type="checkbox"
                      class="checkbox checkbox-xs"
                      :checked="matrix.parseMultiValue(matrix.paperMatrixCells[col.id]?.value).includes(opt.value)"
                      @change="matrix.toggleMultiValue(col.id, opt.value, workspace.activePaperId)"
                    >
                    <span>{{ opt.value }}</span>
                  </label>
                </div>
                <!-- checkbox -->
                <label v-else-if="col.column_type === 'checkbox'" class="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    class="checkbox checkbox-sm"
                    :checked="matrix.paperMatrixCells[col.id]?.value === 'true'"
                    @change="matrix.savePaperMatrixCell(workspace.activePaperId, col.id, $event.target.checked ? 'true' : 'false')"
                  >
                  <span class="text-sm">{{ matrix.paperMatrixCells[col.id]?.value === 'true' ? 'Yes' : 'No' }}</span>
                </label>
                <!-- Inline add option (for enum types) -->
                <div v-if="col.column_type === 'enum_single' || col.column_type === 'enum_multi'" class="flex gap-1 mt-1">
                  <input
                    type="text"
                    placeholder="+ option..."
                    class="input input-xs flex-1 bg-base-300"
                    :value="matrix.newOptionValues[col.id] || ''"
                    @input="matrix.newOptionValues[col.id] = $event.target.value"
                    @keydown.enter="matrix.addOption(col.id)"
                  >
                  <button class="btn btn-ghost btn-xs text-primary" @click="matrix.addOption(col.id)">+</button>
                </div>
                <!-- text -->
                <input
                  v-else
                  type="text"
                  class="input input-sm w-full"
                  placeholder="Enter value..."
                  :value="matrix.paperMatrixCells[col.id]?.value || ''"
                  @change="matrix.savePaperMatrixCell(workspace.activePaperId, col.id, $event.target.value)"
                >
                <!-- Evidence -->
                <div v-if="getEvidenceForColumn(col).length > 0" class="space-y-1 mt-1">
                  <label class="text-xs font-semibold uppercase opacity-60">Evidence</label>
                  <div
                    v-for="ann in getEvidenceForColumn(col)"
                    :key="'me-' + ann.id"
                    class="p-1.5 bg-base-200 rounded text-xs cursor-pointer hover:bg-base-100 transition-colors"
                    @click="workspace.activeAnnotationId = ann.id; ui.rightTab = 'annotations'"
                  >
                    <div class="flex items-center gap-1.5">
                      <span class="badge badge-xs badge-ghost flex-shrink-0">p.{{ ann.page_number }}</span>
                      <p class="flex-1 italic opacity-80 line-clamp-2">{{ ann.selected_text || ann.note || '(area)' }}</p>
                    </div>
                  </div>
                </div>
                <div v-show="col.linked_codes.length === 0" class="text-xs opacity-40 mt-1">
                  No codes linked — open Column editor to link codes for evidence tracking.
                </div>
              </div>
            </div>
          </template>
          <div v-show="matrix.matrixColumns.length === 0" class="text-sm opacity-50 text-center py-4">
            No matrix columns defined. Click "Columns" in the toolbar to create some.
          </div>
        </div>
      </div>
    </div>

    <!-- Horizontal Resize Handle -->
    <div
      v-show="ui.chatOpen"
      class="resize-handle-h shrink-0"
      @mousedown="startChatResize"
    />

    <!-- Bottom Section: Chat Panel -->
    <div
      v-show="ui.chatOpen"
      class="border-t border-base-300 flex flex-col overflow-hidden shrink-0"
      :style="`height:${ui.chatHeight}px`"
    >
      <ChatPanel />
    </div>
  </div>

  <!-- No paper selected -->
  <div v-else class="flex-1 flex items-center justify-center">
    <p class="text-sm opacity-50">Select a paper</p>
  </div>
</template>
