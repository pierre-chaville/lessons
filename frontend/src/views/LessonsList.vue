<script setup lang="ts">
import { ref, onMounted, computed, watch, onBeforeUnmount, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  DocumentTextIcon,
  FolderIcon,
  CalendarDaysIcon,
  ClockIcon,
  MagnifyingGlassIcon,
  FunnelIcon,
  CheckIcon,
  XMarkIcon,
  BarsArrowDownIcon,
  BarsArrowUpIcon,
  ArrowsUpDownIcon,
} from '@heroicons/vue/24/outline'
import { Menu, MenuButton, MenuItems, MenuItem } from '@headlessui/vue'
import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import LessonDetail from './LessonDetail.vue'
import CreateLessonModal from '../components/CreateLessonModal.vue'
import CourseTreeItem from '@/components/CourseTreeItem.vue'
import { lessonsApi } from '@/api/lessons'
import { coursesApi } from '@/api/courses'
import { useAuth } from '@/composables/useAuth'
import type {
  ContentType,
  CourseTreeNode,
  LessonListItem,
  LessonDetail as LessonDetailType,
  LessonStatus,
} from '@/api/types'

const { t } = useI18n()
const { user } = useAuth()

type SortMode = 'date_desc' | 'date_asc' | 'name' | 'status'

const STATUS_ORDER: Record<LessonStatus, number> = {
  draft: 0,
  in_progress: 1,
  revision_requested: 2,
  review_requested: 3,
  validated: 4,
}

const lessons = ref<LessonListItem[]>([])
const tree = ref<CourseTreeNode[]>([])
const loading = ref(true)
const loadingTree = ref(true)
const selectedLesson = ref<LessonListItem | null>(null)
const selectedLessonDetail = ref<LessonDetailType | null>(null)
const selectedHistoryRoute = ref<{
  contentType: ContentType
  versionId: string | null
  compare:
    | {
        versionAId: string
        versionBId: string
      }
    | null
} | null>(null)
const showCreateModal = ref(false)
const sortMode = ref<SortMode>('date_desc')
const titleQuery = ref('')
const selectedHebrewYears = ref<Set<string>>(new Set())
const selectedStatuses = ref<Set<LessonStatus>>(new Set())
const selectedThemeIds = ref<Set<number>>(new Set())

const STATUS_FILTERS: LessonStatus[] = [
  'draft',
  'in_progress',
  'review_requested',
  'revision_requested',
  'validated',
]

const availableHebrewYears = computed<string[]>(() => {
  const years = new Set<string>()
  for (const lesson of lessons.value) {
    const year = (lesson.hebrew_year || lesson.hebrew_date)?.trim()
    if (year) years.add(year)
  }
  return [...years].sort((a, b) => Number(b) - Number(a))
})

const availableThemes = computed<Array<{ id: number; name: string }>>(() => {
  const byId = new Map<number, string>()
  for (const lesson of lessons.value) {
    for (const theme of lesson.themes ?? []) {
      if (!byId.has(theme.id)) byId.set(theme.id, theme.name)
    }
  }
  return [...byId.entries()]
    .map(([id, name]) => ({ id, name }))
    .sort((a, b) => a.name.localeCompare(b.name))
})

const toggleSetValue = <T,>(setRef: { value: Set<T> }, value: T) => {
  const next = new Set(setRef.value)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  setRef.value = next
}

const toggleHebrewYear = (year: string) => toggleSetValue(selectedHebrewYears, year)
const toggleStatusFilter = (status: LessonStatus) => toggleSetValue(selectedStatuses, status)
const toggleThemeFilter = (themeId: number) => toggleSetValue(selectedThemeIds, themeId)

const hasActiveFilters = computed(() =>
  !!titleQuery.value.trim()
  || selectedHebrewYears.value.size > 0
  || selectedStatuses.value.size > 0
  || selectedThemeIds.value.size > 0,
)

const clearAllFilters = () => {
  titleQuery.value = ''
  selectedHebrewYears.value = new Set()
  selectedStatuses.value = new Set()
  selectedThemeIds.value = new Set()
}

const clearTitleQuery = () => {
  titleQuery.value = ''
}

const clearHebrewYears = () => {
  selectedHebrewYears.value = new Set()
}

const clearStatuses = () => {
  selectedStatuses.value = new Set()
}

const clearThemes = () => {
  selectedThemeIds.value = new Set()
}

