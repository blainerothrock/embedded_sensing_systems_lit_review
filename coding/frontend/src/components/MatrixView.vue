<script setup>
import { ref, computed, onMounted } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useMatrixStore } from '@/stores/matrix'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const matrix = useMatrixStore()

const hiddenColumns = ref(new Set())

onMounted(() => {
  if (!matrix.matrixData) matrix.loadMatrixData()
})

const visibleColumns = computed(() => {
  if (!matrix.matrixData) return []
  return matrix.matrixData.columns.filter(c => !hiddenColumns.value.has(c.id))
})

function toggleColumn(colId) {
  const s = new Set(hiddenColumns.value)
  if (s.has(colId)) s.delete(colId)
  else s.add(colId)
  hiddenColumns.value = s
}

function onStatusChange() {
  matrix.loadMatrixData()
}

function navigateToPaper(paperId) {
  ui.setView('papers')
  workspace.selectPaper(paperId)
}

function saveCell(paperId, colId, value) {
  matrix.saveMatrixCell(paperId, colId, value)
}

function toggleCellMulti(paperId, colId, optValue) {
  let current = []
  try {
    current = JSON.parse(matrix.matrixData.cells[paperId]?.[colId]?.value || '[]')
  } catch { current = [] }
  const idx = current.indexOf(optValue)
  if (idx >= 0) current.splice(idx, 1)
  else current.push(optValue)
  saveCell(paperId, colId, JSON.stringify(current))
}
</script>

<template>
  <div class="h-[calc(100vh-3rem)] flex flex-col">
    <!-- Toolbar -->
    <div v-if="matrix.matrixData" class="p-3 border-b border-base-300 bg-base-200 flex items-center gap-3 flex-wrap shrink-0">
      <select class="select select-sm" v-model="matrix.matrixStatusFilter" @change="onStatusChange()">
        <option value="all">All papers</option>
        <option value="included">Included</option>
        <option value="excluded">Excluded</option>
        <option value="pending">Pending</option>
      </select>
      <span class="text-xs opacity-60">{{ matrix.matrixData.papers.length }} papers</span>
      <div class="divider divider-horizontal mx-0"></div>
      <span class="text-xs opacity-60">Columns:</span>
      <div class="flex gap-1 flex-wrap">
        <button
          v-for="col in visibleColumns"
          :key="'toggle-' + col.id"
          class="btn btn-xs"
          :class="hiddenColumns.has(col.id) ? 'btn-ghost opacity-40' : 'btn-outline'"
          @click="toggleColumn(col.id)"
        >
          <span class="w-2 h-2 rounded-full inline-block" :style="{ background: col.color }"></span>
          {{ col.name }}
        </button>
      </div>
    </div>

    <div class="flex-1 overflow-auto p-4">
    <template v-if="matrix.matrixData">
      <div class="overflow-x-auto">
        <table class="table table-xs table-pin-rows table-pin-cols">
          <thead>
            <tr>
              <th class="bg-base-200 z-20">Paper</th>
              <th class="bg-base-200">Year</th>
              <th
                v-for="col in visibleColumns"
                :key="'h-' + col.id"
                class="bg-base-200 text-center min-w-28"
              >
                <div class="flex flex-col items-center gap-0.5">
                  <div class="w-2 h-2 rounded-full" :style="{ background: col.color }"></div>
                  <span>{{ col.name }}</span>
                  <span class="text-xs opacity-40">{{ col.column_type.replace('_', ' ') }}</span>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="paper in matrix.matrixData.papers" :key="paper.id" class="hover">
              <td
                class="max-w-xs truncate bg-base-200 z-10 cursor-pointer"
                @click="navigateToPaper(paper.id)"
              >{{ paper.title }}</td>
              <td class="bg-base-200">{{ paper.year }}</td>
              <td
                v-for="col in visibleColumns"
                :key="'c-' + col.id + '-' + paper.id"
                class="text-center p-1"
                @click.stop
              >
                <!-- enum_single -->
                <select
                  v-if="col.column_type === 'enum_single'"
                  class="select select-xs w-full max-w-28"
                  :value="matrix.matrixData.cells[paper.id]?.[col.id]?.value || ''"
                  @change="saveCell(paper.id, col.id, $event.target.value)"
                >
                  <option value="">—</option>
                  <option v-for="opt in col.options" :key="opt.id" :value="opt.value">{{ opt.value }}</option>
                </select>
                <!-- enum_multi -->
                <div v-else-if="col.column_type === 'enum_multi'" class="text-xs text-left">
                  <label v-for="opt in col.options" :key="opt.id" class="flex items-center gap-1 cursor-pointer">
                    <input
                      type="checkbox"
                      class="checkbox checkbox-xs"
                      :checked="matrix.parseMultiValue(matrix.matrixData.cells[paper.id]?.[col.id]?.value).includes(opt.value)"
                      @change="toggleCellMulti(paper.id, col.id, opt.value)"
                    >
                    <span>{{ opt.value }}</span>
                  </label>
                </div>
                <!-- checkbox -->
                <input
                  v-else-if="col.column_type === 'checkbox'"
                  type="checkbox"
                  class="checkbox checkbox-xs"
                  :checked="matrix.matrixData.cells[paper.id]?.[col.id]?.value === 'true'"
                  @change="saveCell(paper.id, col.id, $event.target.checked ? 'true' : 'false')"
                >
                <!-- text -->
                <input
                  v-else
                  type="text"
                  class="input input-xs w-full max-w-28"
                  :value="matrix.matrixData.cells[paper.id]?.[col.id]?.value || ''"
                  @change="saveCell(paper.id, col.id, $event.target.value)"
                >
                <!-- Evidence count -->
                <span
                  class="badge badge-xs badge-ghost mt-0.5"
                  v-show="matrix.matrixData.evidence?.[paper.id]?.[col.id]"
                >{{ matrix.matrixData.evidence?.[paper.id]?.[col.id] || 0 }} ann.</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
    <div v-else class="flex items-center justify-center h-full">
      <span class="loading loading-spinner loading-md"></span>
    </div>
    </div>
  </div>
</template>
