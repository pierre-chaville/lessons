<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  ArchiveBoxIcon,
  ArrowUturnLeftIcon,
  CheckCircleIcon,
  ClockIcon,
  DocumentTextIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import { bookletsApi } from '@/api/booklets'
import { lessonsApi } from '@/api/lessons'
import { coursesApi } from '@/api/courses'
import type {
  BookletDetail,
  LessonListItem,
  CourseTreeNode,
  BookletItem,
  BookletTemplateField,
} from '@/api/types'
import CourseTreeItem from '@/components/CourseTreeItem.vue'
import { usePermissions } from '@/composables/usePermissions'

const props = defineProps<{
  bookletId: number | null
}>()

const emit = defineEmits<{
  (e: 'back'): void
}>()

const { t } = useI18n()
const templateFieldOptions: BookletTemplateField[] = [
  'title',
  'date',
  'duration',
  'corrected_transcript',
  'edited_transcript',
  'brief',
  'summary',
  'status',
  'themes',
  'course',
]
const { role } = usePermissions()
const loading = ref(false)
const mutating = ref(false)
const downloadingPdf = ref(false)
const downloadingMarkdown = ref(false)
const selectedDownloadFormat = ref<'pdf' | 'markdown'>('pdf')
const detail = ref<BookletDetail | null>(null)
const allLessons = ref<LessonListItem[]>([])
const courseTree = ref<CourseTreeNode[]>([])
const loadingPicker = ref(false)
const expandedCourses = ref<Set<number>>(new Set())
const showAddModal = ref(false)
const showAddChapterModal = ref(false)
const showEditBookletModal = ref(false)
const editingChapterItemId = ref<number | null>(null)
const selectedCourseNode = ref<CourseTreeNode | null>(null)
const draggingItemId = ref<number | null>(null)
const dragOverItemId = ref<number | null>(null)
const chapterForm = ref({
  chapter_title: '',
  chapter_subtitle: '',
  chapter_body: '',
  chapter_starts_new_page: true,
})
const chapterModalIsEditing = computed(() => editingChapterItemId.value != null)
const chapterModalReadOnly = computed(() => !isDraft.value)
const bookletForm = ref({
  title: '',
  subtitle: '',
  description: '',
  template_data: ['title', 'summary', 'brief'] as BookletTemplateField[],
})

const statusClass = (status: string) => {
  if (status === 'ready') return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
  if (status === 'archived') return 'bg-gray-200 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
  return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
}

const loadDetail = async () => {
  if (!props.bookletId) return
  try {
    loading.value = true
    const response = await bookletsApi.get(props.bookletId)
    if (!response.items || response.items.length === 0) {
      response.items = response.lessons.map((lesson) => ({
        ...lesson,
        item_type: 'lesson',
        lesson_id: lesson.lesson_id,
        chapter_title: null,
        chapter_subtitle: null,
        chapter_body: null,
        chapter_starts_new_page: true,
      }))
    }
    detail.value = response
  } finally {
    loading.value = false
  }
}

const loadLessons = async () => {
  allLessons.value = await lessonsApi.list()
}

const loadCourseTree = async () => {
  courseTree.value = await coursesApi.tree()
  const nextExpanded = new Set<number>()
  const expandAll = (nodes: CourseTreeNode[]) => {
    for (const node of nodes) {
      if (node.children.length > 0) {
        nextExpanded.add(node.id)
      }
      expandAll(node.children)
    }
  }
  expandAll(courseTree.value)
  nextExpanded.add(-1) // uncategorized group
  expandedCourses.value = nextExpanded
}

const orderedItems = computed(() => {
  if (!detail.value) return []
  return [...detail.value.items].sort((a, b) => a.position - b.position)
})

const selectedLessonIds = computed(
  () =>
    new Set(
      orderedItems.value
        .filter((i) => i.item_type === 'lesson' && i.lesson_id != null)
        .map((l) => l.lesson_id as number),
    ),
)

const availableLessons = computed(() => {
  return allLessons.value.filter((l) => !selectedLessonIds.value.has(l.id))
})