const filteredLessons = computed(() => {
  const query = titleQuery.value.trim().toLowerCase()
  return lessons.value.filter((lesson) => {
    if (query && !lesson.title.toLowerCase().includes(query)) return false
    if (selectedHebrewYears.value.size > 0) {
      const year = (lesson.hebrew_year || lesson.hebrew_date)?.trim() ?? ''
      if (!selectedHebrewYears.value.has(year)) return false
    }
    if (selectedStatuses.value.size > 0 && !selectedStatuses.value.has(lesson.status)) return false
    if (selectedThemeIds.value.size > 0) {
      const hasMatchingTheme = (lesson.themes ?? []).some((theme) => selectedThemeIds.value.has(theme.id))
      if (!hasMatchingTheme) return false
    }
    return true
  })
})

const sortedLessons = computed(() => {
  const list = [...filteredLessons.value]
  switch (sortMode.value) {
    case 'date_desc':
      return list.sort((a, b) => (b.date ?? '').localeCompare(a.date ?? ''))
    case 'date_asc':
      return list.sort((a, b) => (a.date ?? '').localeCompare(b.date ?? ''))
    case 'name':
      return list.sort((a, b) => (a.title ?? '').localeCompare(b.title ?? ''))
    case 'status':
      return list.sort((a, b) => STATUS_ORDER[a.status] - STATUS_ORDER[b.status])
    default:
      return list
  }
})

const sortOptions: { key: SortMode; labelKey: string }[] = [
  { key: 'date_desc', labelKey: 'lessons.sortDateDesc' },
  { key: 'date_asc', labelKey: 'lessons.sortDateAsc' },
  { key: 'name', labelKey: 'lessons.sortName' },
  { key: 'status', labelKey: 'lessons.sortStatus' },
]

const layoutRef = ref<HTMLElement | null>(null)
const expanded = ref<Set<number>>(new Set())
const selectedCourseId = ref<number | null>(null)
const panelWidth = ref(288)
const isResizing = ref(false)
const lessonsFetchSeq = ref(0)

const MIN_PANEL_WIDTH = 240
const MAX_PANEL_WIDTH = 560
const PANEL_STATE_KEY_PREFIX = 'lessons.courses-panel.v1'
const HOME_TOUR_STATE_KEY_PREFIX = 'lessons.home-tour.v1'

const getHomeTourStateKey = (): string => {
  const userId = user.value?.id ?? 'anonymous'
  return `${HOME_TOUR_STATE_KEY_PREFIX}:${userId}`
}

let homeTourInstance: ReturnType<typeof driver> | null = null

const getPanelStateKey = (): string => {
  const userId = user.value?.id ?? 'anonymous'
  return `${PANEL_STATE_KEY_PREFIX}:${userId}`
}

const collectTreeIds = (nodes: CourseTreeNode[]): number[] => {
  const ids: number[] = []
  for (const n of nodes) {
    ids.push(n.id, ...collectTreeIds(n.children))
  }
  return ids
}

const findNodeById = (nodes: CourseTreeNode[], id: number): CourseTreeNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node
    const found = findNodeById(node.children, id)
    if (found) return found
  }
  return null
}

const findPathToNode = (
  nodes: CourseTreeNode[],
  id: number,
  path: CourseTreeNode[] = [],
): CourseTreeNode[] | null => {
  for (const node of nodes) {
    const nextPath = [...path, node]
    if (node.id === id) return nextPath
    const nestedPath = findPathToNode(node.children, id, nextPath)
    if (nestedPath) return nestedPath
  }
  return null
}

const selectedCourseNode = computed<CourseTreeNode | null>(() => {
  if (!selectedCourseId.value) return null
  return findNodeById(tree.value, selectedCourseId.value)
})

const selectedCoursePath = computed<string[]>(() => {
  if (!selectedCourseId.value) return []
  return findPathToNode(tree.value, selectedCourseId.value)?.map((node) => node.name) ?? []
})

const coursePathById = computed<Map<number, string>>(() => {
  const map = new Map<number, string>()
  const walk = (nodes: CourseTreeNode[], path: string[] = []) => {
    for (const node of nodes) {
      const nextPath = [...path, node.name]
      map.set(node.id, nextPath.join(' / '))
      walk(node.children, nextPath)
    }
  }
  walk(tree.value)
  return map
})

const getCoursePathLabel = (lesson: LessonListItem): string | null => {
  if (!lesson.course) return null
  return coursePathById.value.get(lesson.course.id) ?? lesson.course.name
}

const persistPanelState = () => {
  const payload = {
    selectedCourseId: selectedCourseId.value,
    expandedIds: [...expanded.value],
    panelWidth: panelWidth.value,
  }
  localStorage.setItem(getPanelStateKey(), JSON.stringify(payload))
}

