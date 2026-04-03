<script setup>
import { computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useDebounce } from '@/composables/useDebounce'
import PaperListItem from './PaperListItem.vue'

const workspace = useWorkspaceStore()

const { debounced: searchPapers } = useDebounce(() => {
  workspace.loadPapers()
}, 300)

const activeFilters = computed(() => {
  const f = workspace.statusFilter
  if (!f || f === 'all') return new Set()
  return new Set(f.split(',').filter(Boolean))
})

function toggleFilter(value) {
  const current = new Set(activeFilters.value)
  if (current.has(value)) {
    current.delete(value)
  } else {
    // Mutually exclusive groups
    const decisionGroup = ['pending', 'include', 'exclude']
    const codingGroup = ['coding', 'complete']
    const pdfGroup = ['has_pdf', 'no_pdf']

    if (decisionGroup.includes(value)) decisionGroup.forEach(v => current.delete(v))
    if (codingGroup.includes(value)) codingGroup.forEach(v => current.delete(v))
    if (pdfGroup.includes(value)) pdfGroup.forEach(v => current.delete(v))

    current.add(value)
  }
  workspace.statusFilter = current.size > 0 ? [...current].join(',') : 'all'
  workspace.loadPapers()
}

function onSortChange() {
  workspace.loadPapers()
}

const filterChips = [
  { value: 'pending', label: 'Pending' },
  { value: 'include', label: 'Included' },
  { value: 'exclude', label: 'Excluded' },
  { value: 'coding', label: 'Coding' },
  { value: 'complete', label: 'Complete' },
  { value: 'has_pdf', label: 'PDF' },
  { value: 'no_pdf', label: 'No PDF' },
]
</script>

<template>
  <div class="bg-base-200 flex flex-col h-full">
    <div class="p-2 space-y-1.5 border-b border-base-300">
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
      <div class="flex flex-wrap gap-1">
        <button
          v-for="chip in filterChips"
          :key="chip.value"
          class="btn btn-xs"
          :class="activeFilters.has(chip.value) ? 'btn-primary' : 'btn-ghost opacity-50'"
          @click="toggleFilter(chip.value)"
        >{{ chip.label }}</button>
        <button
          v-if="activeFilters.size > 0"
          class="btn btn-xs btn-ghost opacity-40"
          @click="workspace.statusFilter = 'all'; workspace.loadPapers()"
        >Clear</button>
      </div>
      <div class="flex gap-1.5 items-center">
        <select class="select select-xs flex-1" v-model="workspace.sortBy" @change="onSortChange()">
          <option value="title">Title</option>
          <option value="year">Year</option>
          <option value="id">ID</option>
        </select>
        <button class="btn btn-ghost btn-xs opacity-50" @click="workspace.shufflePapers()" title="Randomize order">Shuffle</button>
      </div>
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
