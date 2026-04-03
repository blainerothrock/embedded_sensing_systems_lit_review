<script setup>
import { ref, computed } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useCodebookStore } from '@/stores/codebook'
import CodeSelector from './CodeSelector.vue'
import RichTextEditor from './RichTextEditor.vue'

const workspace = useWorkspaceStore()
const codebook = useCodebookStore()

const annotationReturnTab = ref(null)

const ann = computed(() => workspace.activeAnnotation)
const regions = computed(() => workspace.annotationRegions)
const existingCodeIds = computed(() => (ann.value?.codes || []).map(c => c.id))

function wordCount(text) {
  if (!text) return 0
  return text.trim().split(/\s+/).filter(w => w).length
}

function goBack() {
  workspace.activeAnnotationId = null
}

function openDetail(annotation) {
  annotationReturnTab.value = null
  workspace.activeAnnotationId = annotation.id
}
</script>

<template>
  <div class="flex-1 overflow-y-auto">
    <!-- DETAIL VIEW -->
    <div v-if="ann" class="p-3 space-y-3">
      <button class="btn btn-xs btn-ghost gap-1" @click="goBack()">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18"/>
        </svg>
        Back to list
      </button>

      <div class="flex items-center gap-2 text-sm flex-wrap">
        <span class="badge badge-sm">{{ ann.annotation_type }}</span>
        <span class="text-xs opacity-50">{{ regions.length }} region{{ regions.length !== 1 ? 's' : '' }}</span>
        <span class="text-xs opacity-40" v-if="ann.created_at">{{ new Date(ann.created_at + 'Z').toLocaleDateString() }}</span>
      </div>

      <!-- Note (not collapsible, renders inline) -->
      <div>
        <label class="text-xs font-semibold uppercase opacity-60">Note</label>
        <div class="mt-1">
          <RichTextEditor
            :model-value="ann.note || ''"
            @save="(md) => workspace.saveAnnotationNote(ann.id, md)"
            placeholder="Free-form notes, thoughts, writing plans..."
            min-height="3rem"
          />
        </div>
      </div>

      <!-- Codes -->
      <div>
        <label class="text-xs font-semibold uppercase opacity-60">Codes ({{ (ann.codes || []).length }})</label>
        <div class="mt-1 space-y-2">
          <div v-for="c in ann.codes" :key="c.id" class="bg-base-300 rounded p-2">
            <div class="flex items-center gap-2">
              <div class="w-2.5 h-2.5 rounded-full flex-shrink-0" :style="{ background: c.color }"></div>
              <span class="text-sm font-medium flex-1">{{ c.name }}</span>
              <button class="btn btn-xs btn-ghost btn-error" @click="workspace.removeAnnotationCode(ann.id, c.id)">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>
                </svg>
              </button>
            </div>
            <!-- Code note (collapsible with word count) -->
            <div class="relative mt-1">
              <input :id="'cn-' + ann.id + '-' + c.id" type="checkbox" class="compact-collapse-toggle" :checked="!!c.ac_note">
              <label :for="'cn-' + ann.id + '-' + c.id" class="compact-collapse-header flex items-center gap-1 cursor-pointer py-0.5">
                <svg class="w-2.5 h-2.5 opacity-30 compact-collapse-arrow shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7"/></svg>
                <span class="text-xs opacity-40">note</span>
                <span v-if="c.ac_note" class="text-xs opacity-30">· {{ wordCount(c.ac_note) }}w</span>
              </label>
              <div class="compact-collapse-body">
                <div>
                  <div class="pt-1">
                    <RichTextEditor
                      :model-value="c.ac_note || ''"
                      @save="(md) => workspace.saveAnnotationCodeNote(ann.id, c.id, md)"
                      placeholder="Why this code? (optional note)"
                      min-height="1.5rem"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Add code button / picker -->
          <button
            v-if="!workspace.showCodePicker"
            class="badge badge-sm badge-ghost cursor-pointer gap-1"
            @click="workspace.showCodePicker = true; workspace.codePickerSearch = ''"
          >
            <svg class="w-3 h-3" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/>
            </svg>
            add code
          </button>
          <CodeSelector
            v-if="workspace.showCodePicker"
            :exclude-ids="existingCodeIds"
            @select="workspace.addAnnotationCode(ann.id, $event); codebook.loadUsageCounts()"
            @close="workspace.showCodePicker = false"
          />
        </div>
      </div>

      <!-- Regions -->
      <div>
        <label class="text-xs font-semibold uppercase opacity-60">Regions ({{ regions.length }})</label>
        <div class="mt-1 space-y-1.5">
          <div v-for="(region, idx) in regions" :key="idx" class="bg-base-300 rounded p-2 text-sm">
            <div class="flex items-center gap-2 mb-1">
              <span class="badge badge-xs badge-ghost">p.{{ region.page }}</span>
              <span class="text-xs opacity-50">{{ region.type === 'area' ? 'area' : 'highlight' }}</span>
              <div class="flex-1"></div>
              <button
                v-if="regions.length > 1"
                class="btn btn-ghost btn-xs btn-square opacity-30 text-error"
                @click="workspace.deleteRegion(idx)"
                title="Remove this region"
              >✕</button>
            </div>
            <p v-if="region.text" class="text-xs italic opacity-80 leading-relaxed">{{ region.text }}</p>
            <p v-else-if="region.type === 'area'" class="text-xs opacity-40">Area annotation</p>
          </div>
        </div>
      </div>

      <!-- Actions -->
      <div class="flex gap-2">
        <button class="btn btn-xs btn-ghost gap-1" @click="workspace.startAddRegion()" title="Add another highlight region">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/>
          </svg>
          Add region
        </button>
        <div class="flex-1"></div>
        <button class="btn btn-xs btn-error btn-ghost" @click="workspace.deleteAnnotation(ann.id)">Delete</button>
      </div>
    </div>

    <!-- LIST VIEW -->
    <div v-else class="p-3 space-y-2">
      <div class="flex items-center gap-2">
        <label class="text-sm font-semibold uppercase opacity-70 flex-1">
          Annotations ({{ workspace.annotations.length }})
        </label>
      </div>
      <div
        v-for="annotation in workspace.annotations"
        :key="annotation.id"
        class="p-2 bg-base-300 rounded-lg text-sm space-y-1.5 cursor-pointer hover:bg-base-200 transition-colors"
        @click="openDetail(annotation)"
      >
        <div class="flex items-start gap-2">
          <span class="badge badge-xs badge-ghost flex-shrink-0">p.{{ annotation.page_number }}</span>
          <p class="flex-1 text-xs italic opacity-80 line-clamp-2">{{ annotation.selected_text || annotation.note || '(area annotation)' }}</p>
        </div>
        <div class="flex flex-wrap gap-1">
          <span
            v-for="c in annotation.codes"
            :key="c.id"
            class="badge badge-xs"
            :style="{ background: c.color + '33', color: c.color, borderColor: c.color }"
          >{{ c.name }}</span>
        </div>
      </div>
      <div v-show="workspace.annotations.length === 0">
        <p class="text-sm opacity-50 text-center py-4">No annotations yet. Highlight text in the PDF or use the box tool.</p>
      </div>
    </div>
  </div>
</template>
