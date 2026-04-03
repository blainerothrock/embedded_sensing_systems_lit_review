import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '@/api'
import { useUiStore } from './ui'

export const useChatStore = defineStore('chat', () => {
  const chatList = ref([])
  const chatId = ref(null)
  const messages = ref([])
  const input = ref('')
  const loading = ref(false)
  const streamContent = ref('')
  const provider = ref('ollama')
  const model = ref('')
  const llmModels = ref({ ollama: [], claude: true })
  const showParams = ref(false)
  const params = ref({
    num_ctx: 32768,
    num_predict: 2048,
    temperature: 0.6,
    top_k: 20,
    top_p: 0.95,
    presence_penalty: 1.5,
  })

  let abortController = null

  const activeMessages = computed(() => messages.value)

  function abort() {
    if (abortController) {
      abortController.abort()
      abortController = null
    }
    loading.value = false
    streamContent.value = ''
  }

  async function loadModels() {
    const data = await api.llmModels()
    llmModels.value = { ollama: data.ollama || [], claude: data.claude }
    if (data.default_params) {
      params.value = { ...params.value, ...data.default_params }
    }
    if (!model.value && llmModels.value.ollama.length > 0) {
      model.value = llmModels.value.ollama[0]
    }
  }

  async function loadChats(paperId) {
    chatList.value = await api.chat.list(paperId)
    if (!chatId.value && chatList.value.length > 0) {
      await loadMessages(chatList.value[0].id)
    }
  }

  async function loadMessages(id) {
    abort()
    chatId.value = id
    messages.value = await api.chat.messages(id)
    const chat = chatList.value.find(c => c.id === id)
    if (chat) {
      provider.value = chat.provider || 'ollama'
      model.value = chat.model || ''
      if (chat.params) {
        try { params.value = { ...params.value, ...JSON.parse(chat.params) } } catch {}
      }
    }
  }

  function newChat() {
    abort()
    chatId.value = null
    messages.value = []
  }

  async function deleteChat(id) {
    await api.chat.delete(id)
    if (chatId.value === id) {
      chatId.value = null
      messages.value = []
    }
  }

  async function sendMessage(paperId) {
    const ui = useUiStore()
    const message = input.value.trim()
    if (!message || loading.value || !paperId) return

    abort()
    input.value = ''
    messages.value.push({ role: 'user', content: message, id: Date.now() })
    loading.value = true
    streamContent.value = ''

    abortController = new AbortController()

    try {
      const res = await fetch(`/api/papers/${paperId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message,
          chat_id: chatId.value,
          provider: provider.value,
          model: model.value,
          params: provider.value === 'ollama' ? params.value : null,
        }),
        signal: abortController.signal,
      })

      const reader = res.body.getReader()
      const decoder = new TextDecoder()

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value, { stream: true })
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = JSON.parse(line.slice(6))

          if (data.type === 'chat_id') {
            chatId.value = data.chat_id
          } else if (data.type === 'text') {
            streamContent.value += data.text
          } else if (data.type === 'done') {
            messages.value.push({
              role: 'assistant',
              content: streamContent.value,
              id: Date.now(),
            })
            streamContent.value = ''
            await loadChats(paperId)
          } else if (data.type === 'error') {
            ui.showToast(data.error, 'error')
          }
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        ui.showToast('Chat failed: ' + err.message, 'error')
      }
    }
    abortController = null
    loading.value = false
  }

  function escapeHtml(text) {
    const div = document.createElement('div')
    div.textContent = text
    return div.innerHTML
  }

  function renderChatContent(content) {
    // Parse quote/page links BEFORE escaping so we work with raw text
    // Replace [[quote:"..." p.N]] with placeholder tokens, then escape, then restore
    const quotes = []
    let processed = content.replace(/\[\[quote:"([\s\S]*?)"\s+p\.(\d+)\]\]/g, (match, text, page) => {
      const idx = quotes.length
      quotes.push({ text: text.replace(/\n/g, ' ').trim(), page })
      return `%%QUOTE_${idx}%%`
    })
    const pageRefs = []
    processed = processed.replace(/\[\[p\.(\d+)\]\]/g, (match, page) => {
      const idx = pageRefs.length
      pageRefs.push(page)
      return `%%PAGE_${idx}%%`
    })

    let html = escapeHtml(processed)

    // Restore quote placeholders
    for (let i = 0; i < quotes.length; i++) {
      const q = quotes[i]
      const escaped = escapeHtml(q.text)
      html = html.replace(`%%QUOTE_${i}%%`,
        `<div class="chat-quote cursor-pointer" data-page="${q.page}" data-quote="${escaped}"><span class="italic">&ldquo;${escaped}&rdquo;</span> <span class="badge badge-xs badge-primary">p.${q.page}</span></div>`)
    }
    // Restore page ref placeholders
    for (let i = 0; i < pageRefs.length; i++) {
      html = html.replace(`%%PAGE_${i}%%`,
        `<button class="badge badge-xs badge-primary cursor-pointer mx-0.5" data-scroll-page="${pageRefs[i]}">p.${pageRefs[i]}</button>`)
    }
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-base-300 rounded p-2 text-xs my-1 overflow-x-auto"><code>$2</code></pre>')
    html = html.replace(/`([^`]+)`/g, '<code class="bg-base-300 rounded px-1 text-xs">$1</code>')
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')
    html = html.replace(/\n/g, '<br>')
    return html
  }

  return {
    chatList, chatId, messages, input, loading, streamContent,
    provider, model, llmModels, showParams, params,
    activeMessages,
    abort, loadModels, loadChats, loadMessages,
    newChat, deleteChat, sendMessage, renderChatContent,
  }
})
