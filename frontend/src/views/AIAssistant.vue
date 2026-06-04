<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from '@headlessui/vue'
import {
  ArrowTopRightOnSquareIcon,
  ChevronUpDownIcon,
  PaperAirplaneIcon,
  SparklesIcon,
} from '@heroicons/vue/24/outline'
import { CheckIcon } from '@heroicons/vue/20/solid'
import { marked } from 'marked'
import { coursesApi } from '@/api/courses'
import { lessonsApi } from '@/api/lessons'
import { searchApi } from '@/api/search'
import type { CourseTreeNode, LessonListItem, RagSearchCitation } from '@/api/types'

type CourseScope = {
  id: number | null
  label: string
  lessonCourseIds: number[]
}
type RagVariant = 'edited' | 'summary'

const { t } = useI18n()

const question = ref('')
const isLoading = ref(false)
const errorMessage = ref('')
const answer = ref('')
const citations = ref<RagSearchCitation[]>([])
const lessons = ref<LessonListItem[]>([])
const courseTree = ref<CourseTreeNode[]>([])
const selectedCourse = ref<CourseScope | null>(null)
const selectedHebrewYear = ref<string | null>(null)
const selectedVariant = ref<RagVariant>('edited')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const sourceColumnRef = ref<HTMLElement | null>(null)
const highlightedReference = ref<number | null>(null)
const variantOptions: RagVariant[] = ['edited', 'summary']
let highlightTimeout: ReturnType<typeof setTimeout> | null = null

const allCourseScope = computed<CourseScope>(() => ({
  id: null,
  label: t('assistant.allCourses'),
  lessonCourseIds: [],
}))

const collectCourseIds = (node: CourseTreeNode): number[] => [
  node.id,
  ...node.children.flatMap((child) => collectCourseIds(child)),
]

const flattenCourseScopes = (
  nodes: CourseTreeNode[],
  parentPath = '',
): CourseScope[] => {
  const scopes: CourseScope[] = []
  for (const node of nodes) {
    const label = parentPath ? `${parentPath} > ${node.name}` : node.name
    scopes.push({
      id: node.id,
      label,
      lessonCourseIds: collectCourseIds(node),
    })
    scopes.push(...flattenCourseScopes(node.children, label))
  }
  return scopes
}

const courseScopes = computed<CourseScope[]>(() => [
  allCourseScope.value,
  ...flattenCourseScopes(courseTree.value),
])

const hebrewYears = computed<string[]>(() => {
  const years = new Set<string>()
  for (const lesson of lessons.value) {
    const year = lesson.hebrew_date?.trim()
    if (year) years.add(year)
  }
  return [...years].sort((a, b) => Number(b) - Number(a))
})

const scopedLessons = computed(() => {
  return lessons.value.filter((lesson) => {
    if (selectedCourse.value?.id) {
      const courseId = lesson.course?.id
      if (!courseId || !selectedCourse.value.lessonCourseIds.includes(courseId)) return false
    }
    if (selectedHebrewYear.value) {
      if ((lesson.hebrew_date?.trim() ?? '') !== selectedHebrewYear.value) return false
    }
    return true
  })
})

const scopedLessonIds = computed(() => scopedLessons.value.map((lesson) => lesson.id))
const hasAnswer = computed(() => !!answer.value || citations.value.length > 0)
const citationReferenceNumbers = computed(() => new Set(citations.value.map((citation) => citation.reference_number)))
const answerHtml = computed(() => renderAnswerMarkdown(answer.value))

const activeCourseLabel = computed(() => selectedCourse.value?.label ?? allCourseScope.value.label)
const activeHebrewYearLabel = computed(() => selectedHebrewYear.value ?? t('assistant.allHebrewYears'))

const renderMarkdown = (markdown: string): string => {
  return marked.parse(markdown || '') as string
}

const formatLessonDate = (dateValue: string | null | undefined): string => {
  if (!dateValue) return ''
  const date = new Date(dateValue)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString()
}

const renderAnswerMarkdown = (markdown: string): string => {
  const citationTokenPrefix = 'RAG_CITATION_REFERENCE_'
  const withCitationTokens = (markdown || '').replace(/\\?\[(\d+)\]/g, (match, rawReference) => {
    const referenceNumber = Number(rawReference)
    if (!citationReferenceNumbers.value.has(referenceNumber)) return match
    return `${citationTokenPrefix}${referenceNumber}__`
  })
  return (marked.parse(withCitationTokens) as string).replace(
    new RegExp(`${citationTokenPrefix}(\\d+)__`, 'g'),
    (_match, rawReference) => {
      const referenceNumber = Number(rawReference)
      if (!citationReferenceNumbers.value.has(referenceNumber)) return `[${rawReference}]`
      return `<a href="#source-${referenceNumber}" data-source-reference="${referenceNumber}" class="inline-flex items-center rounded bg-indigo-50 px-1 font-semibold text-indigo-700 no-underline hover:bg-indigo-100 dark:bg-indigo-900/40 dark:text-indigo-200 dark:hover:bg-indigo-900/70">[${referenceNumber}]</a>`
    },
  )
}

