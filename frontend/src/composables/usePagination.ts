import { ref, computed } from 'vue'

/**
 * Generic client-side pagination helper.
 * Works with any array — slice the source list with `{ offset, limit }` or `{ page, pageSize }`.
 *
 * @example
 * const { page, pageSize, total, totalPages, hasNext, hasPrev, next, prev, goTo, reset } =
 *   usePagination(20)
 *
 * // Set total after fetching:
 * total.value = lessons.length
 */
export function usePagination(initialPageSize = 20) {
  const page = ref(1)
  const pageSize = ref(initialPageSize)
  const total = ref(0)

  const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
  const hasNext = computed(() => page.value < totalPages.value)
  const hasPrev = computed(() => page.value > 1)

  /** Zero-based offset for use with array slicing or API params. */
  const offset = computed(() => (page.value - 1) * pageSize.value)

  function next() {
    if (hasNext.value) page.value++
  }

  function prev() {
    if (hasPrev.value) page.value--
  }

  function goTo(n: number) {
    page.value = Math.min(Math.max(1, n), totalPages.value)
  }

  function reset() {
    page.value = 1
  }

  return {
    page,
    pageSize,
    total,
    totalPages,
    hasNext,
    hasPrev,
    offset,
    next,
    prev,
    goTo,
    reset,
  }
}
