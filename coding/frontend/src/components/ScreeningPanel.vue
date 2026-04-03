<script setup>
import { useWorkspaceStore } from '@/stores/workspace'
import RichTextEditor from './RichTextEditor.vue'

const workspace = useWorkspaceStore()
</script>

<template>
  <div class="flex-1 overflow-y-auto p-3 space-y-4">
    <div class="space-y-2">
      <label class="text-sm font-semibold uppercase opacity-70">Decision</label>
      <div class="flex gap-1">
        <button
          class="btn btn-sm flex-1 gap-1"
          :class="workspace.reviewForm.decision === 'include' ? 'btn-success' : 'btn-ghost'"
          @click="workspace.reviewForm.decision = 'include'"
        >Include</button>
        <button
          class="btn btn-sm flex-1 gap-1"
          :class="workspace.reviewForm.decision === 'exclude' ? 'btn-error' : 'btn-ghost'"
          @click="workspace.reviewForm.decision = 'exclude'"
        >Exclude</button>
        <button
          class="btn btn-sm flex-1 gap-1"
          :class="workspace.reviewForm.decision === 'uncertain' ? 'btn-warning' : 'btn-ghost'"
          @click="workspace.reviewForm.decision = 'uncertain'"
        >Unsure</button>
      </div>
    </div>
    <div class="space-y-2" v-show="workspace.reviewForm.decision === 'exclude'">
      <label class="text-sm font-semibold uppercase opacity-70">Exclusion Codes</label>
      <label
        v-for="ec in workspace.exclusionCodes"
        :key="ec.id"
        class="flex items-start gap-2 cursor-pointer py-0.5"
      >
        <input
          type="checkbox"
          class="checkbox checkbox-xs checkbox-error mt-0.5"
          :checked="workspace.reviewForm.exclusion_code_ids.includes(ec.id)"
          @change="workspace.toggleExclusionCode(ec.id)"
        >
        <span class="text-sm">
          <strong>{{ ec.code }}</strong>:
          <span class="opacity-70">{{ ec.description }}</span>
        </span>
      </label>
    </div>
    <div class="space-y-1">
      <label class="text-sm font-semibold uppercase opacity-70">Notes</label>
      <RichTextEditor
        v-model="workspace.reviewForm.notes"
        placeholder="Review notes..."
        min-height="4rem"
      />
    </div>
    <button
      class="btn btn-sm btn-primary w-full gap-2"
      :disabled="!workspace.reviewForm.decision"
      @click="workspace.saveReview()"
    >Save Review</button>
    <div v-show="workspace.activePaper?.phase3_decision === 'include'" class="space-y-2 pt-2 border-t border-base-300">
      <label class="text-sm font-semibold uppercase opacity-70">Coding Status</label>
      <div class="flex gap-1">
        <button
          class="btn btn-xs flex-1"
          :class="!workspace.activePaper?.coding_status ? 'btn-info' : 'btn-ghost'"
          @click="workspace.setCodingStatus(null)"
        >Included</button>
        <button
          class="btn btn-xs flex-1"
          :class="workspace.activePaper?.coding_status === 'coding' ? 'btn-warning' : 'btn-ghost'"
          @click="workspace.setCodingStatus('coding')"
        >In Progress</button>
        <button
          class="btn btn-xs flex-1"
          :class="workspace.activePaper?.coding_status === 'complete' ? 'btn-success' : 'btn-ghost'"
          @click="workspace.setCodingStatus('complete')"
        >Complete</button>
      </div>
    </div>
    <div v-show="workspace.activePaper && !workspace.activePaper.pdf_path" class="pt-2">
      <label class="btn btn-sm btn-outline w-full gap-2">
        Upload PDF
        <input type="file" accept=".pdf" class="hidden" @change="workspace.uploadPdf($event.target.files[0])">
      </label>
    </div>
  </div>
</template>
