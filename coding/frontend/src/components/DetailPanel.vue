<script setup>
import { computed } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useMatrixStore } from '@/stores/matrix'
import { useCodebookStore } from '@/stores/codebook'
import PaperDetails from './PaperDetails.vue'
import ScreeningPanel from './ScreeningPanel.vue'
import AnnotationList from './AnnotationList.vue'
import RichTextEditor from './RichTextEditor.vue'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const matrix = useMatrixStore()
const codebook = useCodebookStore()

const paper = computed(() => workspace.activePaper)

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
</script>

<template>
  <template v-if="paper">
    <!-- Paper Metadata -->
    <div class="p-3 border-b border-base-300 space-y-1 max-h-48 overflow-y-auto">
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
    <div class="border-b border-base-300 relative">
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

    <!-- Tabs -->
    <div class="tabs tabs-border px-3 pt-1">
      <a class="tab tab-sm gap-1" :class="{ 'tab-active': ui.rightTab === 'details' }" @click="switchTab('details')">Details</a>
      <a class="tab tab-sm gap-1" :class="{ 'tab-active': ui.rightTab === 'screening' }" @click="switchTab('screening')">Screening</a>
      <a class="tab tab-sm gap-1" :class="{ 'tab-active': ui.rightTab === 'annotations' }" @click="switchTab('annotations')">Annotations</a>
      <a class="tab tab-sm gap-1" :class="{ 'tab-active': ui.rightTab === 'summary' }" @click="switchTab('summary')">Summary</a>
      <a class="tab tab-sm gap-1" :class="{ 'tab-active': ui.rightTab === 'matrix' }" @click="switchTab('matrix')">Matrix</a>
    </div>

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
  </template>

  <!-- No paper selected -->
  <div v-else class="flex-1 flex items-center justify-center">
    <p class="text-sm opacity-50">Select a paper</p>
  </div>
</template>