const restorePanelState = () => {
  const raw = localStorage.getItem(getPanelStateKey())
  if (!raw) return

  try {
    const parsed = JSON.parse(raw) as {
      selectedCourseId?: number | null
      expandedIds?: number[]
      panelWidth?: number
    }
    selectedCourseId.value = typeof parsed.selectedCourseId === 'number' ? parsed.selectedCourseId : null
    expanded.value = new Set(
      Array.isArray(parsed.expandedIds)
        ? parsed.expandedIds.filter((id) => typeof id === 'number')
        : [],
    )
    if (typeof parsed.panelWidth === 'number') {
      panelWidth.value = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, parsed.panelWidth))
    }
  } catch {
    // ignore malformed persisted state
  }
}

const toggleExpand = (id: number) => {
  if (expanded.value.has(id)) {
    expanded.value.delete(id)
  } else {
    expanded.value.add(id)
  }
  persistPanelState()
}

const collectDescendantIds = (node: CourseTreeNode): number[] => {
  const ids = [node.id]
  for (const child of node.children) {
    ids.push(...collectDescendantIds(child))
  }
  return ids
}

const selectCourseNode = (node: CourseTreeNode) => {
  selectedCourseId.value = node.id
  persistPanelState()
}

const HISTORY_CONTENT_TYPES: ContentType[] = [
  'title',
  'corrected_transcript',
  'edited_transcript',
  'brief',
  'summary',
]

const parseLessonRoute = (): {
  hashid: string | null
  historyContentType: ContentType | null
  versionId: string | null
  compare:
    | {
        versionAId: string
        versionBId: string
      }
    | null
} => {
  const match = window.location.pathname.match(
    /^\/lessons\/([a-zA-Z0-9]+)(?:\/([a-z_]+)\/history)?\/?$/,
  )
  if (!match) {
    return { hashid: null, historyContentType: null, versionId: null, compare: null }
  }

  const contentTypeCandidate = match[2] as ContentType | undefined
  const historyContentType =
    contentTypeCandidate && HISTORY_CONTENT_TYPES.includes(contentTypeCandidate)
      ? contentTypeCandidate
      : null

  if (match[2] && !historyContentType) {
    return { hashid: null, historyContentType: null, versionId: null, compare: null }
  }

  const params = new URLSearchParams(window.location.search)
  const versionId = historyContentType ? params.get('version') : null
  const compareRaw = historyContentType ? params.get('compare') : null
  let compare: { versionAId: string; versionBId: string } | null = null
  if (compareRaw) {
    const [versionAId, versionBId] = compareRaw.split(',')
    if (versionAId && versionBId) {
      compare = { versionAId, versionBId }
    }
  }

  return { hashid: match[1], historyContentType, versionId, compare }
}

const updateUrl = (
  hashid: string | null,
  historyRoute?: {
    contentType: ContentType
    versionId: string | null
    compare:
      | {
          versionAId: string
          versionBId: string
        }
      | null
  } | null,
) => {
  if (hashid) {
    if (historyRoute) {
      const query = new URLSearchParams()
      if (historyRoute.versionId) query.set('version', historyRoute.versionId)
      if (historyRoute.compare) query.set('compare', `${historyRoute.compare.versionAId},${historyRoute.compare.versionBId}`)
      const search = query.toString() ? `?${query.toString()}` : ''
      window.history.pushState(
        { hashid, history: historyRoute },
        '',
        `/lessons/${hashid}/${historyRoute.contentType}/history${search}`,
      )
      return
    }
    window.history.pushState({ hashid }, '', `/lessons/${hashid}`)
  } else {
    window.history.pushState({}, '', '/lessons')
  }
}

const handlePopState = (event: PopStateEvent) => {
  const parsedRoute = parseLessonRoute()
  const hashid = event.state?.hashid ?? parsedRoute.hashid
  const historyRoute =
    parsedRoute.historyContentType
      ? {
          contentType: parsedRoute.historyContentType,
          versionId: parsedRoute.versionId,
          compare: parsedRoute.compare,
        }
      : null
  if (hashid) {
    const lesson = lessons.value.find((l) => l.hashid === hashid)
    if (lesson) {
      openLesson(lesson, historyRoute, false)
    } else {
      fetchLessonByHashid(hashid, historyRoute, false)
    }
  } else {
    closeLesson()
  }
}

const fetchTree = async () => {
  try {
    loadingTree.value = true
    tree.value = await coursesApi.tree()

    const validIds = new Set(collectTreeIds(tree.value))
    if (selectedCourseId.value !== null && !validIds.has(selectedCourseId.value)) {
      selectedCourseId.value = null
    }
    expanded.value = new Set([...expanded.value].filter((id) => validIds.has(id)))
    persistPanelState()
  } catch { /* silent */ } finally {
    loadingTree.value = false
  }
}