const scrollToSourceReference = async (referenceNumber: number) => {
  await nextTick()
  const container = sourceColumnRef.value
  const card = container?.querySelector<HTMLElement>(`[data-source-card="${referenceNumber}"]`)
  if (!container || !card) return

  if (container.scrollHeight <= container.clientHeight) {
    card.scrollIntoView({ behavior: 'smooth', block: 'start' })
  } else {
  const containerRect = container.getBoundingClientRect()
  const cardRect = card.getBoundingClientRect()
  container.scrollTo({
    top: cardRect.top - containerRect.top + container.scrollTop - 8,
    behavior: 'smooth',
  })
  }

  highlightedReference.value = referenceNumber
  if (highlightTimeout) clearTimeout(highlightTimeout)
  highlightTimeout = setTimeout(() => {
    highlightedReference.value = null
    highlightTimeout = null
  }, 1400)
}

const handleAnswerClick = (event: MouseEvent) => {
  const target = event.target as HTMLElement | null
  const link = target?.closest<HTMLAnchorElement>('a[data-source-reference]')
  if (!link) return

  event.preventDefault()
  const referenceNumber = Number(link.dataset.sourceReference)
  if (Number.isFinite(referenceNumber)) {
    void scrollToSourceReference(referenceNumber)
  }
}

