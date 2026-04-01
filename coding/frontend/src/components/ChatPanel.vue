<script setup>
import { ref, nextTick, watch, computed } from 'vue'
import { useUiStore } from '@/stores/ui'
import { useWorkspaceStore } from '@/stores/workspace'
import { useChatStore } from '@/stores/chat'

const ui = useUiStore()
const workspace = useWorkspaceStore()
const chat = useChatStore()

const chatMessagesEl = ref(null)

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

function closeChat() {
  ui.showChat = false
  chat.abort()
}

function handleKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="bg-base-200 flex flex-col h-full">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 py-2.5 border-b border-base-300">
      <span class="text-sm font-medium">Chat</span>
      <div class="flex gap-1">
        <button class="btn btn-ghost btn-xs btn-square" @click="chat.newChat()" title="New conversation">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M12 4.5v15m7.5-7.5h-15"/>
          </svg>
        </button>
        <button class="btn btn-ghost btn-xs btn-square" @click="closeChat()">
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M6 18 18 6M6 6l12 12"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Provider / Model -->
    <div class="px-3 py-2 border-b border-base-300 space-y-1.5">
      <select class="select select-xs w-full" v-model="chat.provider">
        <option value="ollama">Ollama</option>
        <option value="claude">Claude</option>
      </select>
      <select v-if="chat.provider === 'ollama'" class="select select-xs w-full" v-model="chat.model">
        <option v-for="m in chat.llmModels.ollama" :key="m" :value="m">{{ m }}</option>
      </select>
    </div>

    <!-- Conversation list -->
    <div v-if="chat.chatList.length > 1" class="px-3 py-1 border-b border-base-300">
      <select class="select select-xs w-full" :value="chat.chatId" @change="chat.loadMessages(parseInt($event.target.value))">
        <option v-for="c in chat.chatList" :key="c.id" :value="c.id">
          {{ c.title || 'Chat ' + c.id }}
        </option>
      </select>
    </div>

    <!-- Messages -->
    <div ref="chatMessagesEl" class="flex-1 overflow-y-auto p-3 space-y-3">
      <template v-for="msg in chat.messages" :key="msg.id">
        <div v-if="msg.role === 'user'" class="flex justify-end">
          <div class="bg-primary text-primary-content rounded px-3 py-2 text-xs max-w-[80%] leading-relaxed">
            {{ msg.content }}
          </div>
        </div>
        <div v-else class="bg-base-300 rounded px-3 py-2 text-xs leading-relaxed max-w-[92%]" v-html="chat.renderChatContent(msg.content)">
        </div>
      </template>
      <!-- Streaming -->
      <div v-if="chat.streamContent" class="bg-base-300 rounded px-3 py-2 text-xs leading-relaxed max-w-[92%]" v-html="chat.renderChatContent(chat.streamContent)">
      </div>
      <div v-if="chat.loading && !chat.streamContent" class="flex gap-1 opacity-50">
        <span class="loading loading-dots loading-xs"></span>
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