const isDraft = computed(() => detail.value?.status === 'draft')
const isReady = computed(() => detail.value?.status === 'ready')
const isArchived = computed(() => detail.value?.status === 'archived')
const isAdmin = computed(() => role.value === 'admin')

const addLesson = async (lessonId: number) => {
  if (!props.bookletId) return
  try {
    mutating.value = true
    await bookletsApi.addLesson(props.bookletId, lessonId)
    await loadDetail()
  } finally {
    mutating.value = false
  }
}

const toggleCourse = (courseId: number) => {
  const next = new Set(expandedCourses.value)
  if (next.has(courseId)) next.delete(courseId)
  else next.add(courseId)
  expandedCourses.value = next
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

const modalLessons = computed(() => {
  const source = [...allLessons.value]
  if (selectedCourseNode.value) {
    const ids = new Set(collectDescendantIds(selectedCourseNode.value))
    return source
      .filter((lesson) => {
        const cid = lesson.course?.id ?? lesson.course_id
        return cid != null && ids.has(cid)
      })
      .sort((a, b) => (a.title ?? '').localeCompare(b.title ?? ''))
  }
  return source.sort((a, b) => (a.title ?? '').localeCompare(b.title ?? ''))
})

const openAddModal = () => {
  selectedCourseNode.value = null
  showAddModal.value = true
}

const openAddChapterModal = () => {
  editingChapterItemId.value = null
  chapterForm.value = {
    chapter_title: '',
    chapter_subtitle: '',
    chapter_body: '',
    chapter_starts_new_page: true,
  }
  showAddChapterModal.value = true
}

const openEditChapterModal = (item: BookletItem) => {
  if (item.item_type !== 'chapter') return
  editingChapterItemId.value = item.id
  chapterForm.value = {
    chapter_title: item.chapter_title ?? '',
    chapter_subtitle: item.chapter_subtitle ?? '',
    chapter_body: item.chapter_body ?? '',
    chapter_starts_new_page: item.chapter_starts_new_page,
  }
  showAddChapterModal.value = true
}

const closeAddModal = () => {
  if (mutating.value) return
  showAddModal.value = false
}

const closeAddChapterModal = () => {
  if (mutating.value) return
  showAddChapterModal.value = false
  editingChapterItemId.value = null
}

const openEditBookletModal = () => {
  if (!detail.value) return
  bookletForm.value = {
    title: detail.value.title || '',
    subtitle: detail.value.subtitle || '',
    description: detail.value.description || '',
    template_data: [...(detail.value.template_data || [])],
  }
  showEditBookletModal.value = true
}

const closeEditBookletModal = () => {
  if (mutating.value) return
  showEditBookletModal.value = false
}

const saveBookletMeta = async () => {
  if (!props.bookletId || !detail.value) return
  if (!bookletForm.value.title.trim()) return
  try {
    mutating.value = true
    await bookletsApi.update(props.bookletId, {
      title: bookletForm.value.title.trim(),
      subtitle: bookletForm.value.subtitle.trim() || null,
      description: bookletForm.value.description.trim() || null,
      template_data: [...bookletForm.value.template_data],
    })
    await loadDetail()
    showEditBookletModal.value = false
  } finally {
    mutating.value = false
  }
}

const changeBookletStatus = async (newStatus: 'ready' | 'draft' | 'archived') => {
  if (!props.bookletId) return
  try {
    mutating.value = true
    await bookletsApi.changeStatus(props.bookletId, newStatus)
    await loadDetail()
  } finally {
    mutating.value = false
  }
}

const deleteBooklet = async () => {
  if (!props.bookletId) return
  if (!window.confirm(t('booklets.deleteConfirm'))) return
  try {
    mutating.value = true
    await bookletsApi.delete(props.bookletId)
    emit('back')
  } finally {
    mutating.value = false
  }
}

const downloadBookletPdf = async () => {
  if (!props.bookletId || !detail.value) return
  try {
    downloadingPdf.value = true
    const blob = await bookletsApi.downloadPdf(props.bookletId)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const safeTitle = (detail.value.title || 'booklet').replace(/[^\w\- ]+/g, '').trim() || 'booklet'
    link.download = `${safeTitle}.pdf`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } finally {
    downloadingPdf.value = false
  }
}

const downloadBookletMarkdown = async () => {
  if (!props.bookletId || !detail.value) return
  try {
    downloadingMarkdown.value = true
    const blob = await bookletsApi.downloadMarkdown(props.bookletId)
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const safeTitle = (detail.value.title || 'booklet').replace(/[^\w\- ]+/g, '').trim() || 'booklet'
    link.download = `${safeTitle}.md`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  } finally {
    downloadingMarkdown.value = false
  }
}

const downloadSelectedBooklet = async () => {
  if (selectedDownloadFormat.value === 'markdown') {
    await downloadBookletMarkdown()
    return
  }
  await downloadBookletPdf()
}

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

const saveChapter = async () => {
  if (!props.bookletId) return
  if (!chapterForm.value.chapter_title.trim()) return
  try {
    mutating.value = true
    const payload = {
      chapter_title: chapterForm.value.chapter_title.trim(),
      chapter_subtitle: chapterForm.value.chapter_subtitle.trim() || null,
      chapter_body: chapterForm.value.chapter_body.trim() || null,
      chapter_starts_new_page: chapterForm.value.chapter_starts_new_page,
    }
    if (editingChapterItemId.value != null) {
      await bookletsApi.updateChapter(props.bookletId, editingChapterItemId.value, payload)
    } else {
      await bookletsApi.addChapter(props.bookletId, payload)
    }
    await loadDetail()
    showAddChapterModal.value = false
    editingChapterItemId.value = null
  } finally {
    mutating.value = false
  }
}

const moveItem = async (itemId: number, direction: 'up' | 'down') => {
  if (!props.bookletId || !detail.value) return
  const ids = orderedItems.value.map((i) => i.id)
  const idx = ids.findIndex((id) => id === itemId)
  if (idx < 0) return
  if (direction === 'up' && idx === 0) return
  if (direction === 'down' && idx === ids.length - 1) return
  const swapWith = direction === 'up' ? idx - 1 : idx + 1
  ;[ids[idx], ids[swapWith]] = [ids[swapWith], ids[idx]]
  try {
    mutating.value = true
    await bookletsApi.reorderItems(props.bookletId, ids)
    await loadDetail()
  } finally {
    mutating.value = false
  }
}

const removeItem = async (item: BookletItem) => {
  if (!props.bookletId) return
  const confirmMessage =
    item.item_type === 'chapter' ? t('booklets.removeChapterConfirm') : t('booklets.removeLessonConfirm')
  if (!window.confirm(confirmMessage)) return
  try {
    mutating.value = true
    await bookletsApi.removeItem(props.bookletId, item.id)
    await loadDetail()
  } finally {
    mutating.value = false
  }
}

const onDragStart = (itemId: number) => {
  draggingItemId.value = itemId
  dragOverItemId.value = itemId
}

const onDragOver = (itemId: number, event: DragEvent) => {
  event.preventDefault()
  dragOverItemId.value = itemId
}

const onDragEnd = () => {
  draggingItemId.value = null
  dragOverItemId.value = null
}

const onDrop = async (targetItemId: number) => {
  if (!props.bookletId || !detail.value) return
  const sourceItemId = draggingItemId.value
  onDragEnd()
  if (!sourceItemId || sourceItemId === targetItemId) return

  const ids = orderedItems.value.map((i) => i.id)
  const sourceIdx = ids.findIndex((id) => id === sourceItemId)
  const targetIdx = ids.findIndex((id) => id === targetItemId)
  if (sourceIdx < 0 || targetIdx < 0) return

  const [moved] = ids.splice(sourceIdx, 1)
  ids.splice(targetIdx, 0, moved)
  try {
    mutating.value = true
    await bookletsApi.reorderItems(props.bookletId, ids)
    await loadDetail()
  } finally {
    mutating.value = false
  }
}

onMounted(async () => {
  try {
    loadingPicker.value = true
    await Promise.all([loadDetail(), loadLessons(), loadCourseTree()])
  } finally {
    loadingPicker.value = false
  }
})
watch(() => props.bookletId, loadDetail)
</script>

<template>
  <div class="space-y-4">
    <button
      class="text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
      @click="emit('back')"
    >
      {{ t('booklets.backToList') }}
    </button>

    <div v-if="loading" class="p-8 text-center text-gray-500 dark:text-gray-400">
      {{ t('booklets.loadingDetail') }}
    </div>

    <div
      v-else-if="detail"
      class="bg-white dark:bg-gray-800 shadow-sm rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden"
    >
      <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-700">
        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0">
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ detail.title }}
            </h3>
            <p v-if="detail.subtitle" class="text-sm text-gray-500 dark:text-gray-400 mt-1">
              {{ detail.subtitle }}
            </p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <div class="flex flex-wrap justify-end gap-2">
              <button
                class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="mutating || !isDraft"
                @click="openEditBookletModal"
              >
                <PencilIcon class="h-4 w-4" />
                {{ t('booklets.actions.edit') }}
              </button>
              <button
                v-if="isDraft"
                class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors text-green-700 dark:text-green-300 bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="mutating"
                @click="changeBookletStatus('ready')"
              >
                <CheckCircleIcon class="h-4 w-4" />
                {{ t('booklets.actions.markReady') }}
              </button>
              <button
                v-if="isReady"
                class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 hover:bg-amber-100 dark:hover:bg-amber-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="mutating"
                @click="changeBookletStatus('draft')"
              >
                <ArrowUturnLeftIcon class="h-4 w-4" />
                {{ t('booklets.actions.markDraft') }}
              </button>
              <button
                v-if="isAdmin && !isArchived"
                class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="mutating"
                @click="changeBookletStatus('archived')"
              >
                <ArchiveBoxIcon class="h-4 w-4" />
                {{ t('booklets.actions.archive') }}
              </button>
              <button
                class="flex-shrink-0 inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="mutating || downloadingPdf || downloadingMarkdown"
                @click="deleteBooklet"
              >
                <TrashIcon class="h-4 w-4" />
                {{ t('booklets.actions.delete') }}
              </button>
            </div>
            <div class="flex-shrink-0 flex items-center gap-2 mt-1 sm:mt-0">
              <div
                class="inline-flex rounded-md border border-gray-300 dark:border-gray-600 overflow-hidden"
                role="group"
                :aria-label="t('booklets.actions.downloadFormatLabel')"
              >
                <button
                  type="button"
                  class="px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  :class="
                    selectedDownloadFormat === 'pdf'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'
                  "
                  :disabled="mutating || downloadingPdf || downloadingMarkdown"
                  :aria-pressed="selectedDownloadFormat === 'pdf'"
                  @click="selectedDownloadFormat = 'pdf'"
                >
                  {{ t('booklets.actions.formatPdf') }}
                </button>
                <button
                  type="button"
                  class="px-3 py-2 text-sm font-medium transition-colors border-l border-gray-300 dark:border-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                  :class="
                    selectedDownloadFormat === 'markdown'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600'
                  "
                  :disabled="mutating || downloadingPdf || downloadingMarkdown"
                  :aria-pressed="selectedDownloadFormat === 'markdown'"
                  @click="selectedDownloadFormat = 'markdown'"
                >
                  {{ t('booklets.actions.formatMarkdown') }}
                </button>
              </div>
              <button
                class="inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
                :disabled="mutating || downloadingPdf || downloadingMarkdown"
                @click="downloadSelectedBooklet"
              >
                <DocumentTextIcon class="h-4 w-4" />
                {{
                  downloadingPdf
                    ? t('booklets.actions.downloadingPdf')
                    : downloadingMarkdown
                      ? t('booklets.actions.downloadingMarkdown')
                      : t('booklets.actions.download')
                }}
              </button>
            </div>
          </div>
        </div>
        <p v-if="detail.description" class="text-sm text-gray-600 dark:text-gray-300 mt-3">
          {{ detail.description }}
        </p>
        <div class="mt-3">
          <span :class="['inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium', statusClass(detail.status)]">
            {{ t(`booklets.status.${detail.status}`) }}
          </span>
        </div>
        <div class="mt-4">
          <h4 class="text-sm font-semibold text-gray-900 dark:text-white mb-2">
            {{ t('booklets.templateDataTitle') }}
          </h4>
          <div
            v-if="detail.template_data && detail.template_data.length"
            class="flex flex-wrap gap-2 rounded-md bg-gray-50 p-3 dark:bg-gray-900"
          >
            <span
              v-for="fieldKey in detail.template_data"
              :key="fieldKey"
              class="inline-flex items-center rounded-full bg-indigo-100 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300"
            >
              {{ t(`booklets.templateFields.${fieldKey}`) }}
            </span>
          </div>
          <p v-else class="text-sm text-gray-500 dark:text-gray-400">
            {{ t('booklets.templateDataEmpty') }}
          </p>
        </div>
      </div>

      <div class="p-5">
        <div class="mb-3 flex items-center justify-between gap-3">
          <h4 class="text-sm font-semibold text-gray-900 dark:text-white">
            {{ t('booklets.itemsTitle') }}
          </h4>
          <div class="flex justify-end gap-2">
            <button
              class="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!isDraft || mutating || loadingPicker"
              @click="openAddModal"
            >
              <PlusIcon class="h-4 w-4" />
              {{ t('booklets.actions.addLesson') }}
            </button>
            <button
              class="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-md bg-purple-600 text-white hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="!isDraft || mutating"
              @click="openAddChapterModal"
            >
              <PlusIcon class="h-4 w-4" />
              {{ t('booklets.actions.addChapter') }}
            </button>
          </div>
        </div>
        <p v-if="!isDraft" class="mb-3 text-xs text-amber-600 dark:text-amber-400 text-right">
          {{ t('booklets.compositionLocked') }}
        </p>
        <p v-if="isDraft" class="text-xs text-gray-500 dark:text-gray-400 mb-2">
          {{ t('booklets.dragHint') }}
        </p>
        <div v-if="orderedItems.length === 0" class="text-sm text-gray-500 dark:text-gray-400">
          {{ t('booklets.noItems') }}
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="(row, idx) in orderedItems"
            :key="row.id"
            :draggable="isDraft && !mutating"
            class="flex items-center gap-3 rounded-md border border-gray-200 dark:border-gray-700 px-3 py-2"
            :class="{
              'cursor-grab': isDraft && !mutating,
              'opacity-70': draggingItemId === row.id,
              'ring-2 ring-indigo-300 dark:ring-indigo-700': dragOverItemId === row.id && draggingItemId !== row.id,
            }"
            @dragstart="onDragStart(row.id)"
            @dragover="onDragOver(row.id, $event)"
            @drop.prevent="onDrop(row.id)"
            @dragend="onDragEnd"
          >
            <span class="text-xs text-gray-500 dark:text-gray-400 w-7">{{ row.position }}.</span>
            <span class="text-sm text-gray-900 dark:text-gray-100 flex-1 truncate">
              {{
                row.item_type === 'chapter'
                  ? row.chapter_title || t('booklets.untitledChapter')
                  : row.custom_title || row.lesson_title || `Lesson #${row.lesson_id}`
              }}
            </span>
            <span
              v-if="row.item_type === 'lesson' && row.lesson_status"
              class="text-xs text-gray-500 dark:text-gray-400"
            >
              {{ row.lesson_status }}
            </span>
            <span
              v-if="row.item_type === 'chapter'"
              class="text-xs rounded px-2 py-0.5 bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300"
            >
              {{ t('booklets.chapterBadge') }}
            </span>
            <div class="flex items-center gap-1 ml-2">
              <button
                v-if="row.item_type === 'chapter'"
                class="px-2 py-1 text-xs rounded border border-purple-300 dark:border-purple-700 text-purple-700 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/20 disabled:opacity-50"
                :disabled="mutating"
                @click="openEditChapterModal(row)"
              >
                {{ t('booklets.actions.viewEditChapter') }}
              </button>
              <button
                class="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                :disabled="!isDraft || mutating || idx === 0"
                @click="moveItem(row.id, 'up')"
              >
                ↑
              </button>
              <button
                class="px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
                :disabled="!isDraft || mutating || idx === orderedItems.length - 1"
                @click="moveItem(row.id, 'down')"
              >
                ↓
              </button>
              <button
                class="px-2 py-1 text-xs rounded border border-red-300 dark:border-red-700 text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
                :disabled="!isDraft || mutating"
                @click="removeItem(row)"
              >
                {{ row.item_type === 'chapter' ? t('booklets.actions.removeChapter') : t('booklets.actions.removeLesson') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showEditBookletModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="closeEditBookletModal"
    >
      <div class="w-full max-w-lg bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700">
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
            {{ t('booklets.editTitle') }}
          </h3>
        </div>
        <form class="px-6 py-4 space-y-4" @submit.prevent="saveBookletMeta">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('booklets.fields.title') }}
            </label>
            <input
              v-model="bookletForm.title"
              type="text"
              class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
              :placeholder="t('booklets.placeholders.title')"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('booklets.fields.subtitle') }}
            </label>
            <input
              v-model="bookletForm.subtitle"
              type="text"
              class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
              :placeholder="t('booklets.placeholders.subtitle')"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('booklets.fields.description') }}
            </label>
            <textarea
              v-model="bookletForm.description"
              rows="3"
              class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
              :placeholder="t('booklets.placeholders.description')"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('booklets.fields.templateData') }}
            </label>
            <div class="grid grid-cols-2 gap-2 rounded-md border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700/30 p-3">
              <label
                v-for="fieldKey in templateFieldOptions"
                :key="fieldKey"
                class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300"
              >
                <input
                  v-model="bookletForm.template_data"
                  type="checkbox"
                  :value="fieldKey"
                  class="rounded border-gray-300 dark:border-gray-600"
                />
                {{ t(`booklets.templateFields.${fieldKey}`) }}
              </label>
            </div>
          </div>
          <div class="flex justify-end gap-2 pt-2">
            <button
              type="button"
              class="px-4 py-2 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
              @click="closeEditBookletModal"
            >
              {{ t('booklets.actions.cancel') }}
            </button>
            <button
              type="submit"
              :disabled="mutating || !bookletForm.title.trim()"
              class="px-4 py-2 text-sm rounded-md bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {{ mutating ? t('booklets.actions.saving') : t('booklets.actions.save') }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <div
      v-if="showAddModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="closeAddModal"
    >
      <div class="w-full max-w-6xl max-h-[90vh] bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
            {{ t('booklets.addLessonModalTitle') }}
          </h3>
          <button
            class="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="closeAddModal"
          >
            {{ t('lessons.close') }}
          </button>
        </div>

        <div class="p-5 grid grid-cols-1 lg:grid-cols-3 gap-4 max-h-[calc(90vh-4.5rem)] overflow-hidden">
          <!-- Left panel: course tree -->
          <aside class="lg:col-span-1 bg-white dark:bg-gray-800 shadow-sm rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
            <div class="px-4 py-3 border-b border-gray-200 dark:border-gray-700">
              <h4 class="text-sm font-semibold text-gray-900 dark:text-white">
                {{ t('courses.title') }}
              </h4>
            </div>

            <div v-if="loadingPicker" class="p-4 text-center text-sm text-gray-400 dark:text-gray-500">
              {{ t('booklets.loadingPicker') }}
            </div>

            <div v-else class="overflow-y-auto" style="max-height: calc(90vh - 14rem)">
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
                <span class="flex-1 text-left truncate">{{ t('booklets.allAvailableLessons') }}</span>
              </button>

              <CourseTreeItem
                v-for="node in courseTree"
                :key="node.id"
                :node="node"
                :depth="0"
                :expanded="expandedCourses"
                :selected-id="selectedCourseNode?.id ?? null"
                :show-actions="false"
                @toggle="toggleCourse"
                @select="selectCourseNode"
              />
            </div>
          </aside>

          <!-- Right panel: available lessons -->
          <div class="lg:col-span-2 min-w-0">
            <div v-if="modalLessons.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-700">
              {{ t('booklets.noAvailableLessons') }}
            </div>

            <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-3 overflow-y-auto" style="max-height: calc(90vh - 14rem)">
              <button
                v-for="lesson in modalLessons"
                :key="lesson.id"
                class="text-left bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 transition-all border border-gray-200 dark:border-gray-700 disabled:cursor-not-allowed"
                :class="{
                  'hover:shadow-md dark:hover:shadow-gray-900/50': !selectedLessonIds.has(lesson.id) && isDraft && !mutating,
                  'opacity-60 bg-gray-50 dark:bg-gray-900/30': selectedLessonIds.has(lesson.id),
                }"
                :disabled="!isDraft || mutating || selectedLessonIds.has(lesson.id)"
                @click="addLesson(lesson.id)"
              >
                <div class="flex items-start justify-between gap-2 mb-2">
                  <div class="flex items-start gap-2 min-w-0">
                    <DocumentTextIcon class="h-5 w-5 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-0.5" />
                    <h5 class="text-sm font-semibold text-gray-900 dark:text-white line-clamp-2">
                      {{ lesson.title }}
                    </h5>
                  </div>
                  <span
                    v-if="selectedLessonIds.has(lesson.id)"
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-indigo-100 text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300"
                  >
                    {{ t('booklets.alreadySelected') }}
                  </span>
                </div>
                <p class="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  {{ lesson.course?.name || t('booklets.uncategorizedLessons') }}
                </p>
                <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
                  <ClockIcon class="h-3.5 w-3.5" />
                  <span>{{ formatDate(lesson.date) }}</span>
                  <span v-if="lesson.duration" class="text-gray-400 dark:text-gray-500">·</span>
                  <span v-if="lesson.duration">{{ formatDuration(lesson.duration) }}</span>
                </div>
                <p v-if="lesson.brief" class="text-xs text-gray-600 dark:text-gray-400 mt-2 line-clamp-2">
                  {{ lesson.brief }}
                </p>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="showAddChapterModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      @click.self="closeAddChapterModal"
    >
      <div class="w-full max-w-xl bg-white dark:bg-gray-800 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
            {{ chapterModalIsEditing ? t('booklets.editChapterModalTitle') : t('booklets.addChapterModalTitle') }}
          </h3>
          <button
            class="px-3 py-1.5 text-sm rounded-md border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700"
            @click="closeAddChapterModal"
          >
            {{ t('booklets.actions.cancel') }}
          </button>
        </div>
        <div class="p-5 space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('booklets.chapterFields.title') }}
            </label>
            <input
              v-model="chapterForm.chapter_title"
              type="text"
              class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
              :placeholder="t('booklets.chapterPlaceholders.title')"
              :disabled="mutating || chapterModalReadOnly"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('booklets.chapterFields.subtitle') }}
            </label>
            <input
              v-model="chapterForm.chapter_subtitle"
              type="text"
              class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
              :placeholder="t('booklets.chapterPlaceholders.subtitle')"
              :disabled="mutating || chapterModalReadOnly"
            />
          </div>
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {{ t('booklets.chapterFields.body') }}
            </label>
            <textarea
              v-model="chapterForm.chapter_body"
              rows="4"
              class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-gray-100"
              :placeholder="t('booklets.chapterPlaceholders.body')"
              :disabled="mutating || chapterModalReadOnly"
            />
          </div>
          <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
            <input
              v-model="chapterForm.chapter_starts_new_page"
              type="checkbox"
              class="rounded border-gray-300 dark:border-gray-600"
              :disabled="mutating || chapterModalReadOnly"
            />
            {{ t('booklets.chapterFields.startsNewPage') }}
          </label>
          <div class="flex justify-end">
            <button
              class="px-4 py-2 text-sm rounded-md bg-purple-600 text-white hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed"
              :disabled="mutating || chapterModalReadOnly || !chapterForm.chapter_title.trim()"
              @click="saveChapter"
            >
              {{ chapterModalIsEditing ? t('booklets.actions.saveChapter') : t('booklets.actions.addChapter') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
