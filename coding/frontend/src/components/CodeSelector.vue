<script setup>
import { ref } from 'vue'
import { useCodebookStore } from '@/stores/codebook'

const props = defineProps({
  excludeIds: { type: Array, default: () => [] },
})

const emit = defineEmits(['select', 'close'])

const codebook = useCodebookStore()
const search = ref('')
</script>

<template>
  <div class="bg-base-100 rounded-lg border border-base-300 shadow-lg p-2 overflow-x-hidden">
    <div class="flex items-center gap-1 mb-2">
      <input
        type="text"
        class="input input-xs flex-1"
        placeholder="Search codes..."
        v-model="search"
        @keydown.escape="emit('close')"
      >
      <button class="btn btn-xs btn-ghost" @click="emit('close')">
        <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>
        </svg>
      </button>
    </div>
    <div class="max-h-52 overflow-y-auto space-y-0.5">
      <template v-for="topCode in codebook.codes" :key="'pick-' + topCode.id">
        <div v-if="codebook.codeMatchesSearch(topCode, search)">
          <button
            v-if="!excludeIds.includes(topCode.id)"
            class="flex items-center gap-2 w-full text-left px-2 py-1.5 text-xs rounded hover:bg-base-200 font-semibold"
            @click="emit('select', topCode.id)"
          >
            <div class="w-2.5 h-2.5 rounded-full flex-shrink-0" :style="{ background: topCode.color }"></div>
            <span>{{ topCode.name }}</span>
          </button>
          <div
            v-if="!excludeIds.includes(topCode.id) && topCode.description"
            class="px-2 pb-1 text-xs opacity-40 ml-5"
          >{{ topCode.description }}</div>
          <template v-for="sub in topCode.children" :key="'pick-sub-' + sub.id">
            <button
              v-if="!excludeIds.includes(sub.id) && codebook.subCodeMatchesSearch(sub, topCode, search)"
              class="flex items-center gap-2 w-full text-left px-2 py-1 text-xs rounded hover:bg-base-200 ml-4"
              @click="emit('select', sub.id)"
            >
              <div class="w-2 h-2 rounded-full flex-shrink-0" :style="{ background: sub.color }"></div>
              <span>{{ sub.name }}</span>
            </button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>
