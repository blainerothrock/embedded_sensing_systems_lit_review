<script setup>
import { useMatrixStore } from '@/stores/matrix'

const props = defineProps({
  paper: { type: Object, required: true },
  active: { type: Boolean, default: false },
})

const emit = defineEmits(['select'])
const matrix = useMatrixStore()
</script>

<template>
  <li>
    <a
      @click="emit('select', paper.id)"
      :data-paper-id="paper.id"
      :class="{ active }"
      class="flex flex-col items-start gap-0.5 py-1.5"
    >
      <span class="text-sm leading-tight line-clamp-2">{{ paper.title || 'Untitled' }}</span>
      <div class="flex gap-1 flex-wrap items-center">
        <span
          class="badge badge-xs"
          :class="{
            'badge-success': paper.phase3_decision === 'include',
            'badge-error': paper.phase3_decision === 'exclude',
            'badge-warning': paper.phase3_decision === 'uncertain',
            'badge-ghost': !paper.phase3_decision,
          }"
        >{{ paper.phase3_decision || 'pending' }}</span>
        <span class="badge badge-xs badge-info gap-0.5" v-show="paper.pdf_path">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"/>
          </svg>
          PDF
        </span>
        <span
          class="text-xs opacity-40"
          v-if="matrix.codingCompleteness[paper.id]"
        >{{ matrix.codingCompleteness[paper.id].filled }}/{{ matrix.codingCompleteness[paper.id].total }}</span>
      </div>
    </a>
  </li>
</template>
