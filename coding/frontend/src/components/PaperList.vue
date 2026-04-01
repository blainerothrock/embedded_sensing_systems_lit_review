<script setup>
import { watch } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useDebounce } from '@/composables/useDebounce'
import PaperListItem from './PaperListItem.vue'

const workspace = useWorkspaceStore()

const { debounced: searchPapers } = useDebounce(() => {
  workspace.loadPapers()
}, 300)

function onFilterChange() {
  workspace.loadPapers()
}
</script>

<template>
  <div class="bg-base-200 flex flex-col h-full">
    <div class="p-2 space-y-2 border-b border-base-300">
      <label class="input input-sm w-full flex items-center gap-2">
        <svg class="w-4 h-4 opacity-50" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z"/>
        </svg>
        <input
          type="text"
          placeholder="Search papers..."
          class="grow bg-transparent border-none outline-none text-sm"
          v-model="workspace.searchQuery"
          @input="searchPapers()"
        >
      </label>
      <select class="select select-sm w-full" v-model="workspace.statusFilter" @change="onFilterChange()">
        <option value="all">All papers</option>
        <option value="pending">Pending review</option>
        <option value="include">Included</option>
        <option value="exclude">Excluded</option>
        <option value="has_pdf">Has PDF</option>
        <option value="no_pdf">No PDF</option>
      </select>
    </div>
    <div class="flex-1 overflow-y-auto">
      <ul class="menu menu-sm p-1">
        <PaperListItem
          v-for="paper in workspace.papers"
          :key="paper.id"
          :paper="paper"
          :active="workspace.activePaperId === paper.id"
          @select="workspace.selectPaper($event)"
        />
      </ul>
      <div class="p-4 text-center text-sm opacity-50" v-show="workspace.papers.length === 0">
        No papers found
      </div>
    </div>
    <div class="p-2 border-t border-base-300 text-xs text-center opacity-60">
      {{ workspace.papers.length }} papers
    </div>
  </div>
</template>
