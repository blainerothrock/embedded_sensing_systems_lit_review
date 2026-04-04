<script setup>
import { ref } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useMatrixStore } from '@/stores/matrix'
import { useCodebookStore } from '@/stores/codebook'

const ui = useUiStore()
const matrix = useMatrixStore()
const codebook = useCodebookStore()
const expandedColumns = ref(new Set())

function toggleExpand(colId) {
  const s = new Set(expandedColumns.value)
  if (s.has(colId)) s.delete(colId)
  else s.add(colId)
  expandedColumns.value = s
}
</script>

<template>
  <dialog class="modal" :class="{ 'modal-open': ui.showColumnEditor }">
    <div class="modal-box max-w-5xl max-h-[90vh]">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold">Matrix Columns</h3>
        <button class="btn btn-sm btn-ghost btn-square" @click="ui.showColumnEditor = false">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <!-- Create column -->
      <div class="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="Column name..."
          class="input input-sm flex-1"
          v-model="matrix.newColumnName"
          @keydown.enter="matrix.createColumn()"
        >
        <select class="select select-sm" v-model="matrix.newColumnType">
          <option value="enum_single">Single select</option>
          <option value="enum_multi">Multi select</option>
          <option value="text">Text</option>
          <option value="checkbox">Checkbox</option>
        </select>
        <button class="btn btn-sm btn-primary" @click="matrix.createColumn()">+ Add</button>
        <button class="btn btn-sm btn-ghost opacity-50" @click="matrix.shuffleColors()" title="Randomize all column colors">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M4.098 19.902a3.75 3.75 0 0 0 5.304 0l6.401-6.402M6.75 21A3.75 3.75 0 0 1 3 17.25V4.125C3 3.504 3.504 3 4.125 3h5.25c.621 0 1.125.504 1.125 1.125v4.072M6.75 21a3.75 3.75 0 0 0 3.75-3.75V8.197M6.75 21h13.125c.621 0 1.125-.504 1.125-1.125v-5.25c0-.621-.504-1.125-1.125-1.125h-4.072"/>
          </svg>
        </button>
      </div>

      <!-- Column list -->
      <div class="space-y-2 overflow-y-auto max-h-[70vh]">
        <div v-for="col in matrix.matrixColumns" :key="col.id" class="bg-base-300 rounded-lg">
          <!-- Column header (always visible) -->
          <div class="flex items-center gap-2 px-3 py-2 cursor-pointer" @click="toggleExpand(col.id)">
            <svg
              class="w-3 h-3 opacity-40 shrink-0 transition-transform"
              :class="{ 'rotate-90': expandedColumns.has(col.id) }"
              fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"
            ><path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7"/></svg>
            <input
              type="color"
              :value="col.color || '#888888'"
              @change="matrix.updateColumn(col.id, { color: $event.target.value })"
              @click.stop
              class="w-5 h-5 cursor-pointer border-0 bg-transparent"
            >
            <input
              type="text"
              :value="col.name"
              @change="matrix.updateColumn(col.id, { name: $event.target.value })"
              @click.stop
              class="input input-xs flex-1 bg-transparent font-medium"
            >
            <span class="badge badge-xs badge-ghost">{{ col.column_type.replace('_', ' ') }}</span>
            <span v-if="col.options?.length" class="text-xs opacity-40">{{ col.options.length }} opts</span>
            <button class="btn btn-ghost btn-xs btn-square opacity-30" @click.stop="matrix.reorderColumn(col.id, -1)" title="Move up">▲</button>
            <button class="btn btn-ghost btn-xs btn-square opacity-30" @click.stop="matrix.reorderColumn(col.id, 1)" title="Move down">▼</button>
            <button class="btn btn-ghost btn-xs btn-square text-error opacity-30" @click.stop="matrix.deleteColumn(col.id)">✕</button>
          </div>

          <!-- Expanded content -->
          <div v-show="expandedColumns.has(col.id)" class="px-3 pb-3 space-y-2">
            <textarea
              :value="col.description || ''"
              @change="matrix.updateColumn(col.id, { description: $event.target.value })"
              placeholder="Description (for LLM context)..."
              class="textarea textarea-xs w-full min-h-8 resize-y bg-base-200 opacity-60"
            ></textarea>
            <!-- Options (for enum types) -->
            <div v-if="col.column_type !== 'text'">
              <label class="text-xs font-semibold uppercase opacity-60">Options</label>
              <div class="flex flex-wrap gap-1 mt-1">
                <div
                  v-for="(opt, idx) in col.options"
                  :key="opt.id"
                  class="flex items-center gap-1 bg-base-200 rounded px-1.5 py-0.5"
                >
                  <input
                    type="text"
                    :value="opt.value"
                    @change="matrix.updateOption(opt.id, { value: $event.target.value })"
                    class="input input-xs bg-transparent w-auto min-w-12 max-w-32"
                    :style="{ width: (opt.value.length + 1) + 'ch' }"
                  >
                  <button class="btn btn-ghost btn-xs btn-square opacity-30" @click="matrix.reorderOption(col.id, opt.id, -1)" title="Move left">‹</button>
                  <button class="btn btn-ghost btn-xs btn-square opacity-30" @click="matrix.reorderOption(col.id, opt.id, 1)" title="Move right">›</button>
                  <button class="btn btn-ghost btn-xs btn-square opacity-30 text-error" @click="matrix.deleteOption(opt.id)">✕</button>
                </div>
              </div>
              <div class="flex gap-1 mt-1">
                <input
                  type="text"
                  placeholder="New option..."
                  class="input input-xs flex-1 bg-base-200"
                  :value="matrix.newOptionValues[col.id] || ''"
                  @input="matrix.newOptionValues[col.id] = $event.target.value"
                  @keydown.enter="matrix.addOption(col.id)"
                >
                <button class="btn btn-ghost btn-xs text-primary" @click="matrix.addOption(col.id)">+</button>
              </div>
            </div>

            <!-- Linked codes -->
            <div>
              <label class="text-xs font-semibold uppercase opacity-60">Linked Codes (for evidence)</label>
              <div class="flex flex-wrap gap-1 mt-1">
                <div v-for="lc in col.linked_codes || []" :key="lc.id" class="flex items-center gap-1 bg-base-200 rounded px-1.5 py-0.5">
                  <div class="w-2 h-2 rounded-full" :style="{ background: lc.color }"></div>
                  <span class="text-xs">{{ lc.name }}</span>
                  <button class="btn btn-ghost btn-xs btn-square opacity-30 text-error" @click="matrix.unlinkCode(col.id, lc.id)">✕</button>
                </div>
              </div>
              <select
                class="select select-xs w-full bg-base-200 mt-1"
                @change="if ($event.target.value) { matrix.linkCode(col.id, parseInt($event.target.value)); $event.target.value = '' }"
              >
                <option value="">+ Link a code...</option>
                <template v-for="code in codebook.codes" :key="code.id">
                  <option
                    v-if="!(col.linked_codes || []).some(lc => lc.id === code.id)"
                    :value="code.id"
                    class="font-semibold"
                  >{{ code.name }}</option>
                  <template v-for="sub in code.children || []" :key="sub.id">
                    <option
                      v-if="!(col.linked_codes || []).some(lc => lc.id === sub.id)"
                      :value="sub.id"
                    >&nbsp;&nbsp;└ {{ sub.name }}</option>
                  </template>
                </template>
              </select>
            </div>
          </div>
        </div>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop" @click="ui.showColumnEditor = false">
      <button>close</button>
    </form>
  </dialog>
</template>
