<script setup>
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useCodebookStore } from '@/stores/codebook'
import { useMatrixStore } from '@/stores/matrix'
import { useChatStore } from '@/stores/chat'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const codebook = useCodebookStore()
const matrix = useMatrixStore()
const chat = useChatStore()

function openCodeManager() {
  ui.showCodeManager = true
  codebook.loadCodes()
  codebook.loadUsageCounts()
}

function openColumnEditor() {
  ui.showColumnEditor = true
  matrix.loadColumns()
}

function switchToMatrix() {
  ui.setView('matrix')
  matrix.loadMatrixData()
}

function switchToThemes() {
  ui.setView('themes')
}

function toggleChat() {
  ui.showChat = !ui.showChat
  if (ui.showChat && workspace.activePaperId) {
    chat.loadChats(workspace.activePaperId)
  } else {
    chat.abort()
  }
}
</script>

<template>
  <div class="navbar bg-base-200 border-b border-base-300 px-2 h-12 min-h-0">
    <div class="flex-1 gap-2 flex items-center">
      <!-- Sidebar toggle -->
      <button class="btn btn-sm btn-ghost" @click="ui.sidebarOpen = !ui.sidebarOpen" title="Toggle paper list">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"/>
        </svg>
      </button>
      <div class="flex gap-1">
        <button class="btn btn-xs" :class="ui.view === 'papers' ? 'btn-primary' : 'btn-ghost'"
          @click="ui.setView('papers')">Papers</button>
        <button class="btn btn-xs" :class="ui.view === 'matrix' ? 'btn-primary' : 'btn-ghost'"
          @click="switchToMatrix()">Matrix</button>
        <button class="btn btn-xs" :class="ui.view === 'themes' ? 'btn-primary' : 'btn-ghost'"
          @click="switchToThemes()">Themes</button>
      </div>
      <!-- Paper navigation -->
      <div class="flex items-center gap-1 ml-2" v-show="ui.view === 'papers' && workspace.papers.length > 0">
        <button class="btn btn-xs btn-ghost" @click="workspace.prevPaper()" title="Previous paper (←)">◀</button>
        <span class="text-xs opacity-60 min-w-16 text-center">
          {{ workspace.activePaperId ? (workspace.currentPaperIndex + 1) + ' / ' + workspace.papers.length : '—' }}
        </span>
        <button class="btn btn-xs btn-ghost" @click="workspace.nextPaper()" title="Next paper (→)">▶</button>
      </div>
    </div>
    <div class="flex-none gap-3 flex items-center">
      <button class="btn btn-xs btn-ghost gap-1" @click="openCodeManager()">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z"/>
          <path stroke-linecap="round" stroke-linejoin="round" d="M6 6h.008v.008H6V6Z"/>
        </svg>
        Codes
      </button>
      <button class="btn btn-xs btn-ghost gap-1" @click="openColumnEditor()">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/>
        </svg>
        Columns
      </button>
      <button
        class="btn btn-xs gap-1"
        :class="ui.showChat ? 'btn-secondary' : 'btn-ghost'"
        @click="toggleChat()"
        v-show="ui.view === 'papers' && workspace.activePaper"
        title="Chat with paper"
      >
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M8.625 12a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H8.25m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0H12m4.125 0a.375.375 0 1 1-.75 0 .375.375 0 0 1 .75 0Zm0 0h-.375M21 12c0 4.556-4.03 8.25-9 8.25a9.764 9.764 0 0 1-2.555-.337A5.972 5.972 0 0 1 5.41 20.97a5.969 5.969 0 0 1-.474-.065 4.48 4.48 0 0 0 .978-2.025c.09-.457-.133-.901-.467-1.226C3.93 16.178 3 14.189 3 12c0-4.556 4.03-8.25 9-8.25s9 3.694 9 8.25Z"/>
        </svg>
        Chat
      </button>
      <div class="text-sm opacity-70" v-show="workspace.stats">
        {{ workspace.stats?.reviewed }}/{{ workspace.stats?.total }} reviewed
        · {{ workspace.stats?.has_pdf }} PDFs
      </div>
      <label class="swap swap-rotate btn btn-ghost btn-sm">
        <input type="checkbox" :checked="ui.theme === 'light'" @change="ui.toggleTheme()">
        <svg class="swap-on w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2.25m6.364.386-1.591 1.591M21 12h-2.25m-.386 6.364-1.591-1.591M12 18.75V21m-4.773-4.227-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 1 1-7.5 0 3.75 3.75 0 0 1 7.5 0Z"/>
        </svg>
        <svg class="swap-off w-5 h-5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M21.752 15.002A9.72 9.72 0 0 1 18 15.75c-5.385 0-9.75-4.365-9.75-9.75 0-1.33.266-2.597.748-3.752A9.753 9.753 0 0 0 3 11.25C3 16.635 7.365 21 12.75 21a9.753 9.753 0 0 0 8.002-5.998Z"/>
        </svg>
      </label>
    </div>
  </div>
</template>
