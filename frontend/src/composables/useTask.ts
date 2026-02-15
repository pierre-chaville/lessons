import { ref, onUnmounted } from 'vue'
import type { Ref } from 'vue'
import { tasksApi } from '@/api/tasks'
import type { Task } from '@/api/types'

/**
 * Polls a single task until it reaches a terminal state (completed | failed).
 *
 * @param taskId - Reactive ref holding the task ID to poll, or null when idle.
 *
 * @example
 * const taskId = ref<number | null>(null)
 * const { task, isPolling, start, stop } = useTask(taskId)
 *
 * // After creating a task:
 * taskId.value = createdTask.id
 * start()
 */
export function useTask(taskId: Ref<number | null>) {
  const task = ref<Task | null>(null)
  const isPolling = ref(false)
  let intervalId: number | null = null

  async function poll() {
    if (!taskId.value) return
    try {
      task.value = await tasksApi.get(taskId.value)
      if (task.value.status === 'completed' || task.value.status === 'failed') {
        stop()
      }
    } catch {
      stop()
    }
  }

  function start(intervalMs = 3000) {
    if (intervalId !== null) return // already polling
    isPolling.value = true
    poll()
    intervalId = window.setInterval(poll, intervalMs)
  }

  function stop() {
    if (intervalId !== null) {
      clearInterval(intervalId)
      intervalId = null
    }
    isPolling.value = false
  }

  // Always stop polling when the component is unmounted — prevents memory leaks.
  onUnmounted(stop)

  return { task, isPolling, start, stop }
}