const fetchLessons = async () => {
  const requestSeq = ++lessonsFetchSeq.value
  const selectedId = selectedCourseId.value
  const selectedNode =
    selectedId !== null ? findNodeById(tree.value, selectedId) : null

  // If a course is selected but tree is not loaded yet, wait for tree before fetching.
  if (selectedId !== null && !selectedNode) {
    return
  }

  try {
    loading.value = true
    if (selectedNode) {
      const ids = collectDescendantIds(selectedNode)
      const nextLessons = await lessonsApi.list({ course_ids: ids.join(',') })
      if (requestSeq !== lessonsFetchSeq.value) return
      lessons.value = nextLessons
    } else {
      const nextLessons = await lessonsApi.list()
      if (requestSeq !== lessonsFetchSeq.value) return
      lessons.value = nextLessons
    }
  } catch { /* silent */ } finally {
    if (requestSeq === lessonsFetchSeq.value) {
      loading.value = false
    }
  }
}

watch(selectedCourseId, () => {
  persistPanelState()
  fetchLessons()
})

watch(() => user.value?.id, () => {
  restorePanelState()
})

const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return ''
  const date = new Date(dateString)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const formatDuration = (seconds: number | null | undefined): string => {
  if (!seconds) return ''
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

const stripMarkdown = (value: string | null | undefined): string => {
  if (!value) return ''
  return value
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/`([^`]*)`/g, '$1')
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^>\s?/gm, '')
    .replace(/^[-*+]\s+/gm, '')
    .replace(/^\d+\.\s+/gm, '')
    .replace(/(\*\*|__|\*|_|~~)/g, '')
    .replace(/&[a-zA-Z0-9#]+;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

const fetchLessonByHashid = async (
  hashid: string,
  historyRoute: {
    contentType: ContentType
    versionId: string | null
    compare:
      | {
          versionAId: string
          versionBId: string
        }
      | null
  } | null = null,
  syncUrl = true,
) => {
  try {
    if (syncUrl) updateUrl(hashid, historyRoute)
    selectedLessonDetail.value = await lessonsApi.get(hashid)
    selectedLesson.value = { hashid } as LessonListItem
    selectedHistoryRoute.value = historyRoute
  } catch {
    updateUrl(null)
  }
}

const openLesson = async (
  lesson: LessonListItem,
  historyRoute: {
    contentType: ContentType
    versionId: string | null
    compare:
      | {
          versionAId: string
          versionBId: string
        }
      | null
  } | null = null,
  syncUrl = true,
) => {
  try {
    if (syncUrl) updateUrl(lesson.hashid, historyRoute)
    selectedLessonDetail.value = await lessonsApi.get(lesson.hashid)
    selectedLesson.value = lesson
    selectedHistoryRoute.value = historyRoute
  } catch {
    updateUrl(null)
  }
}

const closeLesson = () => {
  selectedLesson.value = null
  selectedLessonDetail.value = null
  selectedHistoryRoute.value = null
  updateUrl(null)
}

const selectedLessonIndex = computed(() => {
  const hashid = selectedLessonDetail.value?.hashid
  if (!hashid) return -1
  return sortedLessons.value.findIndex((lesson) => lesson.hashid === hashid)
})

const hasPreviousLesson = computed(() => selectedLessonIndex.value > 0)
const hasNextLesson = computed(() => {
  const index = selectedLessonIndex.value
  return index >= 0 && index < sortedLessons.value.length - 1
})

const openPreviousLesson = async () => {
  if (!hasPreviousLesson.value) return
  const index = selectedLessonIndex.value
  if (index <= 0) return
  await openLesson(sortedLessons.value[index - 1], null, true)
}

const openNextLesson = async () => {
  if (!hasNextLesson.value) return
  const index = selectedLessonIndex.value
  if (index < 0 || index >= sortedLessons.value.length - 1) return
  await openLesson(sortedLessons.value[index + 1], null, true)
}

const openCreateModal = () => {
  showCreateModal.value = true
}

const closeCreateModal = () => {
  showCreateModal.value = false
}

const onLessonCreated = () => {
  fetchLessons()
  fetchTree()
}

const updatePanelWidth = (clientX: number) => {
  const layoutBounds = layoutRef.value?.getBoundingClientRect()
  if (!layoutBounds) return
  const nextWidth = clientX - layoutBounds.left
  panelWidth.value = Math.min(MAX_PANEL_WIDTH, Math.max(MIN_PANEL_WIDTH, nextWidth))
}

const onResizeMouseMove = (event: MouseEvent) => {
  if (!isResizing.value) return
  updatePanelWidth(event.clientX)
}

const stopResize = () => {
  if (!isResizing.value) return
  isResizing.value = false
  window.removeEventListener('mousemove', onResizeMouseMove)
  window.removeEventListener('mouseup', stopResize)
  persistPanelState()
}

const startResize = (event: MouseEvent) => {
  event.preventDefault()
  isResizing.value = true
  updatePanelWidth(event.clientX)
  window.addEventListener('mousemove', onResizeMouseMove)
  window.addEventListener('mouseup', stopResize)
}

const startHomeTour = async () => {
  await nextTick()
  homeTourInstance?.destroy()
  homeTourInstance = driver({
    showProgress: true,
    allowClose: true,
    steps: [
      {
        element: '[data-tour="courses-tree"]',
        popover: {
          title: t('lessons.tour.treeTitle'),
          description: t('lessons.tour.treeDescription'),
          side: 'right',
          align: 'start',
        },
      },
      {
        element: '[data-tour="search-input"]',
        popover: {
          title: t('lessons.tour.searchTitle'),
          description: t('lessons.tour.searchDescription'),
          side: 'bottom',
          align: 'start',
        },
      },
      {
        element: '[data-tour="sort-menu"]',
        popover: {
          title: t('lessons.tour.sortTitle'),
          description: t('lessons.tour.sortDescription'),
          side: 'bottom',
          align: 'end',
        },
      },
      {
        element: '[data-tour="facets-row"]',
        popover: {
          title: t('lessons.tour.facetsTitle'),
          description: t('lessons.tour.facetsDescription'),
          side: 'bottom',
          align: 'start',
        },
      },
      {
        element: '[data-tour="lessons-list"]',
        popover: {
          title: t('lessons.tour.listTitle'),
          description: t('lessons.tour.listDescription'),
          side: 'top',
          align: 'start',
        },
      },
      {
        element: '[data-tour="help-button"]',
        popover: {
          title: t('lessons.tour.helpTitle'),
          description: t('lessons.tour.helpDescription'),
          side: 'bottom',
          align: 'end',
        },
      },
      {
        element: '[data-tour="theme-toggle"]',
        popover: {
          title: t('lessons.tour.themeTitle'),
          description: t('lessons.tour.themeDescription'),
          side: 'bottom',
          align: 'end',
        },
      },
    ],
  })
  homeTourInstance.drive()
  localStorage.setItem(getHomeTourStateKey(), 'seen')
}

const startLessonDetailTour = async () => {
  await nextTick()
  homeTourInstance?.destroy()
  homeTourInstance = driver({
    showProgress: true,
    allowClose: true,
    steps: [
      {
        element: '[data-tour="detail-header"]',
        popover: {
          title: t('lessons.tour.detailHeaderTitle'),
          description: t('lessons.tour.detailHeaderDescription'),
          side: 'bottom',
          align: 'start',
        },
      },
      {
        element: '[data-tour="detail-workflow"]',
        popover: {
          title: t('lessons.tour.detailWorkflowTitle'),
          description: t('lessons.tour.detailWorkflowDescription'),
          side: 'left',
          align: 'start',
        },
      },
      {
        element: '[data-tour="detail-tabs"]',
        popover: {
          title: t('lessons.tour.detailTabsTitle'),
          description: t('lessons.tour.detailTabsDescription'),
          side: 'bottom',
          align: 'start',
        },
      },
      {
        element: '[data-tour="detail-content"]',
        popover: {
          title: t('lessons.tour.detailContentTitle'),
          description: t('lessons.tour.detailContentDescription'),
          side: 'top',
          align: 'start',
        },
      },
    ],
  })
  homeTourInstance.drive()
}


onMounted(async () => {
  window.addEventListener('popstate', handlePopState)
  restorePanelState()
  await fetchTree()
  await fetchLessons()
  const parsedRoute = parseLessonRoute()
  const hashid = parsedRoute.hashid
  const historyRoute =
    parsedRoute.historyContentType
      ? {
          contentType: parsedRoute.historyContentType,
          versionId: parsedRoute.versionId,
          compare: parsedRoute.compare,
        }
      : null
  if (hashid) {
    const lesson = lessons.value.find((l) => l.hashid === hashid)
    if (lesson) {
      await openLesson(lesson, historyRoute, false)
    } else {
      await fetchLessonByHashid(hashid, historyRoute, false)
    }
  } else if (localStorage.getItem(getHomeTourStateKey()) !== 'seen') {
    await startHomeTour()
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('popstate', handlePopState)
  stopResize()
  homeTourInstance?.destroy()
  homeTourInstance = null
})

defineExpose({
  isViewingDetail: computed(() => selectedLessonDetail.value !== null),
  goToLessonsHome: closeLesson,
  openCreateModal,
  startHomeTour,
  startLessonDetailTour,
})
</script>

<template>
  <!-- Create Lesson Modal -->
  <CreateLessonModal
    :is-open="showCreateModal"
    :default-course-id="selectedCourseNode?.id ?? null"
    @close="closeCreateModal"
    @created="onLessonCreated"
  />

  <!-- Show lesson detail if a lesson is selected -->
  <LessonDetail
    v-if="selectedLessonDetail"
    :lesson="selectedLessonDetail"
    :has-previous-lesson="hasPreviousLesson"
    :has-next-lesson="hasNextLesson"
    :initial-history-content-type="selectedHistoryRoute?.contentType ?? null"
    :initial-history-version-id="selectedHistoryRoute?.versionId ?? null"
    :initial-history-compare="selectedHistoryRoute?.compare ?? null"
    @close="closeLesson"
    @previous="openPreviousLesson"
    @next="openNextLesson"
  />

  <!-- Two-panel layout: tree on left, lessons on right -->
  <div v-else ref="layoutRef" class="flex min-h-0">
    <!-- Left panel: Course tree -->
    <aside
      data-tour="courses-tree"
      class="flex-shrink-0 bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors"
      :style="{ width: `${panelWidth}px` }"
    >
      <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
          {{ t('courses.title') }}
        </h3>
      </div>

      <div v-if="loadingTree" class="p-4 text-center text-sm text-gray-400 dark:text-gray-500">
        {{ t('courses.loading') }}
      </div>

      <div v-else class="overflow-y-auto" style="max-height: calc(100vh - 12rem)">
        <!-- "All lessons" entry -->
        <button
          @click="selectedCourseId = null"
          :class="[
            'w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors',
            !selectedCourseId
              ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 font-semibold'
              : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700/50',
          ]"
        >
          <DocumentTextIcon class="h-5 w-5 flex-shrink-0" />
          <span class="flex-1 text-left truncate">{{ t('lessons.allLessons') }}</span>
        </button>

        <!-- Tree nodes -->
        <CourseTreeItem
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :depth="0"
          :expanded="expanded"
          :selected-id="selectedCourseId"
          :show-actions="false"
          @toggle="toggleExpand"
          @select="selectCourseNode"
        />
      </div>
    </aside>

    <div class="mx-2 w-3 flex-shrink-0 relative">
      <div
        class="absolute top-3 left-1/2 -translate-x-1/2 h-6 w-1.5 rounded-full bg-gray-300 dark:bg-gray-600 border border-gray-400/60 dark:border-gray-500/70"
      />
      <div
        class="h-full w-full cursor-col-resize rounded bg-transparent hover:bg-indigo-200/60 dark:hover:bg-indigo-700/40 transition-colors"
        :class="{ 'bg-indigo-300/70 dark:bg-indigo-600/60': isResizing }"
        @mousedown="startResize"
      />
    </div>

    <!-- Right panel: Lessons list -->
    <div class="flex-1 min-w-0 pl-2">
      <!-- Facets filters -->
      <div class="mb-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-3">
        <div class="flex flex-wrap items-center gap-2">
          <div class="relative flex-1 min-w-[220px]">
            <MagnifyingGlassIcon class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500" />
            <input
              v-model="titleQuery"
              data-tour="search-input"
              type="text"
              :placeholder="t('lessons.searchTitlePlaceholder')"
              class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 pl-8 pr-8 py-1.5 text-sm text-gray-700 dark:text-gray-200 placeholder:text-gray-400 dark:placeholder:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
            />
            <button
              v-if="titleQuery.trim()"
              @click="clearTitleQuery"
              :title="t('lessons.clear')"
              class="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300"
            >
              <XMarkIcon class="h-3.5 w-3.5" />
            </button>
          </div>

          <div class="ml-auto inline-flex items-center gap-2">
            <span class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
              {{ t('lessons.sortedBy') }}
            </span>
            <Menu as="div" class="relative">
              <MenuButton
                data-tour="sort-menu"
                class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                :title="t('lessons.sort')"
              >
                <ArrowsUpDownIcon class="h-4 w-4" />
                <span class="hidden sm:inline">{{ t(sortOptions.find(o => o.key === sortMode)!.labelKey) }}</span>
              </MenuButton>
              <transition
                enter-active-class="transition ease-out duration-100"
                enter-from-class="transform opacity-0 scale-95"
                enter-to-class="transform opacity-100 scale-100"
                leave-active-class="transition ease-in duration-75"
                leave-from-class="transform opacity-100 scale-100"
                leave-to-class="transform opacity-0 scale-95"
              >
                <MenuItems class="absolute right-0 z-10 mt-1 w-48 origin-top-right rounded-md bg-white dark:bg-gray-800 shadow-lg ring-1 ring-black ring-opacity-5 dark:ring-gray-700 focus:outline-none">
                  <div class="py-1">
                    <MenuItem v-for="opt in sortOptions" :key="opt.key" v-slot="{ active }">
                      <button
                        @click="sortMode = opt.key"
                        :class="[
                          'w-full text-left px-4 py-2 text-sm flex items-center gap-2',
                          active ? 'bg-gray-100 dark:bg-gray-700' : '',
                          sortMode === opt.key
                            ? 'text-indigo-600 dark:text-indigo-400 font-medium'
                            : 'text-gray-700 dark:text-gray-300',
                        ]"
                      >
                        <BarsArrowDownIcon v-if="opt.key === 'date_desc'" class="h-4 w-4" />
                        <BarsArrowUpIcon v-else-if="opt.key === 'date_asc'" class="h-4 w-4" />
                        <ArrowsUpDownIcon v-else class="h-4 w-4" />
                        {{ t(opt.labelKey) }}
                      </button>
                    </MenuItem>
                  </div>
                </MenuItems>
              </transition>
            </Menu>
          </div>
        </div>

        <div data-tour="facets-row" class="mt-2 flex flex-wrap items-center gap-2">
          <div class="inline-flex items-center gap-1">
            <Menu as="div" class="relative">
              <MenuButton class="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 px-2.5 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700">
                <FunnelIcon class="h-3.5 w-3.5" />
                {{ t('lessons.hebrewYear') }}
                <span v-if="selectedHebrewYears.size" class="rounded-full bg-indigo-100 dark:bg-indigo-900/30 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:text-indigo-300">
                  {{ selectedHebrewYears.size }}
                </span>
              </MenuButton>
              <MenuItems class="absolute left-0 z-10 mt-1 min-w-[180px] rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 shadow-lg ring-1 ring-black/5 dark:ring-gray-700 p-1">
                <MenuItem v-for="year in availableHebrewYears" :key="year" v-slot="{ active }">
                  <button
                    @click="toggleHebrewYear(year)"
                    :class="[
                      'w-full rounded px-2 py-1.5 text-left text-xs text-gray-800 dark:text-gray-200 flex items-center justify-between',
                      active ? 'bg-gray-100 dark:bg-gray-700' : '',
                    ]"
                  >
                    <span>{{ year }}</span>
                    <CheckIcon v-if="selectedHebrewYears.has(year)" class="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-300" />
                  </button>
                </MenuItem>
              </MenuItems>
            </Menu>
            <button
              v-if="selectedHebrewYears.size"
              @click="clearHebrewYears"
              :title="t('lessons.clear')"
              class="inline-flex items-center justify-center rounded-md border border-gray-300 dark:border-gray-600 p-1.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <XMarkIcon class="h-3.5 w-3.5" />
            </button>
          </div>

          <div class="inline-flex items-center gap-1">
            <Menu as="div" class="relative">
              <MenuButton class="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 px-2.5 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700">
                <FunnelIcon class="h-3.5 w-3.5" />
                {{ t('lessons.status') }}
                <span v-if="selectedStatuses.size" class="rounded-full bg-indigo-100 dark:bg-indigo-900/30 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:text-indigo-300">
                  {{ selectedStatuses.size }}
                </span>
              </MenuButton>
              <MenuItems class="absolute left-0 z-10 mt-1 min-w-[220px] rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 shadow-lg ring-1 ring-black/5 dark:ring-gray-700 p-1">
                <MenuItem v-for="status in STATUS_FILTERS" :key="status" v-slot="{ active }">
                  <button
                    @click="toggleStatusFilter(status)"
                    :class="[
                      'w-full rounded px-2 py-1.5 text-left text-xs text-gray-800 dark:text-gray-200 flex items-center justify-between',
                      active ? 'bg-gray-100 dark:bg-gray-700' : '',
                    ]"
                  >
                    <span>{{ t('lessons.status_' + status) }}</span>
                    <CheckIcon v-if="selectedStatuses.has(status)" class="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-300" />
                  </button>
                </MenuItem>
              </MenuItems>
            </Menu>
            <button
              v-if="selectedStatuses.size"
              @click="clearStatuses"
              :title="t('lessons.clear')"
              class="inline-flex items-center justify-center rounded-md border border-gray-300 dark:border-gray-600 p-1.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <XMarkIcon class="h-3.5 w-3.5" />
            </button>
          </div>

          <div class="inline-flex items-center gap-1">
            <Menu as="div" class="relative">
              <MenuButton class="inline-flex items-center gap-1.5 rounded-md border border-gray-300 dark:border-gray-600 px-2.5 py-1.5 text-xs text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700">
                <FunnelIcon class="h-3.5 w-3.5" />
                {{ t('lessons.themes') }}
                <span v-if="selectedThemeIds.size" class="rounded-full bg-indigo-100 dark:bg-indigo-900/30 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:text-indigo-300">
                  {{ selectedThemeIds.size }}
                </span>
              </MenuButton>
              <MenuItems class="absolute left-0 z-10 mt-1 min-w-[220px] max-h-64 overflow-y-auto rounded-md bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-200 shadow-lg ring-1 ring-black/5 dark:ring-gray-700 p-1">
                <MenuItem v-for="theme in availableThemes" :key="theme.id" v-slot="{ active }">
                  <button
                    @click="toggleThemeFilter(theme.id)"
                    :class="[
                      'w-full rounded px-2 py-1.5 text-left text-xs text-gray-800 dark:text-gray-200 flex items-center justify-between gap-2',
                      active ? 'bg-gray-100 dark:bg-gray-700' : '',
                    ]"
                  >
                    <span class="truncate">{{ theme.name }}</span>
                    <CheckIcon v-if="selectedThemeIds.has(theme.id)" class="h-3.5 w-3.5 flex-shrink-0 text-indigo-600 dark:text-indigo-300" />
                  </button>
                </MenuItem>
              </MenuItems>
            </Menu>
            <button
              v-if="selectedThemeIds.size"
              @click="clearThemes"
              :title="t('lessons.clear')"
              class="inline-flex items-center justify-center rounded-md border border-gray-300 dark:border-gray-600 p-1.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <XMarkIcon class="h-3.5 w-3.5" />
            </button>
          </div>

          <template v-if="selectedCourseNode">
            <span class="text-xs text-gray-300 dark:text-gray-600">|</span>
            <span class="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300 min-w-0">
              <FolderIcon class="h-4 w-4 flex-shrink-0 text-violet-500 dark:text-violet-400" />
              <span class="truncate max-w-[24rem]">
                {{ selectedCoursePath.join(' / ') }}
              </span>
            </span>
            <button
              @click="selectedCourseId = null"
              :title="t('lessons.clear')"
              class="inline-flex items-center justify-center rounded-md border border-gray-300 dark:border-gray-600 p-1.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
            >
              <XMarkIcon class="h-3.5 w-3.5" />
            </button>
          </template>
          <button
            v-if="hasActiveFilters"
            @click="clearAllFilters"
            class="inline-flex items-center gap-1 rounded-md border border-gray-300 dark:border-gray-600 px-2.5 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700"
          >
            <XMarkIcon class="h-3.5 w-3.5" />
            {{ t('lessons.clearAllFilters') }}
          </button>
          <span class="text-xs text-gray-500 dark:text-gray-400 whitespace-nowrap">
            {{ t('lessons.displayedLessonsCount', { count: sortedLessons.length }) }}
          </span>
        </div>
      </div>

      <div v-if="loading" class="p-8 text-center text-gray-500 dark:text-gray-400">
        {{ t('lessons.loading') }}
      </div>

      <div v-else-if="sortedLessons.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
        {{ t('lessons.noLessons') }}
      </div>

      <div v-else data-tour="lessons-list" class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div
          v-for="lesson in sortedLessons"
          :key="lesson.id"
          @click="openLesson(lesson)"
          class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 hover:shadow-md dark:hover:shadow-gray-900/50 transition-all cursor-pointer border border-gray-200 dark:border-gray-700"
        >
          <div class="flex flex-col h-full">
            <div class="flex items-start gap-2 mb-1.5">
              <DocumentTextIcon class="h-5 w-5 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-0.5" />
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white line-clamp-2">
                {{ lesson.title }}
              </h3>
            </div>

            <div class="flex-1">
              <div class="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                <span class="inline-flex items-center gap-1">
                  <CalendarDaysIcon class="h-3.5 w-3.5" />
                  <span>{{ formatDate(lesson.date) }}</span>
                </span>
                <span v-if="lesson.duration" class="inline-flex items-center gap-1">
                  <ClockIcon class="h-3.5 w-3.5" />
                  <span>{{ formatDuration(lesson.duration) }}</span>
                </span>
                <span
                  v-if="lesson.hebrew_year || lesson.hebrew_date"
                  class="inline-flex items-center rounded-full bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700 dark:bg-violet-900/30 dark:text-violet-300"
                >
                  {{ lesson.hebrew_year || lesson.hebrew_date }}
                </span>
              </div>

              <div class="mb-2 flex items-center gap-2 min-w-0">
                <div
                  v-if="lesson.course"
                  class="min-w-0 inline-flex items-center gap-1 text-xs text-gray-600 dark:text-gray-300"
                >
                  <FolderIcon class="h-3.5 w-3.5 flex-shrink-0 text-violet-500 dark:text-violet-400" />
                  <span class="truncate">{{ getCoursePathLabel(lesson) }}</span>
                </div>
              </div>

              <p v-if="lesson.brief" class="text-xs text-gray-600 dark:text-gray-400 mb-1 line-clamp-2">
                {{ stripMarkdown(lesson.brief) }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

</template>
