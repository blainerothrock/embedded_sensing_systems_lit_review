<script setup>
import { ref, computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  modelValue: { type: String, default: '' },
})

const emit = defineEmits(['update:modelValue', 'save'])

const preview = ref(false)
const saved = ref(false)

const rendered = computed(() => marked.parse(props.modelValue || '*No notes yet.*'))

function save() {
  emit('save', props.modelValue)
  saved.value = true
  setTimeout(() => saved.value = false, 1500)
}

function handleKey(e) {
  if (e.key === 'Tab') {
    e.preventDefault()
    const s = e.target.selectionStart
    const val = props.modelValue
    emit('update:modelValue', val.substring(0, s) + '  ' + val.substring(e.target.selectionEnd))
    setTimeout(() => { e.target.selectionStart = e.target.selectionEnd = s + 2 }, 0)
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault()
    save()
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-1.5">
      <div class="flex items-center gap-1.5">
        <span class="font-mono text-xs opacity-40">Notes</span>
        <div class="join">
          <button class="btn btn-xs join-item" :class="!preview ? 'btn-neutral' : 'btn-ghost'" @click="preview = false">Edit</button>
          <button class="btn btn-xs join-item" :class="preview ? 'btn-neutral' : 'btn-ghost'" @click="preview = true">Preview</button>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="font-mono text-xs text-success transition-opacity duration-300" :class="saved ? 'opacity-100' : 'opacity-0'">saved</span>
        <button class="btn btn-ghost btn-xs btn-square opacity-40 hover:opacity-100" @click="save" title="Cmd+S">
          <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
            <polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>
          </svg>
        </button>
      </div>
    </div>
    <textarea
      v-if="!preview"
      :value="modelValue"
      @input="emit('update:modelValue', $event.target.value)"
      @keydown="handleKey"
      @blur="save"
      class="textarea textarea-bordered w-full text-xs font-mono leading-relaxed focus:outline-none bg-base-100"
      placeholder="Notes... markdown supported"
      rows="3"
      spellcheck="false"
    ></textarea>
    <div
      v-else
      v-html="rendered"
      class="min-h-12 px-3 py-2 rounded bg-base-100 border border-base-300 text-xs leading-relaxed opacity-80"
    ></div>
    <p v-if="!preview" class="font-mono text-xs opacity-30 mt-1">**bold** · *italic* · `code` · - list · Cmd+S</p>
  </div>
</template>
