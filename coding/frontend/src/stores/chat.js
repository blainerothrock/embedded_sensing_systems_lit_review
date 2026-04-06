import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { marked } from 'marked'
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
  const llmModels = ref({ ollama: [], claude: true, vllm: [] })
  const showParams = ref(false)
  const params = ref({
    num_ctx: 32768,
    num_predict: 2048,
    temperature: 0.0,
    top_k: 20,
    top_p: 0.95,
    presence_penalty: 1.5,
  })

  const gpuServerStatus = ref({ vllm: 'off' })

  // Metrics for the current/last generation (Ollama/vLLM)
  const metrics = ref(null)
  const promptTokenEstimate = ref(null)
  let abortController = null
  let sendTimestamp = null
  let firstTokenTimestamp = null

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
    llmModels.value = {
      ollama: data.ollama || [],
      claude: data.claude,
      vllm: data.vllm?.models || [],
    }
    if (data.vllm) gpuServerStatus.value = data.vllm
    if (data.default_params) {
      params.value = { ...params.value, ...data.default_params }
    }
    if (!model.value) {
      _setDefaultModel()
    }
  }

  function _setDefaultModel() {
    if (provider.value === 'ollama' && llmModels.value.ollama.length > 0) {
      model.value = llmModels.value.ollama[0]
    } else if (provider.value === 'vllm' && llmModels.value.vllm.length > 0) {
      model.value = llmModels.value.vllm[0]
    } else if (provider.value === 'claude') {
      model.value = 'claude'
    }
  }

  // Auto-set model when provider changes
  watch(provider, () => {
    _setDefaultModel()
  })

  async function loadChats(paperId) {
    chatList.value = await api.chat.list(paperId)
    if (!chatId.value && chatList.value.length > 0) {
      await loadMessages(chatList.value[0].id)
    }
    // Load prompt size estimate for this paper
    try {
      const data = await api.promptSize(paperId)
      promptTokenEstimate.value = data.estimated_tokens
    } catch { promptTokenEstimate.value = null }
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
    metrics.value = null
    sendTimestamp = performance.now()
    firstTokenTimestamp = null

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
          params: (provider.value === 'ollama' || provider.value === 'vllm') ? params.value : null,
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
            if (!firstTokenTimestamp) firstTokenTimestamp = performance.now()
            streamContent.value += data.text
          } else if (data.type === 'metrics') {
            // Ollama metrics from final chunk
            const m = {}
            m.ttft = firstTokenTimestamp ? ((firstTokenTimestamp - sendTimestamp) / 1000).toFixed(1) : null
            if (data.prompt_eval_count) {
              m.contextTokens = data.prompt_eval_count
              const numCtx = params.value.num_ctx || 32768
              m.contextPct = Math.round((data.prompt_eval_count / numCtx) * 100)
            }
            if (data.eval_count) m.outputTokens = data.eval_count
            if (data.eval_count && data.eval_duration) {
              m.tokPerSec = (data.eval_count / (data.eval_duration / 1e9)).toFixed(1)
            }
            if (data.total_duration) m.totalTime = (data.total_duration / 1e9).toFixed(1)
            metrics.value = m
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
    // Extract quote/page links BEFORE markdown parsing so they don't get mangled
    const quotes = []
    // Format 1: [[quote:"text" p.N]]
    let processed = content.replace(/\[\[quote:"([\s\S]*?)"\s+p\.(\d+)\]\]/g, (match, text, page) => {
      const idx = quotes.length
      quotes.push({ text: text.replace(/\n/g, ' ').trim(), page })
      return `XQUOTE${idx}X`
    })
    // Format 2: Markdown blockquote with quoted text and [[p.N]] — e.g.:
    //   > "some text" [[p.14]]
    //   > "some text..." [[p.14]]
    processed = processed.replace(/^>\s*[""\u201c]([\s\S]*?)[""\u201d]\.?\s*\[\[p\.(\d+)\]\]\s*$/gm, (match, text, page) => {
      const idx = quotes.length
      quotes.push({ text: text.replace(/\n>\s*/g, ' ').replace(/\n/g, ' ').trim(), page })
      return `XQUOTE${idx}X`
    })
    // Format 3: Inline quoted text followed by [[p.N]] — e.g.:
    //   "some text" [[p.14]]
    //   "some text" [[p.2], [p.15]]
    processed = processed.replace(/[""\u201c]([^"""\u201c\u201d\n]{15,}?)[""\u201d]\s*\[\[p\.(\d+)(?:\](?:,\s*\[p\.\d+))*\]\]/g, (match, text, page) => {
      const idx = quotes.length
      quotes.push({ text: text.trim(), page })
      return `XQUOTE${idx}X`
    })
    const pageRefs = []
    // Handle [[p.9], [p.10]] grouped refs — split into individual badges
    processed = processed.replace(/\[\[p\.([\d.]+)(?:\],\s*\[p\.([\d.]+))*\]\]/g, (match) => {
      const pages = [...match.matchAll(/p\.([\d.]+)/g)]
      return pages.map(m => {
        const page = m[1].split('.')[0] // use integer part only
        const idx = pageRefs.length
        pageRefs.push(page)
        return `XPAGE${idx}X`
      }).join(' ')
    })
    // Handle individual [[p.N]] or [[p.N.N]] refs
    processed = processed.replace(/\[\[p\.([\d.]+)\]\]/g, (match, pageStr) => {
      const page = pageStr.split('.')[0] // use integer part only
      const idx = pageRefs.length
      pageRefs.push(page)
      return `XPAGE${idx}X`
    })

    // Parse markdown (marked escapes HTML by default)
    let html = marked.parse(processed, { breaks: true })

    // Restore quote placeholders
    for (let i = 0; i < quotes.length; i++) {
      const q = quotes[i]
      const escaped = escapeHtml(q.text)
      html = html.replace(`XQUOTE${i}X`,
        `<span class="chat-quote cursor-pointer inline-block w-full" data-page="${q.page}" data-quote="${escaped}"><span class="italic">&ldquo;${escaped}&rdquo;</span> <span class="badge badge-xs badge-primary">p.${q.page}</span></span>`)
    }
    // Restore page ref placeholders
    for (let i = 0; i < pageRefs.length; i++) {
      html = html.replace(`XPAGE${i}X`,
        `<button class="badge badge-xs badge-primary cursor-pointer mx-0.5" data-scroll-page="${pageRefs[i]}">p.${pageRefs[i]}</button>`)
    }
    return html
  }

  return {
    chatList, chatId, messages, input, loading, streamContent,
    provider, model, llmModels, showParams, params, metrics, promptTokenEstimate,
    gpuServerStatus, activeMessages,
    abort, loadModels, loadChats, loadMessages,
    newChat, deleteChat, sendMessage, renderChatContent,
  }
})