const resizeTextarea = async () => {
  await nextTick()
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 220)}px`
}

const submitQuestion = async () => {
  const cleanQuestion = question.value.trim()
  if (!cleanQuestion || isLoading.value) return

  if (scopedLessonIds.value.length === 0) {
    answer.value = ''
    citations.value = []
    errorMessage.value = t('assistant.emptyScope')
    return
  }

  try {
    isLoading.value = true
    errorMessage.value = ''
    answer.value = ''
    citations.value = []
    const response = await searchApi.askAi({
      question: cleanQuestion,
      lesson_ids: scopedLessonIds.value,
      variant: selectedVariant.value,
    })
    answer.value = response.answer
    citations.value = response.citations
  } catch {
    errorMessage.value = t('assistant.searchFailed')
  } finally {
    isLoading.value = false
  }
}

const clearAnswer = () => {
  answer.value = ''
  citations.value = []
  errorMessage.value = ''
}

const loadData = async () => {
  try {
    const [lessonRows, treeRows] = await Promise.all([
      lessonsApi.list(),
      coursesApi.tree(),
    ])
    lessons.value = lessonRows
    courseTree.value = treeRows
    selectedCourse.value = allCourseScope.value
  } catch {
    errorMessage.value = t('assistant.loadFailed')
  }
}

watch(question, () => {
  void resizeTextarea()
})

onMounted(async () => {
  await loadData()
  await resizeTextarea()
})
</script>

<template>
  <div class="min-h-[calc(100vh-5rem)] bg-gray-50 dark:bg-gray-900 px-4 py-10">
    <div
      :class="[
        'mx-auto transition-all duration-500',
        hasAnswer || isLoading || errorMessage ? 'max-w-5xl' : 'max-w-3xl pt-16 md:pt-28'
      ]"
    >
      <div class="text-center mb-8">
        <div class="inline-flex items-center justify-center rounded-2xl bg-indigo-100 dark:bg-indigo-900/40 p-3 mb-4">
          <SparklesIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-300" />
        </div>
        <h1 class="text-3xl font-bold text-gray-900 dark:text-white">
          {{ t('assistant.title') }}
        </h1>
        <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
          {{ t('assistant.subtitle') }}
        </p>
      </div>

      <form
        class="rounded-3xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-xl shadow-indigo-100/60 dark:shadow-black/20 overflow-visible"
        @submit.prevent="submitQuestion"
      >
        <textarea
          ref="textareaRef"
          v-model="question"
          rows="3"
          :placeholder="t('assistant.placeholder')"
          class="block w-full resize-none border-0 bg-transparent px-6 py-5 text-base text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-500 focus:ring-0"
          @keydown.enter.ctrl.prevent="submitQuestion"
          @keydown.enter.meta.prevent="submitQuestion"
        ></textarea>

        <div class="flex flex-col gap-3 border-t border-gray-100 dark:border-gray-700 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {{ t('assistant.context') }}
            </span>

            <div class="inline-flex rounded-full bg-gray-100 dark:bg-gray-700 p-1">
              <button
                v-for="variant in variantOptions"
                :key="variant"
                type="button"
                :class="[
                  'rounded-full px-3 py-1 text-sm font-medium transition-colors',
                  selectedVariant === variant
                    ? 'bg-white dark:bg-gray-900 text-indigo-700 dark:text-indigo-300 shadow-sm'
                    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'
                ]"
                @click="selectedVariant = variant"
              >
                {{ t(`assistant.variant.${variant}`) }}
              </button>
            </div>

            <Listbox v-model="selectedCourse">
              <div class="relative">
                <ListboxButton class="inline-flex items-center gap-2 rounded-full bg-indigo-50 dark:bg-indigo-900/30 px-3 py-1.5 text-sm font-medium text-indigo-700 dark:text-indigo-200 hover:bg-indigo-100 dark:hover:bg-indigo-900/50">
                  <span class="max-w-72 truncate">{{ activeCourseLabel }}</span>
                  <ChevronUpDownIcon class="h-4 w-4" />
                </ListboxButton>
                <ListboxOptions class="absolute z-20 mt-2 max-h-72 w-80 overflow-auto rounded-xl bg-white dark:bg-gray-800 py-1 text-sm shadow-lg ring-1 ring-black/10 dark:ring-white/10 focus:outline-none">
                  <ListboxOption
                    v-for="scope in courseScopes"
                    :key="scope.id ?? 'all'"
                    v-slot="{ active, selected }"
                    :value="scope"
                    as="template"
                  >
                    <li :class="[
                      'relative cursor-pointer select-none py-2 pl-3 pr-9',
                      active ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100'
                    ]">
                      <span :class="[selected ? 'font-semibold' : 'font-normal', 'block truncate']">
                        {{ scope.label }}
                      </span>
                      <span v-if="selected" :class="[
                        'absolute inset-y-0 right-0 flex items-center pr-3',
                        active ? 'text-white' : 'text-indigo-600'
                      ]">
                        <CheckIcon class="h-5 w-5" />
                      </span>
                    </li>
                  </ListboxOption>
                </ListboxOptions>
              </div>
            </Listbox>

            <Listbox v-model="selectedHebrewYear">
              <div class="relative">
                <ListboxButton class="inline-flex items-center gap-2 rounded-full bg-gray-100 dark:bg-gray-700 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600">
                  <span>{{ activeHebrewYearLabel }}</span>
                  <ChevronUpDownIcon class="h-4 w-4" />
                </ListboxButton>
                <ListboxOptions class="absolute z-20 mt-2 max-h-72 w-56 overflow-auto rounded-xl bg-white dark:bg-gray-800 py-1 text-sm shadow-lg ring-1 ring-black/10 dark:ring-white/10 focus:outline-none">
                  <ListboxOption v-slot="{ active, selected }" :value="null" as="template">
                    <li :class="[
                      'relative cursor-pointer select-none py-2 pl-3 pr-9',
                      active ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100'
                    ]">
                      <span :class="[selected ? 'font-semibold' : 'font-normal', 'block truncate']">
                        {{ t('assistant.allHebrewYears') }}
                      </span>
                      <span v-if="selected" :class="[
                        'absolute inset-y-0 right-0 flex items-center pr-3',
                        active ? 'text-white' : 'text-indigo-600'
                      ]">
                        <CheckIcon class="h-5 w-5" />
                      </span>
                    </li>
                  </ListboxOption>
                  <ListboxOption
                    v-for="year in hebrewYears"
                    :key="year"
                    v-slot="{ active, selected }"
                    :value="year"
                    as="template"
                  >
                    <li :class="[
                      'relative cursor-pointer select-none py-2 pl-3 pr-9',
                      active ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100'
                    ]">
                      <span :class="[selected ? 'font-semibold' : 'font-normal', 'block truncate']">
                        {{ year }}
                      </span>
                      <span v-if="selected" :class="[
                        'absolute inset-y-0 right-0 flex items-center pr-3',
                        active ? 'text-white' : 'text-indigo-600'
                      ]">
                        <CheckIcon class="h-5 w-5" />
                      </span>
                    </li>
                  </ListboxOption>
                </ListboxOptions>
              </div>
            </Listbox>

            <span class="rounded-full bg-gray-100 dark:bg-gray-700 px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-300">
              {{ t('assistant.scopeCount', { count: scopedLessonIds.length }) }}
            </span>
          </div>

          <div class="flex items-center gap-2 self-end sm:self-auto">
            <button
              v-if="hasAnswer || errorMessage"
              type="button"
              class="rounded-full px-3 py-2 text-sm font-medium text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
              @click="clearAnswer"
            >
              {{ t('assistant.clear') }}
            </button>
            <button
              type="submit"
              :disabled="!question.trim() || isLoading"
              class="inline-flex items-center gap-2 rounded-full bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <PaperAirplaneIcon class="h-4 w-4" />
              {{ isLoading ? t('assistant.asking') : t('assistant.ask') }}
            </button>
          </div>
        </div>
      </form>

      <div v-if="isLoading" class="mt-8 rounded-2xl bg-white dark:bg-gray-800 p-6 shadow-sm border border-gray-200 dark:border-gray-700">
        <div class="flex items-center gap-3 text-indigo-600 dark:text-indigo-300">
          <SparklesIcon class="h-5 w-5 animate-pulse" />
          <span class="text-sm font-medium">{{ t('assistant.thinking') }}</span>
        </div>
      </div>

      <div v-if="errorMessage" class="mt-8 rounded-2xl border border-red-200 dark:border-red-900/60 bg-red-50 dark:bg-red-950/30 p-5 text-sm text-red-700 dark:text-red-300">
        {{ errorMessage }}
      </div>

      <section v-if="answer" class="mt-8 grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
        <article class="lg:col-span-2 rounded-2xl bg-white dark:bg-gray-800 p-6 shadow-sm border border-gray-200 dark:border-gray-700">
          <div
            class="prose prose-indigo max-w-none dark:prose-invert"
            @click="handleAnswerClick"
            v-html="answerHtml"
          ></div>
        </article>

        <aside
          v-if="citations.length > 0"
          ref="sourceColumnRef"
          class="lg:col-span-1 lg:sticky lg:top-4 max-h-none lg:max-h-[calc(100vh-2rem)] overflow-visible lg:overflow-y-auto pr-0 lg:pr-2 custom-scrollbar"
        >
          <h2 class="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            {{ t('assistant.sources') }}
          </h2>
          <div class="mt-3 flex flex-col gap-4">
          <article
            v-for="citation in citations"
            :id="`source-${citation.reference_number}`"
            :key="citation.chunk_id"
            :data-source-card="citation.reference_number"
            :class="[
              'rounded-2xl border bg-white dark:bg-gray-800 p-4 shadow-sm transition-all',
              highlightedReference === citation.reference_number
                ? 'border-yellow-300 ring-4 ring-yellow-200/80 dark:border-yellow-400 dark:ring-yellow-500/20'
                : 'border-gray-200 dark:border-gray-700'
            ]"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex items-start gap-2">
                  <span class="mt-0.5 inline-flex flex-shrink-0 items-center rounded-md bg-indigo-100 dark:bg-indigo-900/40 px-2 py-0.5 text-xs font-bold text-indigo-700 dark:text-indigo-200">
                    [{{ citation.reference_number }}]
                  </span>
                  <a
                    :href="`/lessons/${citation.lesson_hashid}`"
                    class="text-sm font-semibold text-gray-900 dark:text-white hover:text-indigo-600 dark:hover:text-indigo-300"
                  >
                    {{ citation.lesson_title }}
                  </a>
                </div>
                <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  <span v-if="citation.lesson_course_path">{{ citation.lesson_course_path }}</span>
                  <span v-if="citation.lesson_course_path && formatLessonDate(citation.lesson_date)"> · </span>
                  <span v-if="formatLessonDate(citation.lesson_date)">{{ formatLessonDate(citation.lesson_date) }}</span>
                </p>
                <p class="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  {{ t(`assistant.variant.${citation.variant}`) }} · {{ t('assistant.chunkNumber', { number: citation.chunk_index + 1 }) }}
                </p>
              </div>
              <a
                :href="`/lessons/${citation.lesson_hashid}`"
                class="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-indigo-600 dark:hover:bg-gray-700 dark:hover:text-indigo-300"
                :aria-label="citation.lesson_title"
              >
                <ArrowTopRightOnSquareIcon class="h-4 w-4" />
              </a>
            </div>
            <div
              class="prose prose-sm prose-indigo mt-3 max-w-none dark:prose-invert text-gray-700 dark:text-gray-200"
              v-html="renderMarkdown(citation.snippet)"
            ></div>
          </article>
          </div>
        </aside>
      </section>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar {
  scrollbar-width: thin;
  scrollbar-color: rgb(199 210 254) transparent;
}

.custom-scrollbar::-webkit-scrollbar {
  width: 8px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgb(199 210 254);
  border-radius: 9999px;
}
</style>
