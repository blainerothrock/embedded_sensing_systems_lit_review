<script setup>
import { useUiStore } from '@/stores/ui'
import { useCodebookStore } from '@/stores/codebook'

const ui = useUiStore()
const codebook = useCodebookStore()
</script>

<template>
  <dialog class="modal" :class="{ 'modal-open': ui.showCodeManager }">
    <div class="modal-box max-w-2xl max-h-[80vh]">
      <div class="flex items-center justify-between mb-4">
        <h3 class="text-lg font-semibold">Code Builder</h3>
        <button class="btn btn-sm btn-ghost btn-square" @click="ui.showCodeManager = false">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>

      <!-- Create top-level code -->
      <div class="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="New top-level code..."
          class="input input-sm flex-1"
          v-model="codebook.newCodeName"
          @keydown.enter="codebook.createTopCode()"
        >
        <button class="btn btn-sm btn-primary" @click="codebook.createTopCode()">+ Add Code</button>
      </div>

      <!-- Code list -->
      <div class="space-y-3 overflow-y-auto max-h-96">
        <div v-for="code in codebook.codes" :key="code.id" class="bg-base-300 rounded-lg">
          <div class="flex items-center gap-2 px-3 py-2">
            <input
              type="color"
              :value="code.color || '#888888'"
              @change="codebook.updateCode(code.id, { color: $event.target.value })"
              class="w-6 h-6 cursor-pointer border-0 bg-transparent"
            >
            <input
              type="text"
              :value="code.name"
              @change="codebook.updateCode(code.id, { name: $event.target.value })"
              class="input input-xs flex-1 bg-transparent font-medium"
            >
            <span class="text-xs opacity-40 font-mono mr-2">{{ codebook.codeUsageCounts[code.id] || 0 }} ann.</span>
            <button class="btn btn-ghost btn-xs btn-square opacity-40" @click="codebook.reorderCode(code.id, -1)">↑</button>
            <button class="btn btn-ghost btn-xs btn-square opacity-40" @click="codebook.reorderCode(code.id, 1)">↓</button>
            <button
              v-if="!codebook.codeUsageCounts[code.id] && !(code.children || []).length"
              class="btn btn-ghost btn-xs btn-square opacity-30 text-error"
              @click="codebook.deleteCode(code.id)"
            >✕</button>
          </div>
          <div class="px-3 pb-2">
            <textarea
              :value="code.description || ''"
              @change="codebook.updateCode(code.id, { description: $event.target.value })"
              placeholder="Description (optional)..."
              class="textarea textarea-xs w-full min-h-8 h-8 resize-none bg-base-200"
            ></textarea>
          </div>
          <!-- Sub-codes -->
          <div class="px-3 pb-3 space-y-1">
            <div v-for="sub in code.children || []" :key="sub.id" class="pl-4 space-y-0.5">
              <div class="flex items-center gap-2">
                <input
                  type="color"
                  :value="sub.color || '#888888'"
                  @change="codebook.updateCode(sub.id, { color: $event.target.value })"
                  class="w-4 h-4 cursor-pointer border-0 bg-transparent"
                >
                <input
                  type="text"
                  :value="sub.name"
                  @change="codebook.updateCode(sub.id, { name: $event.target.value })"
                  class="input input-xs flex-1 bg-transparent"
                >
                <span class="text-xs opacity-40 font-mono mr-2">{{ codebook.codeUsageCounts[sub.id] || 0 }}</span>
                <button class="btn btn-ghost btn-xs btn-square opacity-40" @click="codebook.reorderCode(sub.id, -1)">↑</button>
                <button class="btn btn-ghost btn-xs btn-square opacity-40" @click="codebook.reorderCode(sub.id, 1)">↓</button>
                <button
                  v-if="!codebook.codeUsageCounts[sub.id]"
                  class="btn btn-ghost btn-xs btn-square opacity-30 text-error"
                  @click="codebook.deleteCode(sub.id)"
                >✕</button>
              </div>
              <input
                type="text"
                :value="sub.description || ''"
                @change="codebook.updateCode(sub.id, { description: $event.target.value })"
                placeholder="Description (for LLM context)..."
                class="input input-xs w-full bg-base-200 text-xs opacity-60"
              >
            </div>
            <div class="flex items-center gap-1 pl-4 pt-1">
              <input
                type="text"
                placeholder="New sub-code..."
                class="input input-xs flex-1 bg-base-200"
                :value="codebook.newSubCodeNames[code.id] || ''"
                @input="codebook.newSubCodeNames[code.id] = $event.target.value"
                @keydown.enter="codebook.createSubCode(code.id)"
              >
              <button class="btn btn-ghost btn-xs btn-square text-primary" @click="codebook.createSubCode(code.id)">+</button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop" @click="ui.showCodeManager = false">
      <button>close</button>
    </form>
  </dialog>
</template>
