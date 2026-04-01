<script setup>
const props = defineProps({
  paper: { type: Object, required: true },
})
</script>

<template>
  <div class="flex-1 overflow-y-auto p-3 space-y-3 text-sm">
    <div v-if="paper.author">
      <label class="font-semibold uppercase opacity-60 text-xs">Authors</label>
      <p class="mt-0.5 leading-relaxed">{{ paper.author }}</p>
    </div>
    <div class="flex gap-4">
      <div v-if="paper.year" class="flex-shrink-0">
        <label class="font-semibold uppercase opacity-60 text-xs">Year</label>
        <p class="mt-0.5">{{ paper.year }}</p>
      </div>
      <div v-if="paper.entry_type" class="flex-shrink-0">
        <label class="font-semibold uppercase opacity-60 text-xs">Type</label>
        <p class="mt-0.5">{{ paper.entry_type }}</p>
      </div>
    </div>
    <div v-if="paper.venue">
      <label class="font-semibold uppercase opacity-60 text-xs">Venue</label>
      <p class="mt-0.5 leading-snug">{{ paper.venue }}</p>
    </div>
    <div v-if="paper.doi || paper.url">
      <label class="font-semibold uppercase opacity-60 text-xs">DOI / Link</label>
      <div class="mt-0.5">
        <a
          class="link link-primary inline-flex items-center gap-1"
          :href="paper.doi ? 'https://doi.org/' + paper.doi : paper.url"
          target="_blank"
        >
          <svg class="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="m4.5 19.5 15-15m0 0H8.25m11.25 0v11.25"/>
          </svg>
          {{ paper.doi || paper.url }}
        </a>
      </div>
    </div>
    <div v-if="paper.bibtex_key">
      <label class="font-semibold uppercase opacity-60 text-xs">BibTeX Key</label>
      <p class="mt-0.5 font-mono text-xs opacity-70">{{ paper.bibtex_key }}</p>
    </div>
    <div v-if="paper.keywords">
      <label class="font-semibold uppercase opacity-60 text-xs">Keywords</label>
      <div class="mt-1 flex flex-wrap gap-1">
        <span
          v-for="kw in paper.keywords.split(',').map(k => k.trim()).filter(k => k)"
          :key="kw"
          class="badge badge-sm badge-ghost"
        >{{ kw }}</span>
      </div>
    </div>
    <div v-if="paper.abstract">
      <label class="font-semibold uppercase opacity-60 text-xs">Abstract</label>
      <p class="mt-1 opacity-80 leading-relaxed">{{ paper.abstract }}</p>
    </div>
  </div>
</template>
