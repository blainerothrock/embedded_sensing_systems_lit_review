import { ref } from 'vue'

export function useDebounce(fn, delay = 300) {
  let timer = null
  const pending = ref(false)

  function debounced(...args) {
    pending.value = true
    clearTimeout(timer)
    timer = setTimeout(() => {
      fn(...args)
      pending.value = false
    }, delay)
  }

  function cancel() {
    clearTimeout(timer)
    pending.value = false
  }

  return { debounced, cancel, pending }
}
