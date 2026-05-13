<script setup lang="ts">
import { ref, onMounted, computed, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  DocumentTextIcon,
  ClockIcon,
  BarsArrowDownIcon,
  BarsArrowUpIcon,
  ArrowsUpDownIcon,
} from '@heroicons/vue/24/outline'
import { Menu, MenuButton, MenuItems, MenuItem } from '@headlessui/vue'
import LessonDetail from './LessonDetail.vue'
import CreateLessonModal from '../components/CreateLessonModal.vue'
import CourseTreeItem from '@/components/CourseTreeItem.vue'
import { lessonsApi } from '@/api/lessons'
import { coursesApi } from '@/api/courses'
import { usersApi, type ClerkUser } from '@/api/users'
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

const STATUS_COLORS: Record<string, string> = {
  draft:              'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  in_progress:        'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  review_requested:   'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  revision_requested: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  validated:          'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
}

type PipelineStep = 'edition' | 'sources' | 'summary'

const LESSON_CARD_STEPS: Array<{ key: PipelineStep; labelKey: string }> = [
  { key: 'edition', labelKey: 'lessons.step_edition' },
  { key: 'sources', labelKey: 'lessons.step_sources' },
  { key: 'summary', labelKey: 'lessons.step_summary' },
]

const lessons = ref<LessonListItem[]>([])
const tree = ref<CourseTreeNode[]>([])
const users = ref<ClerkUser[]>([])
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

const fetchUsers = async () => {
  try { users.value = await usersApi.list() } catch { /* silent */ }
}

const getUserName = (userId: string): string => {
  const u = users.value.find((u) => u.id === userId)
  if (u) {
    const name = [u.first_name, u.last_name].filter(Boolean).join(' ')
    return name || u.email || userId
  }
  return userId
}

