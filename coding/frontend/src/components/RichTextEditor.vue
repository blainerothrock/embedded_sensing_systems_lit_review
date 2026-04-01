<script setup>
import { ref, computed, nextTick } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: 'Click to edit...' },
  minHeight: { type: String, default: '3rem' },
})

const emit = defineEmits(['update:modelValue', 'save'])

const editing = ref(false)
const localValue = ref('')
const textarea = ref(null)

const renderedHtml = computed(() => {
  if (!props.modelValue) return ''
  return marked.parse(props.modelValue)
})

function startEditing() {
  localValue.value = props.modelValue || ''
  editing.value = true
  nextTick(() => {
    if (textarea.value) {
      textarea.value.focus()
      textarea.value.selectionStart = textarea.value.value.length
      autoResize()
    }
  })
}

function save() {
  emit('update:modelValue', localValue.value)
  emit('save', localValue.value)
  editing.value = false
}

function onBlur() {
  save()
}

function onKeydown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault()
    e.stopPropagation()
    save()
  }
  if (e.key === 'Tab') {
    e.preventDefault()
    const el = e.target
    const s = el.selectionStart
    localValue.value = localValue.value.substring(0, s) + '  ' + localValue.value.substring(el.selectionEnd)
    nextTick(() => { el.selectionStart = el.selectionEnd = s + 2 })
  }
}

function autoResize() {
  if (textarea.value) {
    textarea.value.style.height = 'auto'
    textarea.value.style.height = textarea.value.scrollHeight + 'px'
  }
}
</script>

<template>
  <div class="rich-text-editor">
    <!-- View mode: rendered markdown -->
    <div
      v-if="!editing"
      @click="startEditing"
      class="cursor-pointer rounded-md px-2.5 py-2 border border-base-content/10 bg-base-100 hover:border-primary/30 transition-colors"
      :style="{ minHeight: minHeight }"
    >
      <div
        v-if="renderedHtml"
        class="rendered-markdown text-xs leading-relaxed"
        v-html="renderedHtml"
      ></div>
      <p v-else class="text-xs opacity-30 italic">{{ placeholder }}</p>
    </div>

    <!-- Edit mode: plain markdown textarea -->
    <div v-show="editing" class="border border-primary/40 rounded-md bg-base-100 overflow-hidden ring-1 ring-primary/20">
      <textarea
        ref="textarea"
        v-model="localValue"
        @blur="onBlur"
        @keydown="onKeydown"
        @input="autoResize"
        :placeholder="placeholder"
        spellcheck="false"
        class="w-full px-2.5 py-2 bg-transparent text-xs font-mono leading-relaxed resize-none outline-none"
        :style="{ minHeight: minHeight }"
      ></textarea>
      <div class="flex items-center justify-between px-2.5 py-1 border-t border-base-content/5 bg-base-200/50">
        <span class="text-xs opacity-25 font-mono">**bold** · *italic* · `code` · - list · > quote</span>
        <span class="text-xs opacity-25 font-mono">⌘S</span>
      </div>
    </div>
  </div>
</template>

<style>
/* Rendered markdown in view mode */
.rendered-markdown p { margin: 0.25em 0; }
.rendered-markdown ul,
.rendered-markdown ol {
  padding-left: 1.25em;
  margin: 0.25em 0;
}
.rendered-markdown li { margin: 0.1em 0; }
.rendered-markdown blockquote {
  border-left: 3px solid oklch(var(--p));
  padding-left: 0.75em;
  margin: 0.25em 0;
  opacity: 0.8;
}
.rendered-markdown code {
  background: oklch(var(--b3));
  padding: 0.1em 0.3em;
  border-radius: 3px;
  font-size: 0.7rem;
  font-family: 'IBM Plex Mono', monospace;
}
.rendered-markdown pre {
  background: oklch(var(--b3));
  padding: 0.5em;
  border-radius: 4px;
  margin: 0.25em 0;
  overflow-x: auto;
}
.rendered-markdown pre code {
  background: none;
  padding: 0;
}
.rendered-markdown strong { font-weight: 600; }
.rendered-markdown em { font-style: italic; }
.rendered-markdown h1, .rendered-markdown h2, .rendered-markdown h3 {
  font-weight: 600;
  margin: 0.5em 0 0.25em;
}
.rendered-markdown h1 { font-size: 1.1em; }
.rendered-markdown h2 { font-size: 1em; }
.rendered-markdown h3 { font-size: 0.9em; }
</style>
