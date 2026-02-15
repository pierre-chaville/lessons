import { ref, readonly } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: number
  type: ToastType
  message: string
  /** Duration in ms. 0 = persist until manually dismissed. */
  duration: number
}

/**
 * Module-level state — shared across all components so toasts are visible
 * from anywhere in the app without a global store.
 */
const toasts = ref<Toast[]>([])
let nextId = 0

function add(message: string, type: ToastType, duration: number): number {
  const id = ++nextId
  toasts.value.push({ id, type, message, duration })
  if (duration > 0) {
    setTimeout(() => remove(id), duration)
  }
  return id
}

function remove(id: number): void {
  const index = toasts.value.findIndex((t) => t.id === id)
  if (index !== -1) toasts.value.splice(index, 1)
}

/**
 * Lightweight reactive toast system — no external library required.
 * Render `<ToastContainer />` (to be created in components/ui/) once in App.vue.
 *
 * @example
 * const toast = useToast()
 * toast.success(t('common.saved'))
 * toast.error(t('common.error'))
 */
export function useToast() {
  return {
    /** Read-only list of active toasts — bind to the toast container. */
    toasts: readonly(toasts),

    success: (message: string, duration = 4000) => add(message, 'success', duration),
    error:   (message: string, duration = 6000) => add(message, 'error',   duration),
    warning: (message: string, duration = 5000) => add(message, 'warning', duration),
    info:    (message: string, duration = 4000) => add(message, 'info',    duration),

    /** Dismiss a toast immediately by its ID. */
    remove,
  }
}
