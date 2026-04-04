<script setup>
import { ref, nextTick, watch, computed, onMounted } from 'vue'
import { useWorkspaceStore } from '@/stores/workspace'
import { useChatStore } from '@/stores/chat'

const workspace = useWorkspaceStore()
const chat = useChatStore()

const chatMessagesEl = ref(null)

// Load chats and models when panel becomes visible
onMounted(() => {
  if (workspace.activePaperId) {
    chat.loadChats(workspace.activePaperId)
    chat.loadModels()
  }
})

// Reset chat when paper changes
watch(() => workspace.activePaperId, (paperId) => {
  if (paperId) {
    chat.chatId = null
    chat.messages = []
    chat.chatList = []
    chat.loadChats(paperId)
  }
})

// Auto-scroll on new messages
watch(() => chat.messages.length, () => {
  nextTick(() => scrollToBottom())
})
watch(() => chat.streamContent, () => {
  nextTick(() => scrollToBottom())
})

function scrollToBottom() {
  if (chatMessagesEl.value) {
    chatMessagesEl.value.scrollTop = chatMessagesEl.value.scrollHeight
  }
}

function send() {
  chat.sendMessage(workspace.activePaperId)
}

async function deleteCurrentChat() {
  if (!chat.chatId) return
  if (!confirm('Delete this conversation?')) return
  await chat.deleteChat(chat.chatId)
  await chat.loadChats(workspace.activePaperId)
}

