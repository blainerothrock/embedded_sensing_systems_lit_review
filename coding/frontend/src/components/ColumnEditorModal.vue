<script setup>
import { useUiStore } from '@/stores/ui'
import { useMatrixStore } from '@/stores/matrix'
import { useCodebookStore } from '@/stores/codebook'

const ui = useUiStore()
const matrix = useMatrixStore()
const codebook = useCodebookStore()
</script>

<template>
  <dialog class="modal" :class="{ 'modal-open': ui.showColumnEditor }">
    <div class="modal-box max-w-2xl max-h-[80vh]">
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
        </select>
        <button class="btn btn-sm btn-primary" @click="matrix.createColumn()">+ Add</button>
      </div>

      <!-- Column list -->
      <div class="space-y-3 overflow-y-auto max-h-96">
        <div v-for="col in matrix.matrixColumns" :key="col.id" class="bg-base-300 rounded-lg p-3 space-y-2">
          <div class="flex items-center gap-2">
            <input
              type="color"
              :value="col.color || '#888888'"
              @change="matrix.updateColumn(col.id, { color: $event.target.value })"
              class="w-6 h-6 cursor-pointer border-0 bg-transparent"
            >
            <input
              type="text"
              :value="col.name"
              @change="matrix.updateColumn(col.id, { name: $event.target.value })"
              class="input input-xs flex-1 bg-transparent font-medium"
            >
            <span class="badge badge-xs badge-ghost">{{ col.column_type.replace('_', ' ') }}</span>
            <button class="btn btn-ghost btn-xs btn-square text-error opacity-30" @click="matrix.deleteColumn(col.id)">✕</button>
          </div>

          <!-- Options (for enum types) -->
          <div v-if="col.column_type !== 'text'" class="pl-4 space-y-1">
            <label class="text-xs font-semibold uppercase opacity-60">Options</label>
            <div v-for="opt in col.options" :key="opt.id" class="flex items-center gap-2">
              <span class="text-sm flex-1">{{ opt.value }}</span>
              <button class="btn btn-ghost btn-xs btn-square opacity-30 text-error" @click="matrix.deleteOption(opt.id)">✕</button>
            </div>
            <div class="flex gap-1">
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
          <div class="pl-4 space-y-1">
            <label class="text-xs font-semibold uppercase opacity-60">Linked Codes (for evidence)</label>
            <div v-for="lc in col.linked_codes || []" :key="lc.id" class="flex items-center gap-2">
              <div class="w-2 h-2 rounded-full" :style="{ background: lc.color }"></div>
              <span class="text-sm flex-1">{{ lc.name }}</span>
              <button class="btn btn-ghost btn-xs btn-square opacity-30 text-error" @click="matrix.unlinkCode(col.id, lc.id)">✕</button>
            </div>
            <select
              class="select select-xs w-full bg-base-200"
              @change="if ($event.target.value) { matrix.linkCode(col.id, parseInt($event.target.value)); $event.target.value = '' }"
            >
              <option value="">+ Link a code...</option>
              <template v-for="code in codebook.allCodesFlat" :key="code.id">
                <option
                  v-if="!(col.linked_codes || []).some(lc => lc.id === code.id)"
                  :value="code.id"
                >{{ code.name }}</option>
              </template>
            </select>
          </div>
        </div>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop" @click="ui.showColumnEditor = false">
      <button>close</button>
    </form>
  </dialog>
</template>
