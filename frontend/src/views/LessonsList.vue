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
import type { CourseTreeNode, LessonListItem, LessonDetail as LessonDetailType, LessonStatus } from '@/api/types'

const { t } = useI18n()

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

const lessons = ref<LessonListItem[]>([])
const tree = ref<CourseTreeNode[]>([])
const users = ref<ClerkUser[]>([])
const loading = ref(true)
const loadingTree = ref(true)
const selectedLesson = ref<LessonListItem | null>(null)
const selectedLessonDetail = ref<LessonDetailType | null>(null)
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

const expanded = ref<Set<number>>(new Set())
const selectedCourseNode = ref<CourseTreeNode | null>(null)

const toggleExpand = (id: number) => {
  if (expanded.value.has(id)) {
    expanded.value.delete(id)
  } else {
    expanded.value.add(id)
  }
}

const expandAll = (nodes: CourseTreeNode[]) => {
  for (const n of nodes) {
    if (n.children.length > 0) {
      expanded.value.add(n.id)
      expandAll(n.children)
    }
  }
}

const collectDescendantIds = (node: CourseTreeNode): number[] => {
  const ids = [node.id]
  for (const child of node.children) {
    ids.push(...collectDescendantIds(child))
  }
  return ids
}

const selectCourseNode = (node: CourseTreeNode) => {
  if (selectedCourseNode.value?.id === node.id) {
    selectedCourseNode.value = null
  } else {
    selectedCourseNode.value = node
  }
}

const getHashidFromUrl = (): string | null => {
  const match = window.location.pathname.match(/\/lessons\/([a-zA-Z0-9]+)/)
  return match ? match[1] : null
}

const updateUrl = (hashid: string | null) => {
  if (hashid) {
    window.history.pushState({ hashid }, '', `/lessons/${hashid}`)
  } else {
    window.history.pushState({}, '', '/lessons')
  }
}

const handlePopState = (event: PopStateEvent) => {
  const hashid = event.state?.hashid ?? getHashidFromUrl()
  if (hashid) {
    const lesson = lessons.value.find((l) => l.hashid === hashid)
    if (lesson) {
      openLesson(lesson)
    } else {
      fetchLessonByHashid(hashid)
    }
  } else {
    closeLesson()
  }
}

const fetchTree = async () => {
  try {
    loadingTree.value = true
    tree.value = await coursesApi.tree()
    expandAll(tree.value)
  } catch { /* silent */ } finally {
    loadingTree.value = false
  }
}

const fetchLessons = async () => {
  try {
    loading.value = true
    if (selectedCourseNode.value) {
      const ids = collectDescendantIds(selectedCourseNode.value)
      lessons.value = await lessonsApi.list({ course_ids: ids.join(',') })
    } else {
      lessons.value = await lessonsApi.list()
    }
  } catch { /* silent */ } finally {
    loading.value = false
  }
}

watch(selectedCourseNode, () => {
  fetchLessons()
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

const fetchLessonByHashid = async (hashid: string) => {
  try {
    selectedLessonDetail.value = await lessonsApi.get(hashid)
    selectedLesson.value = { hashid } as LessonListItem
  } catch {
    updateUrl(null)
  }
}

const openLesson = async (lesson: LessonListItem) => {
  try {
    updateUrl(lesson.hashid)
    selectedLessonDetail.value = await lessonsApi.get(lesson.hashid)
    selectedLesson.value = lesson
  } catch {
    updateUrl(null)
  }
}

const closeLesson = () => {
  selectedLesson.value = null
  selectedLessonDetail.value = null
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

onMounted(async () => {
  window.addEventListener('popstate', handlePopState)
  await Promise.all([fetchTree(), fetchLessons(), fetchUsers()])
  const hashid = getHashidFromUrl()
  if (hashid) {
    const lesson = lessons.value.find((l) => l.hashid === hashid)
    if (lesson) {
      await openLesson(lesson)
    } else {
      await fetchLessonByHashid(hashid)
    }
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('popstate', handlePopState)
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
    @close="closeCreateModal"
    @created="onLessonCreated"
  />

  <!-- Show lesson detail if a lesson is selected -->
  <LessonDetail
    v-if="selectedLessonDetail"
    :lesson="selectedLessonDetail"
    @close="closeLesson"
  />

  <!-- Two-panel layout: tree on left, lessons on right -->
  <div v-else class="flex gap-6 min-h-0">
    <!-- Left panel: Course tree -->
    <aside class="w-72 flex-shrink-0 bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
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
          @click="selectedCourseNode = null"
          :class="[
            'w-full flex items-center gap-2 px-4 py-2 text-sm transition-colors',
            !selectedCourseNode
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
          :selected-id="selectedCourseNode?.id ?? null"
          :show-actions="false"
          @toggle="toggleExpand"
          @select="selectCourseNode"
        />
      </div>
    </aside>

    <!-- Right panel: Lessons list -->
    <div class="flex-1 min-w-0">
      <!-- Toolbar: breadcrumb + sort -->
      <div class="mb-4 flex items-center gap-2">
        <template v-if="selectedCourseNode">
          <span class="text-sm text-gray-500 dark:text-gray-400">
            {{ selectedCourseNode.name }}
          </span>
          <span class="text-xs text-gray-400 dark:text-gray-500">
            ({{ selectedCourseNode.lesson_count }} {{ t('lessons.lessonsLabel') }})
          </span>
          <button
            @click="selectedCourseNode = null"
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