const sortedLessons = computed(() => {
  const list = [...lessons.value]
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

const MIN_PANEL_WIDTH = 240
const MAX_PANEL_WIDTH = 560
const PANEL_STATE_KEY_PREFIX = 'lessons.courses-panel.v1'

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

const selectedCourseNode = computed<CourseTreeNode | null>(() => {
  if (!selectedCourseId.value) return null
  return findNodeById(tree.value, selectedCourseId.value)
})

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
  if (selectedCourseId.value === node.id) {
    selectedCourseId.value = null
  } else {
    selectedCourseId.value = node.id
  }
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
  try {
    loading.value = true
    const selectedNode = selectedCourseNode.value
    if (selectedNode) {
      const ids = collectDescendantIds(selectedNode)
      lessons.value = await lessonsApi.list({ course_ids: ids.join(',') })
    } else {
      lessons.value = await lessonsApi.list()
    }
  } catch { /* silent */ } finally {
    loading.value = false
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

const isStepDone = (lesson: LessonListItem, step: PipelineStep): boolean => {
  const status = lesson.process_status ?? ''
  if (step === 'edition') {
    if (typeof lesson.edition_done === 'boolean') return lesson.edition_done
    return ['edition', 'sources_extraction', 'sources_checking', 'summary'].includes(status)
  }
  if (step === 'sources') {
    if (typeof lesson.sources_done === 'boolean') return lesson.sources_done
    return ['sources_extraction', 'sources_checking', 'summary'].includes(status)
  }
  if (typeof lesson.summary_done === 'boolean') return lesson.summary_done
  return status === 'summary' || lesson.status === 'validated' || !!lesson.brief
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

onMounted(async () => {
  window.addEventListener('popstate', handlePopState)
  restorePanelState()
  await fetchTree()
  await Promise.all([fetchLessons(), fetchUsers()])
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
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('popstate', handlePopState)
  stopResize()
})

defineExpose({
  isViewingDetail: computed(() => selectedLessonDetail.value !== null),
  openCreateModal,
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
    :initial-history-content-type="selectedHistoryRoute?.contentType ?? null"
    :initial-history-version-id="selectedHistoryRoute?.versionId ?? null"
    :initial-history-compare="selectedHistoryRoute?.compare ?? null"
    @close="closeLesson"
  />

  <!-- Two-panel layout: tree on left, lessons on right -->
  <div v-else ref="layoutRef" class="flex min-h-0">
    <!-- Left panel: Course tree -->
    <aside
      class="flex-shrink-0 bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors"
      :style="{ width: `${panelWidth}px` }"
    >
      <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 class="text-sm font-semibold text-gray-900 dark:text-white">
          {{ t('courses.title') }}
        </h3>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ t('courses.resizeHint') }}
        </p>
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

    <div
      class="mx-2 w-1.5 flex-shrink-0 cursor-col-resize rounded bg-transparent hover:bg-indigo-200 dark:hover:bg-indigo-700 transition-colors"
      :class="{ 'bg-indigo-300 dark:bg-indigo-600': isResizing }"
      @mousedown="startResize"
    />

    <!-- Right panel: Lessons list -->
    <div class="flex-1 min-w-0 pl-2">
      <!-- Toolbar: breadcrumb + sort -->
      <div class="mb-4 flex items-center gap-2">
        <template v-if="selectedCourseNode">
          <span class="text-sm text-gray-500 dark:text-gray-400">
            {{ selectedCourseNode?.name }}
          </span>
          <span class="text-xs text-gray-400 dark:text-gray-500">
            ({{ selectedCourseNode?.lesson_count ?? 0 }} {{ t('lessons.lessonsLabel') }})
          </span>
          <button
            @click="selectedCourseId = null"
            class="text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
          >
            {{ t('lessons.showAll') }}
          </button>
        </template>

        <!-- Sort dropdown (always visible, pushed to right) -->
        <div class="ml-auto">
          <Menu as="div" class="relative">
            <MenuButton
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

      <div v-if="loading" class="p-8 text-center text-gray-500 dark:text-gray-400">
        {{ t('lessons.loading') }}
      </div>

      <div v-else-if="sortedLessons.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
        {{ t('lessons.noLessons') }}
      </div>

      <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div
          v-for="lesson in sortedLessons"
          :key="lesson.id"
          @click="openLesson(lesson)"
          class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-5 hover:shadow-md dark:hover:shadow-gray-900/50 transition-all cursor-pointer border border-gray-200 dark:border-gray-700"
        >
          <div class="flex flex-col h-full">
            <div class="flex items-start gap-2 mb-2">
              <DocumentTextIcon class="h-5 w-5 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-0.5" />
              <h3 class="text-sm font-semibold text-gray-900 dark:text-white line-clamp-2">
                {{ lesson.title }}
              </h3>
            </div>

            <div class="flex-1">
              <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-2">
                <ClockIcon class="h-3.5 w-3.5" />
                <span>{{ formatDate(lesson.date) }}</span>
                <span v-if="lesson.duration" class="text-gray-400 dark:text-gray-500">·</span>
                <span v-if="lesson.duration">{{ formatDuration(lesson.duration) }}</span>
              </div>

              <p v-if="lesson.brief" class="text-xs text-gray-600 dark:text-gray-400 mb-2 line-clamp-2">
                {{ lesson.brief }}
              </p>

              <!-- Status + editors row -->
              <div class="flex items-center gap-2 mb-2">
                <span
                  :class="[
                    'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium',
                    STATUS_COLORS[lesson.status || 'draft'],
                  ]"
                >
                  {{ t('lessons.status_' + (lesson.status || 'draft')) }}
                </span>
                <template v-if="lesson.status !== 'validated' && lesson.editors?.length">
                  <span class="text-gray-300 dark:text-gray-600">·</span>
                  <span
                    v-for="editor in lesson.editors"
                    :key="editor.user_id"
                    class="text-xs text-gray-500 dark:text-gray-400 truncate"
                  >
                    {{ getUserName(editor.user_id) }}
                  </span>
                </template>
              </div>

              <div class="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                <span
                  v-for="step in LESSON_CARD_STEPS"
                  :key="step.key"
                  :class="isStepDone(lesson, step.key) ? 'text-emerald-600 dark:text-emerald-400' : 'text-gray-400 dark:text-gray-500'"
                >
                  {{ isStepDone(lesson, step.key) ? '✓' : '○' }} {{ t(step.labelKey) }}
                </span>
              </div>

              <div v-if="lesson.course || (lesson.themes && lesson.themes.length > 0)" class="flex items-center gap-2">
                <div v-if="lesson.course" class="flex-shrink-0">
                  <span class="inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                    {{ lesson.course.name }}
                  </span>
                </div>
                <div v-if="lesson.themes && lesson.themes.length > 0" class="flex flex-wrap items-center gap-1 ml-auto">
                  <span
                    v-for="theme in lesson.themes"
                    :key="theme.id"
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-300"
                  >
                    {{ theme.name }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