function onMessagesClick(e) {
  // Handle page scroll links
  const scrollBtn = e.target.closest('[data-scroll-page]')
  if (scrollBtn) {
    const page = parseInt(scrollBtn.dataset.scrollPage)
    if (page) {
      const pageDiv = document.querySelector(`.pdf-page[data-page="${page}"]`)
      if (pageDiv) pageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
    return
  }
  // Handle quote links — scroll to page and briefly highlight
  const quoteEl = e.target.closest('[data-page][data-quote]')
  if (quoteEl) {
    const page = parseInt(quoteEl.dataset.page)
    const quoteText = quoteEl.dataset.quote
    if (page) {
      const pageDiv = document.querySelector(`.pdf-page[data-page="${page}"]`)
      if (pageDiv) {
        pageDiv.scrollIntoView({ behavior: 'smooth', block: 'center' })
        // Brief highlight overlay on the page
        if (quoteText) {
          const overlay = pageDiv.querySelector('.pdf-annotation-layer')
          if (overlay) {
            const hl = document.createElement('div')
            hl.className = 'chat-text-highlight'
            hl.style.left = '5%'
            hl.style.top = '5%'
            hl.style.width = '90%'
            hl.style.height = '90%'
            hl.style.opacity = '0.3'
            overlay.appendChild(hl)
            setTimeout(() => hl.remove(), 1500)
          }
        }
      }
    }
    return
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="bg-base-200 flex flex-col h-full min-h-0">
    <!-- Compact header: provider, model, conversation, actions -->
    <div class="px-2 py-1.5 border-b border-base-300 space-y-1 shrink-0">
      <div class="flex items-center gap-1">
        <select class="select select-xs flex-1" v-model="chat.provider">
          <option value="ollama">Ollama</option>
          <option value="claude">Claude</option>
        </select>
        <select v-if="chat.provider === 'ollama'" class="select select-xs flex-1" v-model="chat.model">
          <option v-for="m in chat.llmModels.ollama" :key="m" :value="m">{{ m }}</option>
        </select>
        <button
          v-if="chat.provider === 'ollama'"
          class="btn btn-ghost btn-xs btn-square opacity-50"
          :class="{ 'btn-active': chat.showParams }"
          @click="chat.showParams = !chat.showParams"
          title="Model parameters"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.212-1.281c-.063-.374-.313-.686-.645-.87a6.47 6.47 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z"/></svg>
        </button>
        <button class="btn btn-ghost btn-xs btn-square" @click="chat.newChat()" title="New conversation">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/>
          </svg>
        </button>
      </div>
      <!-- Params (expandable) -->
      <div v-if="chat.showParams && chat.provider === 'ollama'" class="grid grid-cols-2 gap-1.5">
        <template v-for="(val, key) in chat.params" :key="key">
          <label v-if="key === 'num_ctx' || key === 'num_predict'" class="flex flex-col">
            <span class="text-xs opacity-40">{{ key }}</span>
            <select
              class="select select-xs w-full bg-base-300"
              :value="val"
              @change="chat.params[key] = parseInt($event.target.value)"
            >
              <template v-if="key === 'num_ctx'">
                <option v-for="v in [2048, 4096, 8192, 16384, 32768, 65536, 131072]" :key="v" :value="v">{{ v.toLocaleString() }}</option>
              </template>
              <template v-else>
                <option v-for="v in [512, 1024, 2048, 4096, 8192]" :key="v" :value="v">{{ v.toLocaleString() }}</option>
              </template>
            </select>
          </label>
          <label v-else class="flex flex-col">
            <span class="text-xs opacity-40">{{ key }}</span>
            <input
              type="number"
              class="input input-xs w-full bg-base-300"
              :value="val"
              :step="key === 'temperature' || key === 'top_p' || key === 'presence_penalty' ? 0.1 : 1"
              @change="chat.params[key] = parseFloat($event.target.value)"
            >
          </label>
        </template>
      </div>
      <!-- Conversation selector -->
      <div v-if="chat.chatList.length >= 1" class="flex gap-1 items-center">
        <select class="select select-xs flex-1" :value="chat.chatId" @change="chat.loadMessages(parseInt($event.target.value))">
          <option v-for="c in chat.chatList" :key="c.id" :value="c.id">
            {{ c.title || 'Chat ' + c.id }}
          </option>
        </select>
        <button
          class="btn btn-ghost btn-xs btn-square opacity-40 text-error"
          @click="deleteCurrentChat()"
          title="Delete this conversation"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0"/>
          </svg>
        </button>
      </div>
      <!-- Prompt size estimate -->
      <div v-if="chat.promptTokenEstimate && chat.provider === 'ollama'" class="text-[10px] opacity-40">
        prompt ~{{ chat.promptTokenEstimate.toLocaleString() }} tokens ({{ Math.round((chat.promptTokenEstimate / chat.params.num_ctx) * 100) }}% of {{ chat.params.num_ctx.toLocaleString() }} ctx)
      </div>
    </div>

    <!-- Messages -->
    <div ref="chatMessagesEl" class="flex-1 overflow-y-auto p-3 space-y-3" @click="onMessagesClick">
      <template v-for="msg in chat.messages" :key="msg.id">
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="bg-primary text-primary-content rounded px-3 py-2 text-xs max-w-[80%] leading-relaxed">
            {{ msg.content }}
          </div>
        </div>
        <div v-else class="chat-md bg-base-300 rounded px-3 py-2 text-xs leading-relaxed max-w-[92%]" v-html="chat.renderChatContent(msg.content)">
        </div>
      </template>
      <!-- Streaming -->
      <div v-if="chat.streamContent" class="chat-md bg-base-300 rounded px-3 py-2 text-xs leading-relaxed max-w-[92%]" v-html="chat.renderChatContent(chat.streamContent)">
      </div>
      <div v-if="chat.loading && !chat.streamContent" class="flex gap-1 opacity-50">
        <span class="loading loading-dots loading-xs"></span>
      </div>
      <!-- Ollama generation metrics -->
      <div v-if="chat.metrics && chat.provider === 'ollama'" class="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] opacity-40 px-1">
        <span v-if="chat.metrics.ttft">TTFT {{ chat.metrics.ttft }}s</span>
        <span v-if="chat.metrics.tokPerSec">{{ chat.metrics.tokPerSec }} tok/s</span>
        <span v-if="chat.metrics.outputTokens">{{ chat.metrics.outputTokens }} tokens</span>
        <span v-if="chat.metrics.contextTokens">ctx {{ chat.metrics.contextTokens.toLocaleString() }} ({{ chat.metrics.contextPct }}%)</span>
        <span v-if="chat.metrics.totalTime">total {{ chat.metrics.totalTime }}s</span>
      </div>
    </div>

    <!-- Input -->
    <div class="p-2 border-t border-base-300">
      <div class="flex gap-1.5">
        <textarea
          class="textarea textarea-xs flex-1 resize-none"
          placeholder="Ask about this paper..."
          rows="1"
          v-model="chat.input"
          @keydown="handleKeydown"
        ></textarea>
        <button
          class="btn btn-primary btn-xs btn-square"
          @click="send()"
          :disabled="chat.loading || !chat.input.trim()"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
            <path d="m22 2-11 20-4-9-9-4z"/>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
