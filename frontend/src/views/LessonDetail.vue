<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { marked } from 'marked'
import {
  ArrowLeftIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  CalendarIcon,
  DocumentTextIcon,
  FolderIcon,
  PlayIcon,
  PauseIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
  PrinterIcon,
  TrashIcon,
  ExclamationTriangleIcon,
  CogIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  MagnifyingGlassIcon,
  ChartBarIcon,
  StopIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  ClockIcon as HistoryIcon,
} from '@heroicons/vue/24/outline'
import { SpeakerWaveIcon } from '@heroicons/vue/24/solid'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { lessonsApi } from '@/api/lessons'
import { coursesApi } from '@/api/courses'
import { themesApi } from '@/api/themes'
import { tasksApi } from '@/api/tasks'
import { configApi } from '@/api/config'
import { sourcesApi } from '@/api/sources'
import { usersApi, type ClerkUser } from '@/api/users'
import { useToast } from '@/composables/useToast'
import { usePermissions } from '@/composables/usePermissions'
import { useAuth } from '@/composables/useAuth'
import VersionHistoryPanel from '@/components/VersionHistoryPanel.vue'
import MilkdownEditor from '@/components/MilkdownEditor.vue'
import LessonDocumentModal from '@/components/LessonDocumentModal.vue'
import type {
  LessonDetail as LessonDetailType,
  LessonSource,
  LessonStatus,
  LessonWorkflowStep,
  LessonWorkflowStepStatus,
  Course,
  CourseTreeNode,
  Theme,
  ContentType,
  AuditLogRow,
} from '@/api/types'

const props = defineProps<{
  lesson: LessonDetailType
  hasPreviousLesson?: boolean
  hasNextLesson?: boolean
  autoplayFrom?: number | null
  initialHistoryContentType?: ContentType | null
  initialHistoryVersionId?: string | null
  initialHistoryCompare?: {
    versionAId: string
    versionBId: string
    fromVersionNumber?: number | null
    toVersionNumber?: number | null
  } | null
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'previous'): void
  (e: 'next'): void
}>()

const { t, locale } = useI18n()
const toast = useToast()
const { can, role } = usePermissions()
const { user } = useAuth()

const showLessonPager = computed(
  () => props.hasPreviousLesson !== undefined || props.hasNextLesson !== undefined,
)

const canEditLesson = computed(() => {
  if (['publisher', 'admin'].includes(role.value)) return true
  if (role.value === 'editor') {
    const userId = user.value?.id
    return !!userId && (props.lesson.editors ?? []).some((e) => e.user_id === userId)
  }
  return false
})

const audioUrl = ref<string | null>(null)

// Audio player ref and state
const audioPlayer = ref<HTMLAudioElement | null>(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const currentSegment = ref<{ start: number; end: number } | null>(null)

const courses = ref<Course[]>([])
const courseTree = ref<CourseTreeNode[]>([])
const themes = ref<Theme[]>([])
const users = ref<ClerkUser[]>([])

type LessonTabExportView = 'summary' | 'edited' | 'transcript'
type LessonExportFormat = 'pdf' | 'docx' | 'md'
type DocumentModalMode = 'export' | 'import'
type LessonExportPreferences = {
  format: LessonExportFormat
  includeFields: string[]
}

const EXPORT_PREFERENCES_STORAGE_KEY = 'lessonExportPreferences'
const FALLBACK_EXPORT_FIELDS = ['title', 'date']

const isLessonExportFormat = (value: unknown): value is LessonExportFormat =>
  value === 'pdf' || value === 'docx' || value === 'md'

const loadLessonExportPreferences = (): LessonExportPreferences => {
  if (typeof window === 'undefined') {
    return { format: 'docx', includeFields: [...FALLBACK_EXPORT_FIELDS] }
  }
  try {
    const raw = window.localStorage.getItem(EXPORT_PREFERENCES_STORAGE_KEY)
    if (!raw) return { format: 'docx', includeFields: [...FALLBACK_EXPORT_FIELDS] }
    const parsed = JSON.parse(raw) as Partial<LessonExportPreferences>
    const format = isLessonExportFormat(parsed.format) ? parsed.format : 'docx'
    const includeFields = Array.isArray(parsed.includeFields)
      ? parsed.includeFields.filter((field): field is string => typeof field === 'string')
      : [...FALLBACK_EXPORT_FIELDS]
    return { format, includeFields: includeFields.length ? includeFields : [...FALLBACK_EXPORT_FIELDS] }
  } catch {
    return { format: 'docx', includeFields: [...FALLBACK_EXPORT_FIELDS] }
  }
}

const saveLessonExportPreferences = (preferences: LessonExportPreferences) => {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(EXPORT_PREFERENCES_STORAGE_KEY, JSON.stringify(preferences))
  } catch {
    // Ignore storage errors (private mode / quota / browser restrictions).
  }
}

const showLessonDocumentModal = ref(false)
const lessonDocumentMode = ref<DocumentModalMode>('export')
const lessonDocumentView = ref<LessonTabExportView>('summary')
const isSubmittingLessonDocument = ref(false)
const lessonExportPreferences = ref<LessonExportPreferences>(loadLessonExportPreferences())
const defaultLessonExportFormat = computed<LessonExportFormat>(() => lessonExportPreferences.value.format)
const defaultLessonExportFields = computed<string[]>(() => lessonExportPreferences.value.includeFields)

// Toggle between summary, corrected transcript, and initial transcript
const activeView = ref('summary')

// Edit summary state
const isEditingSummary = ref(false)
const editedSummary = ref('')
const isSavingSummary = ref(false)
const DRAFT_SAVE_DEBOUNCE_MS = 500
let summaryDraftSaveTimeout: ReturnType<typeof setTimeout> | null = null

// Edit full edited-markdown state
const isEditingEditedMarkdown = ref(false)
const editedMarkdownDraft = ref('')
const isSavingEditedMarkdown = ref(false)
let editedDraftSaveTimeout: ReturnType<typeof setTimeout> | null = null
const showDraftRestoreDialog = ref(false)
const draftRestoreTarget = ref<'summary' | 'edited' | null>(null)
const draftRestoreBaseValue = ref('')
const draftRestoreValue = ref('')

const getSummaryDraftStorageKey = () => `lessons:draft:summary:${props.lesson.hashid}`
const getEditedDraftStorageKey = () => `lessons:draft:edited:${props.lesson.hashid}`

const clearDraftSaveTimeout = (kind: 'summary' | 'edited') => {
  const timeout = kind === 'summary' ? summaryDraftSaveTimeout : editedDraftSaveTimeout
  if (!timeout) return
  clearTimeout(timeout)
  if (kind === 'summary') summaryDraftSaveTimeout = null
  else editedDraftSaveTimeout = null
}

const readDraftFromStorage = (storageKey: string): string | null => {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(storageKey)
  return raw === null ? null : raw
}

const saveDraftToStorage = (storageKey: string, value: string) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(storageKey, value)
}

const clearDraftFromStorage = (storageKey: string) => {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(storageKey)
}

const getDraftCandidate = (
  contentType: 'summary' | 'edited',
  baseValue: string,
): string | null => {
  const storageKey =
    contentType === 'summary'
      ? getSummaryDraftStorageKey()
      : getEditedDraftStorageKey()
  const draft = readDraftFromStorage(storageKey)
  if (draft === null || draft === baseValue) return null
  return draft
}

const openEditorWithValue = (
  contentType: 'summary' | 'edited',
  value: string,
) => {
  if (contentType === 'summary') {
    editedSummary.value = value
    isEditingSummary.value = true
    return
  }

  editedMarkdownDraft.value = value
  isEditingEditedMarkdown.value = true
}

const startDraftRestoreFlow = (
  contentType: 'summary' | 'edited',
  baseValue: string,
  draftValue: string,
) => {
  draftRestoreTarget.value = contentType
  draftRestoreBaseValue.value = baseValue
  draftRestoreValue.value = draftValue
  showDraftRestoreDialog.value = true
}

const closeDraftRestoreDialogState = () => {
  showDraftRestoreDialog.value = false
  draftRestoreTarget.value = null
  draftRestoreBaseValue.value = ''
  draftRestoreValue.value = ''
}

const handleDraftRestoreDecision = (shouldRestore: boolean) => {
  const target = draftRestoreTarget.value
  if (!target) {
    closeDraftRestoreDialogState()
    return
  }
  const nextValue = shouldRestore ? draftRestoreValue.value : draftRestoreBaseValue.value
  closeDraftRestoreDialogState()
  openEditorWithValue(target, nextValue)
}

const draftRestoreTitle = computed(() => {
  return draftRestoreTarget.value === 'summary'
    ? t('lessons.restoreSummaryDraftTitle')
    : t('lessons.restoreEditedDraftTitle')
})

const draftRestoreMessage = computed(() => {
  return draftRestoreTarget.value === 'summary'
    ? t('lessons.restoreSummaryDraftConfirm')
    : t('lessons.restoreEditedDraftConfirm')
})

const scheduleDraftSave = (
  contentType: 'summary' | 'edited',
  value: string,
) => {
  const storageKey =
    contentType === 'summary'
      ? getSummaryDraftStorageKey()
      : getEditedDraftStorageKey()
  clearDraftSaveTimeout(contentType)
  const timeout = setTimeout(() => {
    saveDraftToStorage(storageKey, value)
    if (contentType === 'summary') summaryDraftSaveTimeout = null
    else editedDraftSaveTimeout = null
  }, DRAFT_SAVE_DEBOUNCE_MS)
  if (contentType === 'summary') summaryDraftSaveTimeout = timeout
  else editedDraftSaveTimeout = timeout
}

// Edit lesson state
const isEditingLesson = ref(false)
const editedLesson = ref<{
  title: string
  date: string
  course_id: number | null
  theme_ids: number[]
  editor_ids: string[]
  brief: string
}>({ title: '', date: '', course_id: null, theme_ids: [], editor_ids: [], brief: '' })
const isSavingLesson = ref(false)

// Edit segment state
const editingSegmentIndex = ref<number | null>(null)
const editedSegmentText = ref('')
const isSavingSegment = ref(false)

// Edit edited-paragraph state
const editingParagraphIndex = ref<number | null>(null)
const editedParagraphText = ref('')
const isSavingParagraph = ref(false)

// Delete confirmation state
const showDeleteConfirm = ref(false)
const isDeleting = ref(false)

// Source modal state
const showSourceModal = ref(false)
const selectedSourceEditedText = ref('')
const selectedSource = ref<Record<string, unknown> | null>(null)
const sefariaTextEnglish = ref('')
const sefariaTextHebrew = ref('')
const isLoadingSefaria = ref(false)
const sefariaDisplayMode = ref<'he' | 'en' | 'both'>('both')

// Source stats modal state
const showSourceStatsModal = ref(false)
const workflowAuditLog = ref<AuditLogRow[]>([])
const workflowAuditLoading = ref(false)
const workflowExpandedPayload = ref<Set<number>>(new Set())

// Transcript expander state (for edited view)
const expandedTranscriptIndex = ref<number | null>(null)
const showSideBySideTranscript = ref(false)
const showSourcesInEdited = ref(true)
const showSummaryWithEdited = ref(false)

const historyContentType = ref<ContentType | null>(props.initialHistoryContentType ?? null)
const historySelectedVersionId = ref<string | null>(props.initialHistoryVersionId ?? null)
const historyActiveCompare = ref<{
  versionAId: string
  versionBId: string
  fromVersionNumber?: number | null
  toVersionNumber?: number | null
} | null>(props.initialHistoryCompare ?? null)
const isHistoryMode = computed(() => historyContentType.value !== null)

// Process tasks modal state
const showProcessModal = ref(false)
const selectedProcesses = ref<Record<string, boolean>>({
  transcribe: false, correct: false, edition: false, extraction: false, summary: false, brief: false, sources: false,
})
const selectedSummaryPrompt = ref('')
const availableSummaryPrompts = ref<Array<{ name: string; text: string }>>([])
const selectedCorrectionPrompt = ref('')
const availableCorrectionPrompts = ref<Array<{ name: string; text: string }>>([])
const selectedEditionPrompt = ref('')
const availableEditionPrompts = ref<Array<{ name: string; text: string }>>([])
const selectedExtractionPrompt = ref('')
const availableExtractionPrompts = ref<Array<{ name: string; text: string }>>([])
const selectedSourcesPrompt = ref('')
const availableSourcesPrompts = ref<Array<{ name: string; text: string }>>([])
const isCreatingTasks = ref(false)

// Configure marked options
marked.setOptions({ breaks: true, gfm: true })

// Processing status
const isProcessing = computed(() => !!props.lesson.process_status)

const processStatusLabel = computed(() => {
  const statusMap: Record<string, string> = {
    transcript: t('lessons.processStatusTranscript'),
    edition: t('lessons.processStatusEdition'),
    sources_extraction: t('lessons.processStatusSourcesExtraction'),
    sources_checking: t('lessons.processStatusSourcesChecking'),
    summary: t('lessons.processStatusSummary'),
  }
  return props.lesson.process_status
    ? statusMap[props.lesson.process_status] ?? props.lesson.process_status
    : ''
})

// Auto-refresh while processing
let refreshInterval: ReturnType<typeof setInterval> | null = null
let awaitingProcessing = false  // true after creating tasks, before worker picks them up

const refreshLesson = async () => {
  try {
    const updated = await lessonsApi.get(props.lesson.hashid)
    Object.assign(props.lesson, updated)
    if (updated.process_status) {
      // Worker has picked up the task — no longer "awaiting"
      awaitingProcessing = false
    } else if (!awaitingProcessing) {
      // Processing finished (status went from non-null → null) — stop polling
      stopPolling()
    }
  } catch { /* silent */ }
}

const startPolling = () => {
  if (refreshInterval) return
  refreshInterval = setInterval(refreshLesson, 5000)
}

const stopPolling = () => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
  awaitingProcessing = false
}

watch(isProcessing, (processing) => {
  if (processing) {
    startPolling()
  } else if (!awaitingProcessing) {
    stopPolling()
  }
}, { immediate: true })

onBeforeUnmount(() => {
  stopPolling()
  clearDraftSaveTimeout('summary')
  clearDraftSaveTimeout('edited')
})

// Render markdown to HTML
const renderMarkdown = (markdown: string | null | undefined): string => {
  if (!markdown) return ''
  return marked(markdown) as string
}

type EditedPart = { start: number; end: number; text: string }

const splitMarkdownParagraphs = (markdown: string | null | undefined): string[] => {
  if (!markdown) return []
  return markdown
    .split(/\n\s*\n+/)
    .map((p) => p.trim())
    .filter((p) => p.length > 0)
}

const editedParts = computed<EditedPart[]>(() => {
  const payload = props.lesson.edited_transcript
  if (!payload?.markdown) return []
  const paragraphs = splitMarkdownParagraphs(payload.markdown)
  const alignment = Array.isArray(payload.alignment) ? payload.alignment : []
  return paragraphs.map((text, index) => {
    const row = alignment[index]
    return {
      start: typeof row?.start === 'number' ? row.start : 0,
      end: typeof row?.end === 'number' ? row.end : 0,
      text,
    }
  })
})

const isEditedAlignmentStale = computed(() => {
  const payload = props.lesson.edited_transcript
  if (!payload?.markdown) return false
  const paragraphs = splitMarkdownParagraphs(payload.markdown)
  const alignment = Array.isArray(payload.alignment) ? payload.alignment : []
  if (paragraphs.length === 0) return false
  if (!payload.aligned_at || !payload.markdown_hash || !payload.transcript_hash) return true
  if (alignment.length !== paragraphs.length) return true
  return alignment.some((row) => {
    if (!row) return true
    const hasIndexes = typeof row.start_index === 'number' && typeof row.end_index === 'number'
    const hasTimes = typeof row.start === 'number' && typeof row.end === 'number'
    const intentionallyUnaligned = !hasIndexes && !hasTimes && typeof row.match_score === 'number'
    return !(hasIndexes && hasTimes) && !intentionallyUnaligned
  })
})

const isSummaryAlignmentStale = computed(() => {
  if (!props.lesson.summary || !props.lesson.edited_transcript?.markdown) return false
  const meta = (props.lesson.summary_metadata ?? {}) as Record<string, unknown>
  const rows = Array.isArray(meta.summary_alignment) ? meta.summary_alignment : []
  if (!meta.summary_aligned_at || !meta.summary_hash || !meta.edited_markdown_hash) return true
  if (rows.length === 0) return true
  return false
})

const summaryParagraphs = computed(() => splitMarkdownParagraphs(props.lesson.summary || ''))

type SummaryAlignedRow = {
  summaryText: string
  startIndex: number | null
  endIndex: number | null
  alignedEditedParts: EditedPart[]
}
type SummaryEditedPart = EditedPart & {
  paragraphIndex: number
  isUnmatched: boolean
}
type SummaryCompareRow = {
  key: string
  summaryText: string | null
  editedParts: SummaryEditedPart[]
  isUnmatchedEditedRow: boolean
}

const summaryAlignedRows = computed<SummaryAlignedRow[]>(() => {
  const meta = (props.lesson.summary_metadata ?? {}) as Record<string, unknown>
  const alignment = Array.isArray(meta.summary_alignment) ? meta.summary_alignment as Array<Record<string, unknown>> : []
  const edited = editedParts.value
  return summaryParagraphs.value.map((summaryText, index) => {
    const row = alignment[index]
    const startIndex = typeof row?.start_index === 'number' ? row.start_index : null
    const endIndex = typeof row?.end_index === 'number' ? row.end_index : null
    let alignedEditedParts: EditedPart[] = []
    if (
      startIndex !== null &&
      endIndex !== null &&
      startIndex >= 0 &&
      endIndex >= startIndex &&
      endIndex < edited.length
    ) {
      alignedEditedParts = edited.slice(startIndex, endIndex + 1)
    }
    return { summaryText, startIndex, endIndex, alignedEditedParts }
  })
})

const summaryComparisonRows = computed<SummaryCompareRow[]>(() => {
  const edited = editedParts.value
  const rows: SummaryCompareRow[] = []
  let nextEditedIndex = 0

  const pushUnmatchedRowsUntil = (targetExclusive: number) => {
    const limit = Math.min(targetExclusive, edited.length)
    for (let idx = nextEditedIndex; idx < limit; idx += 1) {
      const part = edited[idx]
      rows.push({
        key: `unmatched-${idx}`,
        summaryText: null,
        editedParts: [{ ...part, paragraphIndex: idx, isUnmatched: true }],
        isUnmatchedEditedRow: true,
      })
    }
    nextEditedIndex = Math.max(nextEditedIndex, limit)
  }

  summaryAlignedRows.value.forEach((row, rowIndex) => {
    const validRange = (
      row.startIndex !== null &&
      row.endIndex !== null &&
      row.startIndex >= 0 &&
      row.endIndex >= row.startIndex &&
      row.endIndex < edited.length
    )

    let editedRowParts: SummaryEditedPart[] = []
    if (validRange) {
      pushUnmatchedRowsUntil(row.startIndex as number)
      const start = row.startIndex as number
      const end = row.endIndex as number
      editedRowParts = edited.slice(start, end + 1).map((part, offset) => ({
        ...part,
        paragraphIndex: start + offset,
        isUnmatched: false,
      }))
      nextEditedIndex = Math.max(nextEditedIndex, end + 1)
    }

    rows.push({
      key: `summary-${rowIndex}`,
      summaryText: row.summaryText,
      editedParts: editedRowParts,
      isUnmatchedEditedRow: false,
    })
  })

  pushUnmatchedRowsUntil(edited.length)
  return rows
})

const isSummaryAlignedPartPlaying = (part: EditedPart): boolean =>
  isPlaying.value &&
  currentTime.value >= part.start &&
  currentTime.value < part.end

// Format seconds to MM:SS format
const formatTimestamp = (seconds: number | null | undefined): string => {
  if (!seconds && seconds !== 0) return '00:00'
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

// Check if transcript has segments structure
const hasSegments = (transcript: unknown): boolean => {
  return transcript != null && Array.isArray(transcript)
}

const loadAudioUrl = async () => {
  if (!props.lesson.hashid) { audioUrl.value = null; return }
  try {
    const data = await lessonsApi.getAudioUrl(props.lesson.hashid)
    audioUrl.value = data?.url ?? null
  } catch {
    audioUrl.value = null
  }
}

watch(() => props.lesson.hashid, () => { loadAudioUrl() }, { immediate: true })

// Play audio from specific timestamp
const playFromTimestamp = (startTime: number) => {
  if (!audioPlayer.value) return
  const audio = audioPlayer.value
  if (!audio.paused) audio.pause()

  const doSeekAndPlay = () => {
    if (isNaN(audio.duration) || audio.duration === 0) return
    if (startTime > audio.duration) return
    if (audio.seekable.length === 0) {
      audio.addEventListener('canplay', () => { doSeekAndPlay() }, { once: true })
      return
    }
    audio.addEventListener('seeked', () => {
      audio.play().then(() => { isPlaying.value = true }).catch(() => {})
    }, { once: true })
    audio.currentTime = startTime
  }

  if (audio.readyState >= 2) {
    doSeekAndPlay()
  } else {
    audio.addEventListener('canplay', () => { doSeekAndPlay() }, { once: true })
    if (audio.readyState === 0) audio.load()
  }
}

// Auto-play when requested by parent (e.g., Search results)
watch(
  () => props.autoplayFrom,
  (startTime) => {
    if (startTime === null || startTime === undefined) return
    nextTick(() => { playFromTimestamp(startTime) })
  },
  { immediate: true },
)

// Toggle play/pause
const togglePlayPause = () => {
  if (!audioPlayer.value) return
  if (isPlaying.value) {
    audioPlayer.value.pause()
    isPlaying.value = false
  } else {
    audioPlayer.value.play()
    isPlaying.value = true
  }
};

// Stop audio completely (pause + rewind to start)
const stopAudio = () => {
  if (!audioPlayer.value) return
  audioPlayer.value.pause()
  audioPlayer.value.currentTime = 0
  isPlaying.value = false
  currentTime.value = 0
};

// Update current time
const updateTime = () => {
  if (audioPlayer.value) currentTime.value = audioPlayer.value.currentTime
}

// Audio ended
const onAudioEnded = () => { isPlaying.value = false }

// Check if segment is currently playing
const isSegmentActive = (segment: { start: number; end: number }): boolean =>
  currentTime.value >= segment.start && currentTime.value <= segment.end

// Get currently active segment
const activeSegmentIndex = computed(() => {
  if (activeView.value !== 'transcript') return -1
  return unifiedTranscript.value.findIndex(
    (segment) => currentTime.value >= segment.start && currentTime.value <= segment.end,
  )
})

// Auto-scroll to active segment
watch(activeSegmentIndex, (newIndex) => {
  if (newIndex === -1 || !isPlaying.value) return
  nextTick(() => {
    const segmentElement = document.querySelector(`[data-segment-index="${newIndex}"]`)
    if (segmentElement) {
      segmentElement.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' })
    }
  })
})

const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return ''
  const date = new Date(dateString)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

const formatDuration = (seconds: number | null | undefined): string => {
  if (!seconds) return t('lessons.noDuration')
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

// Build a map of paragraph_index → LessonSource[] from the top-level sources array
const sourcesByParagraph = computed(() => {
  const map = new Map<number, LessonSource[]>()
  if (!props.lesson.sources) return map
  for (const s of props.lesson.sources) {
    if (!map.has(s.paragraph_index)) {
      map.set(s.paragraph_index, [])
    }
    map.get(s.paragraph_index)!.push(s)
  }
  return map
})

/** Return the sources for a given paragraph index from the lesson_source table. */
const getSourcesForParagraph = (paragraphIndex: number): LessonSource[] => {
  return sourcesByParagraph.value.get(paragraphIndex) ?? []
}

// Function to add source markers to edited text
const addSourceMarkers = (text: string, sources: Record<string, unknown>[], globalStartIndex = 0): string => {
  if (!sources || sources.length === 0) return text

  let markedText = text

  // Helper function to escape special regex characters
  const escapeRegex = (str: string) => str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  
  // Use cited_excerpt if available (preferred), otherwise fall back to translation_text or original_text
  const sourcesWithText = sources
    .map((source, idx) => {
      // Prefer cited_excerpt as it's the exact text from the edited version
      const sourceText = source.cited_excerpt || source.translation_text || source.original_text;
      if (!sourceText) return null;
      
      // Remove quotes if present (they might be added/removed during editing)
      const cleanSourceText = sourceText.replace(/^["'«»""]|["'«»""]$/g, '').trim();
      if (!cleanSourceText) return null;
      
      // Try case-insensitive search
      const escapedText = escapeRegex(cleanSourceText);
      const regex = new RegExp(escapedText, 'i');
      
      // Check if this text appears in the edited text (case-insensitive)
      if (regex.test(text)) {
        // Find the actual match (preserving original case)
        const match = text.match(regex);
        if (match) {
          return {
            source,
            text: match[0], // Use the actual matched text (preserves case)
            searchText: cleanSourceText,
            index: idx,
            length: cleanSourceText.length
          };
        }
      }
      return null;
    })
    .filter(item => item !== null);
  
  // Sort by text length (longest first) to avoid nested replacements
  sourcesWithText.sort((a, b) => b.length - a.length);
  
  sourcesWithText.forEach((item) => {
    const marker = globalStartIndex + item.index + 1;
    const matchedText = item.text; // Use the actual matched text from the edited text
    
    // Escape the matched text for safe replacement
    const escapedMatch = escapeRegex(matchedText);
    const regex = new RegExp(escapedMatch);
    
    // Create a highlighted version with superscript marker
    const highlighted = `<mark class="bg-yellow-100 dark:bg-yellow-900/30 dark:text-yellow-50 px-0.5 rounded">${matchedText}<sup class="text-indigo-600 dark:text-indigo-400 font-bold ml-0.5">[${marker}]</sup></mark>`;
    
    // Replace first occurrence (preserving case)
    markedText = markedText.replace(regex, highlighted);
  });
  
  return markedText;
};

// Function to highlight matched text in Sefaria text
const highlightMatchedText = (text: string, matchedText: string): string => {
  if (!text || !matchedText) return text
  const escapedMatch = matchedText.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(
    new RegExp(`(${escapedMatch})`, 'gi'),
    '<mark class="bg-yellow-200 dark:bg-yellow-800/50 dark:text-yellow-100 px-1 rounded font-medium">$1</mark>',
  )
}

// Collect all sources from lesson_source table, grouped by type
const allSources = computed(() => {
  if (!props.lesson.sources || props.lesson.sources.length === 0) return [];
  
  const typeMap = new Map();
  const edited = editedParts.value;
  
  props.lesson.sources.forEach((source) => {
    const type = source.type || 'Unknown';
    
    if (!typeMap.has(type)) {
      typeMap.set(type, []);
    }
    
    // Attach the corresponding edited paragraph for context
    const editedPart = edited[source.paragraph_index] ?? null;
    typeMap.get(type).push({
      ...source,
      editedPart
    });
  });
  
  // Convert to array of types with their sources, sorted by type name
  return Array.from(typeMap.entries())
    .map(([type, sources]) => ({ type, sources }))
    .sort((a, b) => a.type.localeCompare(b.type));
});

// Compute source statistics by type (from lesson_source table)
const sourceStats = computed(() => {
  if (!props.lesson.sources || props.lesson.sources.length === 0) return [];
  
  const typeStatsMap = new Map();
  
  props.lesson.sources.forEach((source) => {
    const type = source.type || 'Unknown';
    
    if (!typeStatsMap.has(type)) {
      typeStatsMap.set(type, {
        type,
        total: 0,
        slugRetrieved: 0,
        citationFound: 0,
        checked: 0 // verified with confidence > 90%
      });
    }
    
    const stats = typeStatsMap.get(type);
    stats.total++;
    
    if (source.slug_retrieved === true) {
      stats.slugRetrieved++;
    }
    
    // Citation found: FOUND, SIMILAR, or PARTIAL
    if (source.verification_status && 
        ['exactly_found', 'paraphrase_or_similar', 'partially_found'].includes(source.verification_status)) {
      stats.citationFound++;
    }
    
    // Checked: FOUND or SIMILAR AND verification confidence > 90%
    if (source.verification_status && 
        ['exactly_found', 'paraphrase_or_similar'].includes(source.verification_status) &&
        source.verification_confidence !== null && 
        source.verification_confidence > 0.9) {
      stats.checked++;
    }
  });
  
  // Convert to array and sort by type name
  return Array.from(typeStatsMap.values())
    .sort((a, b) => a.type.localeCompare(b.type));
});

// Total statistics across all types
const totalStats = computed(() => {
  return sourceStats.value.reduce((acc, stats) => {
    acc.total += stats.total;
    acc.slugRetrieved += stats.slugRetrieved;
    acc.citationFound += stats.citationFound;
    acc.checked += stats.checked;
    return acc;
  }, { total: 0, slugRetrieved: 0, citationFound: 0, checked: 0 });
});

// Compute global source indices for each part (uses lesson_source table data)
const getGlobalSourceIndex = (partIndex: number) => {
  let count = 0;
  for (let i = 0; i < partIndex; i++) {
    count += getSourcesForParagraph(i).length;
  }
  return count;
};

// Available views based on what data exists
const availableViews = computed(() => {
  const views = [];
  if (props.lesson.summary) {
    views.push({ key: 'summary', label: t('lessons.summary') });
  }
  if (props.lesson.edited_transcript) {
    views.push({ key: 'edited', label: t('lessons.editedTranscript') });
  }
  if (allSources.value.length > 0) {
    views.push({ key: 'sources', label: t('lessons.sources') });
  }
  if (props.lesson.transcript || props.lesson.corrected_transcript) {
    views.push({ key: 'transcript', label: t('lessons.transcript') });
  }
  if (canEditLesson.value) {
    views.push({ key: 'workflow', label: t('lessons.workflowHistory') })
  }
  return views;
});

// Unified transcript with correction information
const unifiedTranscript = computed(() => {
  const initialTranscript = props.lesson.transcript || [];
  const correctedTranscript = props.lesson.corrected_transcript || [];
  
  // If no initial transcript, return corrected or empty
  if (!initialTranscript.length) {
    return correctedTranscript.map((seg, index) => ({
      index,
      start: seg.start,
      end: seg.end,
      correctedText: seg.text,
      originalText: null,
      hasDiff: false
    }));
  }
  
  // Map segments with correction info
  return initialTranscript.map((seg, index) => {
    const correctedSeg = correctedTranscript[index];
    const originalText = seg.text;
    const correctedText = correctedSeg ? correctedSeg.text : originalText;
    const hasDiff = correctedSeg && originalText !== correctedText;
    
    return {
      index,
      start: seg.start,
      end: seg.end,
      correctedText,
      originalText: hasDiff ? originalText : null,
      hasDiff
    };
  });
});

// Set initial view to first available
if (availableViews.value.length > 0) {
  activeView.value = availableViews.value[0].key;
}

watch(activeView, (value) => {
  if (value === 'workflow') {
    loadWorkflowAudit()
  }
})

// Edit summary functions
const startEditSummary = () => {
  const baseSummary = props.lesson.summary || ''
  const draft = getDraftCandidate('summary', baseSummary)
  if (draft !== null) {
    startDraftRestoreFlow('summary', baseSummary, draft)
    return
  }
  openEditorWithValue('summary', baseSummary)
}

const cancelEditSummary = () => {
  clearDraftSaveTimeout('summary')
  isEditingSummary.value = false
  editedSummary.value = ''
}

const closeSummaryEditorPage = () => {
  if (isSavingSummary.value) return
  cancelEditSummary()
}

const saveSummary = async () => {
  if (isSavingSummary.value) return
  try {
    isSavingSummary.value = true
    const updated = await lessonsApi.update(props.lesson.hashid, { summary: editedSummary.value })
    Object.assign(props.lesson, updated)
    const realigned = await lessonsApi.realignSummary(props.lesson.hashid)
    Object.assign(props.lesson, realigned)
    isEditingSummary.value = false
    clearDraftFromStorage(getSummaryDraftStorageKey())
    clearDraftSaveTimeout('summary')
    editedSummary.value = ''
    toast.success(t('lessons.realignSummarySuccess'))
  } catch {
    toast.error(t('lessons.realignSummaryFailed'))
  } finally {
    isSavingSummary.value = false
  }
}

const startEditEditedMarkdown = () => {
  const baseEditedMarkdown = props.lesson.edited_transcript?.markdown || ''
  const draft = getDraftCandidate('edited', baseEditedMarkdown)
  if (draft !== null) {
    startDraftRestoreFlow('edited', baseEditedMarkdown, draft)
    return
  }
  openEditorWithValue('edited', baseEditedMarkdown)
}

const cancelEditEditedMarkdown = () => {
  if (isSavingEditedMarkdown.value) return
  clearDraftSaveTimeout('edited')
  isEditingEditedMarkdown.value = false
  editedMarkdownDraft.value = ''
}

const closeEditedMarkdownEditorPage = () => {
  if (isSavingEditedMarkdown.value) return
  cancelEditEditedMarkdown()
}

const saveEditedMarkdown = async () => {
  if (isSavingEditedMarkdown.value || !props.lesson.edited_transcript) return
  try {
    isSavingEditedMarkdown.value = true
    await lessonsApi.update(props.lesson.hashid, {
      edited_transcript: {
        ...props.lesson.edited_transcript,
        markdown: editedMarkdownDraft.value,
        markdown_hash: null,
        transcript_hash: null,
        aligned_at: null,
      },
    })
    const updated = await lessonsApi.realignEdited(props.lesson.hashid)
    Object.assign(props.lesson, updated)
    isEditingEditedMarkdown.value = false
    clearDraftFromStorage(getEditedDraftStorageKey())
    clearDraftSaveTimeout('edited')
    editedMarkdownDraft.value = ''
    toast.success(t('lessons.realignSuccess'))
  } catch {
    toast.error(t('lessons.realignFailed'))
  } finally {
    isSavingEditedMarkdown.value = false
  }
}

// Fetch text from backend Sefaria cache
const fetchSefariaText = async (slug: string) => {
  if (!slug) { sefariaTextEnglish.value = ''; sefariaTextHebrew.value = ''; return }
  try {
    isLoadingSefaria.value = true
    const entry = await sourcesApi.getSefariaCache(slug)
    sefariaTextEnglish.value = entry.text_english || ''
    sefariaTextHebrew.value = entry.text_hebrew || ''
  } catch (err) {
    const msg = `Error fetching cached text: ${err instanceof Error ? err.message : String(err)}`
    sefariaTextEnglish.value = msg
    sefariaTextHebrew.value = ''
  } finally {
    isLoadingSefaria.value = false
  }
}

/**
 * Split a text block into lines/sentences for interleaved display.
 * Sefaria stores paragraphs separated by newlines.
 */
const splitSefariaLines = (text: string): string[] => {
  if (!text) return []
  return text.split('\n').filter(line => line.trim() !== '')
}

/**
 * Build interleaved Hebrew + English pairs for side-by-side display.
 * Each pair is { he: string, en: string }.
 */
const sefariaInterleavedLines = computed(() => {
  const heLines = splitSefariaLines(sefariaTextHebrew.value)
  const enLines = splitSefariaLines(sefariaTextEnglish.value)
  const maxLen = Math.max(heLines.length, enLines.length)
  const pairs: Array<{ he: string; en: string }> = []
  for (let i = 0; i < maxLen; i++) {
    pairs.push({ he: heLines[i] || '', en: enLines[i] || '' })
  }
  return pairs
})

/** The text to display when a single language mode is selected. */
const sefariaDisplayText = computed(() => {
  if (sefariaDisplayMode.value === 'he') return sefariaTextHebrew.value || sefariaTextEnglish.value
  if (sefariaDisplayMode.value === 'en') return sefariaTextEnglish.value || sefariaTextHebrew.value
  return ''  // 'both' mode uses the interleaved view
})

const hasSefariaText = computed(() => !!(sefariaTextEnglish.value || sefariaTextHebrew.value))

// Open source modal with edited part text and source data
const openSourceModal = async (editedPart: { text: string }, source: Record<string, unknown>) => {
  selectedSourceEditedText.value = editedPart.text
  selectedSource.value = source
  sefariaTextEnglish.value = ''
  sefariaTextHebrew.value = ''
  if (source.standard_slug) await fetchSefariaText(source.standard_slug as string)
  showSourceModal.value = true
}

// Toggle transcript expander
const toggleTranscript = (index: number) => {
  expandedTranscriptIndex.value = expandedTranscriptIndex.value === index ? null : index
}

type IndexedTranscriptSegment = {
  index: number
  start: number
  end: number
  text: string
}

type EditedSideBySideRow = {
  key: string
  editedPart: (EditedPart & { index: number }) | null
  transcriptSegments: IndexedTranscriptSegment[]
  isUnmatchedTranscriptRow: boolean
}

const transcriptSegmentsForEditedView = computed<IndexedTranscriptSegment[]>(() => {
  const transcript = props.lesson.corrected_transcript ?? props.lesson.transcript ?? []
  return transcript.map((seg, index) => ({
    index,
    start: seg.start,
    end: seg.end,
    text: seg.text,
  }))
})

const editedSideBySideRows = computed<EditedSideBySideRow[]>(() => {
  const parts = editedParts.value.map((part, index) => ({ ...part, index }))
  const transcript = transcriptSegmentsForEditedView.value
  const alignment = Array.isArray(props.lesson.edited_transcript?.alignment)
    ? props.lesson.edited_transcript.alignment
    : []

  const rows: EditedSideBySideRow[] = []
  let nextTranscriptIndex = 0

  const pushUnmatchedRowsUntil = (targetExclusive: number) => {
    const limit = Math.min(Math.max(targetExclusive, 0), transcript.length)
    if (nextTranscriptIndex >= limit) return
    rows.push({
      key: `unmatched-${nextTranscriptIndex}-${limit - 1}`,
      editedPart: null,
      transcriptSegments: transcript.slice(nextTranscriptIndex, limit),
      isUnmatchedTranscriptRow: true,
    })
    nextTranscriptIndex = limit
  }

  parts.forEach((part) => {
    const row = alignment[part.index]
    const startIndex = typeof row?.start_index === 'number' ? row.start_index : null
    const endIndex = typeof row?.end_index === 'number' ? row.end_index : null
    const hasValidIndexRange = (
      startIndex !== null &&
      endIndex !== null &&
      startIndex >= 0 &&
      endIndex >= startIndex &&
      endIndex < transcript.length
    )

    if (hasValidIndexRange) {
      pushUnmatchedRowsUntil(startIndex as number)
      rows.push({
        key: `edited-${part.index}`,
        editedPart: part,
        transcriptSegments: transcript.slice(startIndex as number, (endIndex as number) + 1),
        isUnmatchedTranscriptRow: false,
      })
      nextTranscriptIndex = Math.max(nextTranscriptIndex, (endIndex as number) + 1)
      return
    }

    rows.push({
      key: `edited-unmapped-${part.index}`,
      editedPart: part,
      transcriptSegments: [],
      isUnmatchedTranscriptRow: false,
    })
  })

  pushUnmatchedRowsUntil(transcript.length)
  return rows
})

// Get transcript segments for an edited part
const getTranscriptSegments = (part: { start: number; end: number }) => {
  const transcript = props.lesson.corrected_transcript ?? props.lesson.transcript ?? []
  return transcript.filter(
    (seg) =>
      (seg.start >= part.start && seg.start < part.end) ||
      (seg.end > part.start && seg.end <= part.end) ||
      (seg.start <= part.start && seg.end >= part.end),
  )
}

// Check if an edited part is currently playing
const isEditedPartPlaying = (part: { start: number; end: number }): boolean =>
  isPlaying.value && currentTime.value >= part.start && currentTime.value < part.end

// Get currently active edited paragraph index (for auto-scroll)
const activeEditedParagraphIndex = computed(() => {
  if (activeView.value !== 'edited' || !isPlaying.value) return -1
  const parts = editedParts.value
  if (!parts) return -1
  return parts.findIndex(
    (part) => currentTime.value >= part.start && currentTime.value < part.end,
  )
})

// Auto-scroll to active edited paragraph
watch(activeEditedParagraphIndex, (newIndex) => {
  if (newIndex === -1 || !isPlaying.value) return
  nextTick(() => {
    const el = document.querySelector(`[data-paragraph-index="${newIndex}"]`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' })
    }
  })
})

// Toggle play/pause for edited part
const togglePlayEditedPart = (part: { start: number; end: number }) => {
  if (!audioPlayer.value) return
  if (isEditedPartPlaying(part)) {
    audioPlayer.value.pause()
    isPlaying.value = false
  } else {
    playFromTimestamp(part.start)
  }
}

// Download PDF helper
const triggerDownload = (blob: Blob, filename: string) => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
}

const openLessonDocumentModal = (mode: DocumentModalMode, view: LessonTabExportView) => {
  lessonDocumentMode.value = mode
  lessonDocumentView.value = view
  showLessonDocumentModal.value = true
}

const closeLessonDocumentModal = () => {
  if (isSubmittingLessonDocument.value) return
  showLessonDocumentModal.value = false
}

const tabExportType = computed(() => {
  if (lessonDocumentView.value === 'summary') return 'summary' as const
  if (lessonDocumentView.value === 'edited') return 'edited' as const
  return 'transcript' as const
})

const slugifyFilenamePart = (value: string | null | undefined): string => {
  const text = (value ?? '').trim().toLowerCase()
  if (!text) return 'untitled'
  const normalized = text
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return normalized || 'untitled'
}

const getExportTypeLabel = (exportType: 'summary' | 'edited' | 'transcript' | 'sources' | 'sources_detailed'): string => {
  if (exportType === 'summary') return t('lessons.summary')
  if (exportType === 'edited') return t('lessons.editedTranscript')
  if (exportType === 'transcript') return t('lessons.transcript')
  if (exportType === 'sources_detailed') return `${t('lessons.sources')} detailed`
  return t('lessons.sources')
}

const buildLessonExportFilename = (
  exportType: 'summary' | 'edited' | 'transcript' | 'sources' | 'sources_detailed',
  extension: LessonExportFormat,
): string => {
  const datePart = formatDate(props.lesson.date) || 'undated'
  const titlePart = slugifyFilenamePart(props.lesson.title)
  const exportTypePart = slugifyFilenamePart(getExportTypeLabel(exportType))
  return `${datePart}_${titlePart}_${exportTypePart}.${extension}`
}

const handleLessonExport = async (payload: { format: LessonExportFormat; includeFields: string[] }) => {
  if (isSubmittingLessonDocument.value) return
  try {
    isSubmittingLessonDocument.value = true
    const updatedPreferences: LessonExportPreferences = {
      format: payload.format,
      includeFields: [...payload.includeFields],
    }
    lessonExportPreferences.value = updatedPreferences
    saveLessonExportPreferences(updatedPreferences)
    const transcriptType = props.lesson.corrected_transcript ? 'corrected' : 'initial'
    const blob = await lessonsApi.exportDocument(props.lesson.hashid, tabExportType.value, {
      format: payload.format,
      include_fields: payload.includeFields,
      transcript_type: transcriptType,
      lang: locale.value,
    })
    const filename = buildLessonExportFilename(tabExportType.value, payload.format)
    triggerDownload(blob, filename)
    showLessonDocumentModal.value = false
  } catch {
    toast.error(t('lessons.exportFailed'))
  } finally {
    isSubmittingLessonDocument.value = false
  }
}

const handleLessonImport = async (payload: { file: File | null }) => {
  if (isSubmittingLessonDocument.value || !payload.file) return
  try {
    isSubmittingLessonDocument.value = true
    const updated = await lessonsApi.importDocument(
      props.lesson.hashid,
      tabExportType.value,
      payload.file,
    )
    Object.assign(props.lesson, updated)
    toast.success(t('lessons.importSuccess'))
    showLessonDocumentModal.value = false
  } catch {
    toast.error(t('lessons.importFailed'))
  } finally {
    isSubmittingLessonDocument.value = false
  }
}

const isRealigningEdited = ref(false)
const realignEditedMarkdown = async () => {
  if (isRealigningEdited.value || !canEditLesson.value || isProcessing.value) return
  try {
    isRealigningEdited.value = true
    const updated = await lessonsApi.realignEdited(props.lesson.hashid)
    Object.assign(props.lesson, updated)
    toast.success(t('lessons.realignSuccess'))
  } catch {
    toast.error(t('lessons.realignFailed'))
  } finally {
    isRealigningEdited.value = false
  }
}

const isRealigningSummary = ref(false)
const realignSummaryAlignment = async () => {
  if (isRealigningSummary.value || !canEditLesson.value || isProcessing.value) return
  try {
    isRealigningSummary.value = true
    const updated = await lessonsApi.realignSummary(props.lesson.hashid)
    Object.assign(props.lesson, updated)
    toast.success(t('lessons.realignSummarySuccess'))
  } catch {
    toast.error(t('lessons.realignSummaryFailed'))
  } finally {
    isRealigningSummary.value = false
  }
}

const downloadSourcesPDF = async () => {
  try {
    const blob = await lessonsApi.exportDocument(props.lesson.hashid, 'sources', {
      format: 'pdf',
      lang: locale.value,
    })
    triggerDownload(blob, buildLessonExportFilename('sources', 'pdf'))
  } catch {
    toast.error(t('lessons.downloadFailed'))
  }
}

const downloadDetailedSourcesPDF = async () => {
  try {
    const blob = await lessonsApi.exportDocument(props.lesson.hashid, 'sources_detailed', {
      format: 'pdf',
      lang: locale.value,
    })
    triggerDownload(blob, buildLessonExportFilename('sources_detailed', 'pdf'))
  } catch {
    toast.error(t('lessons.downloadFailed'))
  }
}

// Edit lesson functions
type CourseOption = {
  id: number
  label: string
}

const flattenCourseTree = (
  nodes: CourseTreeNode[],
  ancestors: string[] = [],
): CourseOption[] => {
  return nodes.flatMap((node) => {
    const path = [...ancestors, node.name]
    return [
      { id: node.id, label: path.join(' / ') },
      ...flattenCourseTree(node.children, path),
    ]
  })
}

const courseOptions = computed<CourseOption[]>(() => {
  if (courseTree.value.length > 0) {
    return flattenCourseTree(courseTree.value)
  }

  return [...courses.value]
    .sort((a, b) => a.sort_order - b.sort_order)
    .map((course) => ({ id: course.id, label: course.name }))
})

const fetchCourses = async () => {
  try { courses.value = await coursesApi.list() } catch { /* silent */ }
  try { courseTree.value = await coursesApi.tree() } catch { /* silent */ }
}

const courseById = computed<Map<number, Course>>(() => {
  const map = new Map<number, Course>()
  for (const course of courses.value) {
    map.set(course.id, course)
  }
  return map
})

const lessonCoursePath = computed<string | null>(() => {
  const lessonCourseId = props.lesson.course_id ?? props.lesson.course?.id ?? null
  if (!lessonCourseId) return null

  if (!courseById.value.size) {
    return props.lesson.course?.name ?? null
  }

  const path: string[] = []
  const visited = new Set<number>()
  let currentId: number | null = lessonCourseId

  while (currentId !== null && !visited.has(currentId)) {
    visited.add(currentId)
    const node = courseById.value.get(currentId)
    if (!node) break
    path.push(node.name)
    currentId = node.parent_id ?? null
  }

  if (path.length === 0) return props.lesson.course?.name ?? null
  return path.reverse().join(' / ')
})

watch(
  () => props.lesson.course_id,
  async (courseId) => {
    if (courseId && !courses.value.length) {
      await fetchCourses()
    }
  },
  { immediate: true },
)

const fetchThemes = async () => {
  try { themes.value = await themesApi.list() } catch { /* silent */ }
}

const fetchUsers = async () => {
  if (!['publisher', 'admin'].includes(role.value)) return
  try { users.value = await usersApi.list() } catch { /* silent */ }
}

watch(
  () => props.lesson.editors,
  (editors) => {
    if (editors?.length && !users.value.length) fetchUsers()
  },
  { immediate: true },
)

watch(
  editedSummary,
  (value) => {
    if (!isEditingSummary.value || isSavingSummary.value) return
    scheduleDraftSave('summary', value)
  },
)

watch(
  editedMarkdownDraft,
  (value) => {
    if (!isEditingEditedMarkdown.value || isSavingEditedMarkdown.value) return
    scheduleDraftSave('edited', value)
  },
)

const getUserName = (userId: string, fallbackName?: string | null) => {
  if (fallbackName?.trim()) return fallbackName.trim()
  const u = users.value.find((u) => u.id === userId)
  if (u) {
    const name = [u.first_name, u.last_name].filter(Boolean).join(' ')
    return name || u.username || u.email || userId
  }
  // Editors cannot access /users, so fall back to the signed-in Clerk profile
  // for their own assignment chip instead of showing the raw Clerk ID.
  if (user.value?.id === userId) {
    const ownName = [user.value.firstName, user.value.lastName].filter(Boolean).join(' ')
    const ownEmail = user.value.primaryEmailAddress?.emailAddress ?? null
    return ownName || user.value.username || ownEmail || userId
  }
  return userId
}

const openHistory = (contentType: ContentType) => {
  historyContentType.value = contentType
  historySelectedVersionId.value = null
  historyActiveCompare.value = null
  window.history.pushState(
    { hashid: props.lesson.hashid, history: { contentType } },
    '',
    `/lessons/${props.lesson.hashid}/${contentType}/history`,
  )
}

const closeHistoryMode = () => {
  historyContentType.value = null
  historySelectedVersionId.value = null
  historyActiveCompare.value = null
  window.history.pushState(
    { hashid: props.lesson.hashid },
    '',
    `/lessons/${props.lesson.hashid}`,
  )
}

const onHistoryVersionChange = (versionId: string | null) => {
  if (historySelectedVersionId.value === versionId) return
  if (!historyContentType.value) return
  historySelectedVersionId.value = versionId
  historyActiveCompare.value = null
  const query = new URLSearchParams()
  if (versionId) query.set('version', versionId)
  const search = query.toString() ? `?${query.toString()}` : ''
  window.history.pushState(
    { hashid: props.lesson.hashid, history: { contentType: historyContentType.value, versionId } },
    '',
    `/lessons/${props.lesson.hashid}/${historyContentType.value}/history${search}`,
  )
}

const onHistoryCompareChange = (
  compare: {
    versionAId: string
    versionBId: string
    fromVersionNumber?: number | null
    toVersionNumber?: number | null
  } | null,
) => {
  if (!historyContentType.value) return
  historyActiveCompare.value = compare
  const query = new URLSearchParams()
  if (historySelectedVersionId.value) query.set('version', historySelectedVersionId.value)
  if (compare) query.set('compare', `${compare.versionAId},${compare.versionBId}`)
  const search = query.toString() ? `?${query.toString()}` : ''
  window.history.pushState(
    {
      hashid: props.lesson.hashid,
      history: {
        contentType: historyContentType.value,
        versionId: historySelectedVersionId.value,
        compare,
      },
    },
    '',
    `/lessons/${props.lesson.hashid}/${historyContentType.value}/history${search}`,
  )
}

watch(
  () => [props.initialHistoryContentType, props.initialHistoryVersionId, props.initialHistoryCompare] as const,
  ([contentType, versionId, compare]) => {
    historyContentType.value = contentType ?? null
    historySelectedVersionId.value = versionId ?? null
    historyActiveCompare.value = compare ?? null
  },
  { immediate: true },
)

const loadWorkflowAudit = async () => {
  workflowAuditLoading.value = true
  try {
    if (!users.value.length) await fetchUsers()
    const rows = await lessonsApi.getLessonAuditLog(props.lesson.hashid, { limit: 100 })
    // Show the full lesson timeline returned by backend.
    // (status transitions, creation/deletion, content version events, restores, etc.)
    workflowAuditLog.value = rows
  } catch {
    workflowAuditLog.value = []
  } finally {
    workflowAuditLoading.value = false
  }
}

const workflowActorName = (actorId: string | null) => {
  if (!actorId) return t('audit.system')
  return getUserName(actorId)
}

const workflowActorRole = (role: string | null) => {
  if (!role) return t('audit.system')
  if (role === 'pipeline') return t('history.pipeline')
  return role
}

const workflowActionLabel = (action: string) => {
  const key = `audit.actions.${action.replace(/\./g, '_')}`
  const translated = t(key)
  return translated === key ? action : translated
}

const toggleWorkflowPayload = (id: number) => {
  if (workflowExpandedPayload.value.has(id)) {
    workflowExpandedPayload.value.delete(id)
  } else {
    workflowExpandedPayload.value.add(id)
  }
}

const startEditLesson = async () => {
  if (!courses.value.length) await fetchCourses()
  if (!themes.value.length) await fetchThemes()
  if (!users.value.length) await fetchUsers()
  editedLesson.value = {
    title: props.lesson.title,
    date: props.lesson.date ? new Date(props.lesson.date).toISOString().slice(0, 10) : '',
    course_id: props.lesson.course_id ?? null,
    theme_ids: props.lesson.theme_ids ?? [],
    editor_ids: props.lesson.editors?.map((e) => e.user_id) ?? [],
    brief: props.lesson.brief ?? '',
  }
  isEditingLesson.value = true
}

const cancelEditLesson = () => { isEditingLesson.value = false }

const saveLesson = async () => {
  if (isSavingLesson.value) return
  try {
    isSavingLesson.value = true
    const updated = await lessonsApi.update(props.lesson.hashid, {
      title: editedLesson.value.title,
      date: editedLesson.value.date ? new Date(editedLesson.value.date).toISOString() : null,
      course_id: editedLesson.value.course_id,
      theme_ids: editedLesson.value.theme_ids,
      editor_ids: editedLesson.value.editor_ids,
      brief: editedLesson.value.brief || null,
    })
    Object.assign(props.lesson, updated)
    isEditingLesson.value = false
  } catch {
    toast.error(t('lessons.saveFailed'))
  } finally {
    isSavingLesson.value = false
  }
}

const toggleTheme = (themeId: number) => {
  const index = editedLesson.value.theme_ids.indexOf(themeId)
  if (index === -1) {
    editedLesson.value.theme_ids.push(themeId)
  } else {
    editedLesson.value.theme_ids.splice(index, 1)
  }
}

const toggleEditor = (userId: string) => {
  const index = editedLesson.value.editor_ids.indexOf(userId)
  if (index === -1) {
    editedLesson.value.editor_ids.push(userId)
  } else {
    editedLesson.value.editor_ids.splice(index, 1)
  }
}

const editorRoleUsers = computed(() =>
  users.value.filter((u) => u.role && ['editor', 'publisher', 'admin'].includes(u.role))
)

// Delete lesson functions
const confirmDelete = () => { showDeleteConfirm.value = true }
const cancelDelete = () => { showDeleteConfirm.value = false }

const deleteLesson = async () => {
  try {
    isDeleting.value = true
    await lessonsApi.delete(props.lesson.hashid)
    showDeleteConfirm.value = false
    emit('close')
  } catch {
    toast.error(t('lessons.deleteFailed'))
  } finally {
    isDeleting.value = false
  }
}

// Process option availability: depends on existing data + selected options
const hasTranscript = computed(() => !!(props.lesson.transcript && props.lesson.transcript.length > 0))
const hasCorrectedTranscript = computed(() => !!(props.lesson.corrected_transcript && props.lesson.corrected_transcript.length > 0))
const hasEditedTranscript = computed(() => editedParts.value.length > 0)
const hasSourcesExtracted = computed(() => {
  return !!(props.lesson.sources && props.lesson.sources.length > 0)
})

const WORKFLOW_STEPS: LessonWorkflowStep[] = [
  'transcription',
  'edited',
  'sources',
  'summary',
  'brief',
]
const DEFAULT_STEP_STATUS: LessonWorkflowStepStatus = 'non_started'
const USER_EDITABLE_STEP_STATUSES: LessonWorkflowStepStatus[] = ['in_progress', 'completed', 'validated']
const STEP_STATUS_VALUES: LessonWorkflowStepStatus[] = [
  'non_started',
  'failed',
  'to_review',
  'in_progress',
  'completed',
  'validated',
]

const normalizedStepStatuses = computed<Record<LessonWorkflowStep, LessonWorkflowStepStatus>>(() => {
  const raw = (props.lesson.step_statuses ?? {}) as Record<string, unknown>
  const statuses = WORKFLOW_STEPS.reduce((acc, step) => {
    const candidate = raw[step]
    acc[step] = (
      typeof candidate === 'string' && STEP_STATUS_VALUES.includes(candidate as LessonWorkflowStepStatus)
        ? candidate
        : DEFAULT_STEP_STATUS
    ) as LessonWorkflowStepStatus
    return acc
  }, {} as Record<LessonWorkflowStep, LessonWorkflowStepStatus>)

  // Frontend safety net: support legacy keys and infer from visible content.
  const legacyEdited = raw.edited ?? raw.edition ?? raw.correction
  if (
    statuses.edited === 'non_started'
    && typeof legacyEdited === 'string'
    && STEP_STATUS_VALUES.includes(legacyEdited as LessonWorkflowStepStatus)
  ) {
    statuses.edited = legacyEdited as LessonWorkflowStepStatus
  }
  if (
    statuses.edited === 'non_started'
    && (
      hasEditedTranscript.value
      || hasCorrectedTranscript.value
      || !!props.lesson.summary
      || !!props.lesson.brief
      || ['edition', 'sources_extraction', 'sources_checking', 'summary'].includes(props.lesson.process_status || '')
    )
  ) {
    statuses.edited = 'in_progress'
  }

  const legacySources = raw.sources ?? raw.extraction
  if (
    statuses.sources === 'non_started'
    && typeof legacySources === 'string'
    && STEP_STATUS_VALUES.includes(legacySources as LessonWorkflowStepStatus)
  ) {
    statuses.sources = legacySources as LessonWorkflowStepStatus
  }
  if (statuses.sources === 'non_started' && hasSourcesExtracted.value) {
    statuses.sources = 'in_progress'
  }

  return statuses
})

const pipelineSteps = computed(() =>
  WORKFLOW_STEPS.map((key) => ({ key, status: normalizedStepStatuses.value[key] })),
)

const stepStatusBadgeClass = (status: LessonWorkflowStepStatus): string => {
  switch (status) {
    case 'validated':
    case 'completed':
      return 'bg-emerald-50 text-emerald-700 border-emerald-100 dark:bg-emerald-900/30 dark:text-emerald-300 dark:border-emerald-800'
    case 'to_review':
      return 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:border-amber-800'
    case 'failed':
      return 'bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/30 dark:text-rose-300 dark:border-rose-800'
    case 'in_progress':
      return 'bg-indigo-50 text-indigo-700 border-indigo-100 dark:bg-indigo-900/30 dark:text-indigo-300 dark:border-indigo-800'
    default:
      return 'bg-slate-50 text-slate-600 border-slate-200 dark:bg-slate-800/60 dark:text-slate-300 dark:border-slate-700'
  }
}

const isUpdatingStepStatus = ref(false)
const updateStepStatus = async (step: LessonWorkflowStep, status: LessonWorkflowStepStatus) => {
  if (!USER_EDITABLE_STEP_STATUSES.includes(status)) return
  try {
    isUpdatingStepStatus.value = true
    const updated = await lessonsApi.updateStepStatus(props.lesson.hashid, step, status)
    Object.assign(props.lesson, updated)
    toast.success(t('lessons.stepStatusUpdated'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t('lessons.stepStatusUpdateFailed'))
  } finally {
    isUpdatingStepStatus.value = false
  }
}
const onStepStatusSelection = (step: LessonWorkflowStep, event: Event) => {
  const value = (event.target as HTMLSelectElement | null)?.value as LessonWorkflowStepStatus | undefined
  if (!value) return
  updateStepStatus(step, value)
}

// Status transitions
const TRANSITIONS: Record<string, Record<string, string[]>> = {
  draft:              { in_progress:       ['editor', 'publisher', 'admin'] },
  in_progress:        { review_requested:  ['editor', 'publisher', 'admin'] },
  review_requested:   { validated:         ['publisher', 'admin'],
                        revision_requested:['publisher', 'admin'] },
  revision_requested: { in_progress:       ['editor', 'publisher', 'admin'] },
  validated:          { in_progress:       ['admin'] },
}
const LESSON_STATUS_VALUES: LessonStatus[] = [
  'draft',
  'in_progress',
  'review_requested',
  'revision_requested',
  'validated',
]

const availableTransitions = computed(() => {
  const current = props.lesson.status || 'draft'
  const transitions = TRANSITIONS[current] || {}
  return Object.entries(transitions)
    .filter(([_, roles]) => roles.includes(role.value))
    .map(([target]) => target as LessonStatus)
})
const isStatusSelectable = (target: LessonStatus): boolean => {
  const current = props.lesson.status || 'draft'
  if (target === current) return true
  return availableTransitions.value.includes(target)
}

const isUpdatingStatus = ref(false)
const lessonStatusVisual = computed<LessonWorkflowStepStatus>(() => {
  const current = props.lesson.status || 'draft'
  switch (current) {
    case 'in_progress':
      return 'in_progress'
    case 'review_requested':
    case 'revision_requested':
      return 'to_review'
    case 'validated':
      return 'completed'
    default:
      return 'non_started'
  }
})

const updateStatus = async (newStatus: LessonStatus) => {
  try {
    isUpdatingStatus.value = true
    const updated = await lessonsApi.updateStatus(props.lesson.hashid, newStatus)
    Object.assign(props.lesson, updated)
    toast.success(t('lessons.statusUpdated'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail || t('lessons.statusUpdateFailed'))
  } finally {
    isUpdatingStatus.value = false
  }
}

const onLessonStatusSelection = (event: Event) => {
  const target = (event.target as HTMLSelectElement | null)?.value as LessonStatus | undefined
  const current = props.lesson.status || 'draft'
  if (!target || target === current) return
  if (!availableTransitions.value.includes(target)) return
  updateStatus(target)
}

const canCorrect = computed(() => hasTranscript.value || selectedProcesses.value.transcribe)
const canEdition = computed(() => hasCorrectedTranscript.value || selectedProcesses.value.correct)
const canExtraction = computed(() => hasEditedTranscript.value || selectedProcesses.value.edition)
const canSources = computed(() => hasSourcesExtracted.value || selectedProcesses.value.extraction)
const canSummary = computed(() => hasEditedTranscript.value || selectedProcesses.value.edition)
const canBrief = computed(() => !!props.lesson.summary || selectedProcesses.value.summary)

// Uncheck options that become disabled
watch([canCorrect, canEdition, canExtraction, canSources, canSummary, canBrief], () => {
  if (!canCorrect.value) selectedProcesses.value.correct = false
  if (!canEdition.value) selectedProcesses.value.edition = false
  if (!canExtraction.value) selectedProcesses.value.extraction = false
  if (!canSources.value) selectedProcesses.value.sources = false
  if (!canSummary.value) selectedProcesses.value.summary = false
  if (!canBrief.value) selectedProcesses.value.brief = false
})

// Process tasks modal functions
const openProcessModal = async () => {
  selectedProcesses.value = {
    transcribe: false, correct: false, edition: false, extraction: false, summary: false, brief: false, sources: false,
  }
  showProcessModal.value = true
  try {
    const config = await configApi.get()

    const loadPrompts = (
      section: { prompts?: Array<{ name: string; text: string }>; prompt?: string },
      availableRef: typeof availableSummaryPrompts,
      selectedRef: typeof selectedSummaryPrompt,
    ) => {
      let prompts = section?.prompts ?? []
      if (prompts.length === 0 && section?.prompt) {
        prompts = [{ name: 'Default', text: section.prompt }]
      }
      availableRef.value = prompts
      if (prompts.length > 0 && !selectedRef.value) {
        selectedRef.value = prompts[0].name
      }
    }

    loadPrompts(config?.summary, availableSummaryPrompts, selectedSummaryPrompt)
    loadPrompts(config?.correction, availableCorrectionPrompts, selectedCorrectionPrompt)
    loadPrompts(config?.edition, availableEditionPrompts, selectedEditionPrompt)
    loadPrompts(config?.extraction, availableExtractionPrompts, selectedExtractionPrompt)
    loadPrompts(config?.sources, availableSourcesPrompts, selectedSourcesPrompt)
  } catch { /* silent */ }
}

const closeProcessModal = () => { showProcessModal.value = false }

const selectAllRemaining = () => {
  // Select all steps that haven't been completed yet
  if (!hasTranscript.value) selectedProcesses.value.transcribe = true
  if (!hasCorrectedTranscript.value) selectedProcesses.value.correct = true
  if (!hasEditedTranscript.value) selectedProcesses.value.edition = true
  if (!hasSourcesExtracted.value) selectedProcesses.value.extraction = true
  // Sources checking can always be re-run, select if extraction will be done or sources exist
  if (canSources.value) selectedProcesses.value.sources = true
  if (!props.lesson.summary) selectedProcesses.value.summary = true
  if (!props.lesson.brief) selectedProcesses.value.brief = true
}

const createTasks = async () => {
  const selectedTasks = Object.keys(selectedProcesses.value).filter((k) => selectedProcesses.value[k])
  if (selectedTasks.length === 0) {
    toast.error(t('lessons.selectAtLeastOneProcess'))
    return
  }
  try {
    isCreatingTasks.value = true
    const taskOrder = ['transcribe', 'correct', 'edition', 'extraction', 'summary', 'brief', 'sources']
    const orderedTasks = taskOrder.filter((t) => selectedTasks.includes(t))
    const taskTypeMap: Record<string, string> = {
      transcribe: 'transcription', correct: 'correction', edition: 'edition',
      extraction: 'extraction', summary: 'summary', brief: 'brief', sources: 'sources',
    }
    for (const taskType of orderedTasks) {
      const parameters: Record<string, unknown> = { lesson_id: props.lesson.id }
      if (taskType === 'correct')    { parameters.segments_per_group = 100; parameters.max_concurrency = 10; parameters.prompt_type = selectedCorrectionPrompt.value }
      if (taskType === 'edition')    { parameters.words_per_group = 1000; parameters.max_concurrency = 10; parameters.prompt_type = selectedEditionPrompt.value }
      if (taskType === 'extraction') { parameters.max_concurrency = 10; parameters.prompt_type = selectedExtractionPrompt.value }
      if (taskType === 'summary')    { parameters.prompt_type = selectedSummaryPrompt.value }
      if (taskType === 'sources')    { parameters.prompt_type = selectedSourcesPrompt.value }
      await tasksApi.create({ task_type: taskTypeMap[taskType] as import('@/api/types').TaskType, parameters })
    }
    toast.success(t('lessons.tasksCreated', { count: orderedTasks.length }))
    closeProcessModal()
    // Start polling — flag that we're waiting for the worker to pick up the tasks
    awaitingProcessing = true
    startPolling()
  } catch {
    toast.error(t('lessons.tasksCreationFailed'))
  } finally {
    isCreatingTasks.value = false
  }
}

// Edit segment functions
const startEditSegment = (index: number, currentText: string) => {
  editingSegmentIndex.value = index
  editedSegmentText.value = currentText
}

const cancelEditSegment = () => {
  editingSegmentIndex.value = null
  editedSegmentText.value = ''
}

const saveSegment = async () => {
  if (isSavingSegment.value || editingSegmentIndex.value === null) return
  try {
    isSavingSegment.value = true
    const hasCorrected = !!(props.lesson.corrected_transcript?.length)
    if (!hasCorrected) {
      toast.error('Please run correction first. Raw transcript is not versioned/audited.')
      return
    }
    const segments = [...(props.lesson.corrected_transcript ?? [])]
    if (editingSegmentIndex.value < segments.length) {
      segments[editingSegmentIndex.value] = {
        ...segments[editingSegmentIndex.value],
        text: editedSegmentText.value,
      }
      const updated = await lessonsApi.update(props.lesson.hashid, {
        corrected_transcript: segments,
      })
      Object.assign(props.lesson, updated)
      editingSegmentIndex.value = null
      editedSegmentText.value = ''
    }
  } catch {
    toast.error(t('lessons.saveFailed'))
  } finally {
    isSavingSegment.value = false
  }
}

// Edit edited-paragraph functions
const startEditParagraph = (index: number, currentText: string) => {
  editingParagraphIndex.value = index
  editedParagraphText.value = currentText
}

const cancelEditParagraph = () => {
  editingParagraphIndex.value = null
  editedParagraphText.value = ''
}

const saveParagraph = async () => {
  if (isSavingParagraph.value || editingParagraphIndex.value === null) return
  if (!props.lesson.edited_transcript) return
  try {
    isSavingParagraph.value = true
    const paragraphs = [...editedParts.value]
    if (editingParagraphIndex.value < paragraphs.length) {
      paragraphs[editingParagraphIndex.value] = {
        ...paragraphs[editingParagraphIndex.value],
        text: editedParagraphText.value,
      }
      const markdown = paragraphs.map((p) => p.text.trim()).filter(Boolean).join('\n\n')
      const updated = await lessonsApi.update(props.lesson.hashid, {
        edited_transcript: {
          ...props.lesson.edited_transcript,
          markdown,
          markdown_hash: null,
          aligned_at: null,
        },
      })
      Object.assign(props.lesson, updated)
      editingParagraphIndex.value = null
      editedParagraphText.value = ''
    }
  } catch {
    toast.error(t('lessons.saveFailed'))
  } finally {
    isSavingParagraph.value = false
  }
}
</script>

<template>
  <!-- Delete Confirmation Dialog -->
  <Dialog :open="showDeleteConfirm" @close="cancelDelete" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-4xl w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6 max-h-[85vh] overflow-y-auto">
          <div class="flex items-center gap-4 mb-4">
            <div class="flex-shrink-0 w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <ExclamationTriangleIcon class="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
                {{ t('lessons.deleteConfirmTitle') }}
              </DialogTitle>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {{ t('lessons.deleteConfirmMessage') }}
              </p>
            </div>
          </div>
          
          <p class="text-sm text-gray-700 dark:text-gray-300 mb-6 pl-16">
            <strong>{{ lesson.title }}</strong>
          </p>
          
          <div class="flex justify-end gap-3">
            <button
              @click="cancelDelete"
              :disabled="isDeleting"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('lessons.cancel') }}
            </button>
            <button
              @click="deleteLesson"
              :disabled="isDeleting"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 rounded-md transition-colors"
            >
              <TrashIcon class="h-4 w-4" />
              {{ isDeleting ? t('lessons.deleting') : t('lessons.deleteConfirm') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Process Tasks Modal -->
  <Dialog :open="showProcessModal" @close="closeProcessModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="w-[min(96vw,1100px)] bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-5 md:p-6 max-h-[85vh] overflow-y-auto">
          <div class="flex items-start justify-between gap-4 mb-6">
            <div class="flex items-center gap-4 min-w-0">
              <div class="flex-shrink-0 w-12 h-12 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
                <CogIcon class="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
              </div>
              <div>
                <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
                  {{ t('lessons.processLessonTitle') }}
                </DialogTitle>
                <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                  {{ t('lessons.processLessonDescription') }}
                </p>
              </div>
            </div>
            <button
              @click="selectAllRemaining"
              class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 hover:bg-indigo-100 dark:hover:bg-indigo-900/40 rounded-md transition-colors flex-shrink-0"
            >
              <CheckIcon class="h-3.5 w-3.5" />
              {{ t('lessons.selectAllRemaining') }}
            </button>
          </div>

          <!-- Process Selection -->
          <div class="space-y-2 mb-6">
            <!-- Transcribe (always available) -->
            <label class="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors">
              <input
                type="checkbox"
                v-model="selectedProcesses.transcribe"
                class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
              />
              <div>
                <div class="text-sm font-medium text-gray-900 dark:text-white">
                  {{ t('lessons.processTranscribe') }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">
                  {{ t('lessons.processTranscribeDesc') }}
                </div>
              </div>
            </label>
            
            <!-- Correct (needs transcript) -->
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] gap-3 items-start">
              <label :class="[
                'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                canCorrect
                  ? 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
                  : 'border-gray-100 dark:border-gray-800 opacity-50 cursor-not-allowed'
              ]">
                <input
                  type="checkbox"
                  v-model="selectedProcesses.correct"
                  :disabled="!canCorrect"
                  class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 disabled:opacity-50"
                />
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">
                    {{ t('lessons.processCorrect') }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">
                    {{ t('lessons.processCorrectDesc') }}
                  </div>
                </div>
              </label>
              <div v-if="selectedProcesses.correct && availableCorrectionPrompts.length > 0">
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {{ t('lessons.correctionPromptType') }}
                </label>
                <select
                  v-model="selectedCorrectionPrompt"
                  class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                >
                  <option
                    v-for="prompt in availableCorrectionPrompts"
                    :key="prompt.name"
                    :value="prompt.name"
                  >
                    {{ prompt.name }}
                  </option>
                </select>
              </div>
            </div>
            
            <!-- Edition (needs corrected transcript) -->
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] gap-3 items-start">
              <label :class="[
                'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                canEdition
                  ? 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
                  : 'border-gray-100 dark:border-gray-800 opacity-50 cursor-not-allowed'
              ]">
                <input
                  type="checkbox"
                  v-model="selectedProcesses.edition"
                  :disabled="!canEdition"
                  class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 disabled:opacity-50"
                />
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">
                    {{ t('lessons.processEdition') }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">
                    {{ t('lessons.processEditionDesc') }}
                  </div>
                </div>
              </label>
              <div v-if="selectedProcesses.edition && availableEditionPrompts.length > 0">
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {{ t('lessons.editionPromptType') }}
                </label>
                <select
                  v-model="selectedEditionPrompt"
                  class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                >
                  <option
                    v-for="prompt in availableEditionPrompts"
                    :key="prompt.name"
                    :value="prompt.name"
                  >
                    {{ prompt.name }}
                  </option>
                </select>
              </div>
            </div>
            
            <!-- Extract sources (needs edited transcript) -->
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] gap-3 items-start">
              <label :class="[
                'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                canExtraction
                  ? 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
                  : 'border-gray-100 dark:border-gray-800 opacity-50 cursor-not-allowed'
              ]">
                <input
                  type="checkbox"
                  v-model="selectedProcesses.extraction"
                  :disabled="!canExtraction"
                  class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 disabled:opacity-50"
                />
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">
                    {{ t('lessons.processExtraction') }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">
                    {{ t('lessons.processExtractionDesc') }}
                  </div>
                </div>
              </label>
              <div v-if="selectedProcesses.extraction && availableExtractionPrompts.length > 0">
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {{ t('lessons.extractionPromptType') }}
                </label>
                <select
                  v-model="selectedExtractionPrompt"
                  class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                >
                  <option
                    v-for="prompt in availableExtractionPrompts"
                    :key="prompt.name"
                    :value="prompt.name"
                  >
                    {{ prompt.name }}
                  </option>
                </select>
              </div>
            </div>

            <!-- Verify sources (needs sources extracted) -->
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] gap-3 items-start">
              <label :class="[
                'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                canSources
                  ? 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
                  : 'border-gray-100 dark:border-gray-800 opacity-50 cursor-not-allowed'
              ]">
                <input
                  type="checkbox"
                  v-model="selectedProcesses.sources"
                  :disabled="!canSources"
                  class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 disabled:opacity-50"
                />
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">
                    {{ t('lessons.processSources') }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">
                    {{ t('lessons.processSourcesDesc') }}
                  </div>
                </div>
              </label>
              <div v-if="selectedProcesses.sources && availableSourcesPrompts.length > 0">
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {{ t('lessons.sourcesPromptType') }}
                </label>
                <select
                  v-model="selectedSourcesPrompt"
                  class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                >
                  <option
                    v-for="prompt in availableSourcesPrompts"
                    :key="prompt.name"
                    :value="prompt.name"
                  >
                    {{ prompt.name }}
                  </option>
                </select>
              </div>
            </div>

            <!-- Summary (needs edited transcript) -->
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] gap-3 items-start">
              <label :class="[
                'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                canSummary
                  ? 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
                  : 'border-gray-100 dark:border-gray-800 opacity-50 cursor-not-allowed'
              ]">
                <input
                  type="checkbox"
                  v-model="selectedProcesses.summary"
                  :disabled="!canSummary"
                  class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 disabled:opacity-50"
                />
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">
                    {{ t('lessons.processSummary') }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">
                    {{ t('lessons.processSummaryDesc') }}
                  </div>
                </div>
              </label>
              <div v-if="selectedProcesses.summary && availableSummaryPrompts.length > 0">
                <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
                  {{ t('lessons.summaryPromptType') }}
                </label>
                <select
                  v-model="selectedSummaryPrompt"
                  class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                >
                  <option
                    v-for="prompt in availableSummaryPrompts"
                    :key="prompt.name"
                    :value="prompt.name"
                  >
                    {{ prompt.name }}
                  </option>
                </select>
              </div>
            </div>

            <!-- Brief (needs summary) -->
            <div class="grid grid-cols-1 md:grid-cols-[minmax(0,1fr)_minmax(16rem,20rem)] gap-3 items-start">
              <label :class="[
                'flex items-center gap-3 p-3 rounded-lg border transition-colors',
                canBrief
                  ? 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer'
                  : 'border-gray-100 dark:border-gray-800 opacity-50 cursor-not-allowed'
              ]">
                <input
                  type="checkbox"
                  v-model="selectedProcesses.brief"
                  :disabled="!canBrief"
                  class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500 disabled:opacity-50"
                />
                <div class="flex-1">
                  <div class="text-sm font-medium text-gray-900 dark:text-white">
                    {{ t('lessons.processBrief') }}
                  </div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">
                    {{ t('lessons.processBriefDesc') }}
                  </div>
                </div>
              </label>
            </div>
          </div>
          
          <!-- Action Buttons -->
          <div class="flex justify-end gap-3">
            <button
              @click="closeProcessModal"
              :disabled="isCreatingTasks"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('lessons.cancel') }}
            </button>
            <button
              @click="createTasks"
              :disabled="isCreatingTasks"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CogIcon class="h-4 w-4" />
              {{ isCreatingTasks ? t('lessons.creating') : t('lessons.createTasks') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Edit Lesson Modal -->
  <Dialog :open="isEditingLesson" @close="cancelEditLesson" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />

    <div class="fixed inset-0 flex items-start justify-center p-3 sm:p-4 overflow-y-auto">
      <DialogPanel class="mx-auto my-4 sm:my-8 w-full max-w-5xl max-h-[92vh] bg-white dark:bg-gray-800 rounded-lg shadow-xl flex flex-col overflow-hidden">
        <div class="p-6 overflow-y-auto">
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ t('lessons.modifySession') }}
          </DialogTitle>

          <div class="grid grid-cols-1 xl:grid-cols-2 gap-6 xl:gap-8">
            <div class="space-y-4">
              <!-- Title -->
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('lessons.lessonTitle') }}
                </label>
                <input
                  v-model="editedLesson.title"
                  type="text"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>

              <!-- Date -->
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('lessons.date') }}
                </label>
                <input
                  v-model="editedLesson.date"
                  type="date"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                />
              </div>

              <!-- Brief -->
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('lessons.brief') }}
                </label>
                <textarea
                  v-model="editedLesson.brief"
                  :placeholder="t('lessons.briefPlaceholder')"
                  rows="5"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                ></textarea>
              </div>
            </div>

            <div class="space-y-4">
              <!-- Course -->
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('lessons.course') }}
                </label>
                <select
                  v-model="editedLesson.course_id"
                  class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                >
                  <option :value="null">{{ t('lessons.noCourse') }}</option>
                  <option v-for="course in courseOptions" :key="course.id" :value="course.id">
                    {{ course.label }}
                  </option>
                </select>
              </div>

              <!-- Themes -->
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('lessons.themes') }}
                </label>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="theme in themes"
                    :key="theme.id"
                    @click="toggleTheme(theme.id)"
                    :class="[
                      'px-3 py-1.5 rounded-full text-sm font-medium transition-colors',
                      editedLesson.theme_ids.includes(theme.id)
                        ? 'bg-indigo-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    ]"
                  >
                    {{ theme.name }}
                  </button>
                </div>
              </div>

              <!-- Editors -->
              <div>
                <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  {{ t('lessons.editors') }}
                </label>
                <div class="flex flex-wrap gap-2">
                  <button
                    v-for="user in editorRoleUsers"
                    :key="user.id"
                    @click="toggleEditor(user.id)"
                    :class="[
                      'px-3 py-1.5 rounded-full text-sm font-medium transition-colors',
                      editedLesson.editor_ids.includes(user.id)
                        ? 'bg-sky-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                    ]"
                  >
                    {{ [user.first_name, user.last_name].filter(Boolean).join(' ') || user.email || user.id }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-end gap-3 pt-6">
            <button
              @click="cancelEditLesson"
              :disabled="isSavingLesson"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('lessons.cancel') }}
            </button>
            <button
              @click="saveLesson"
              :disabled="isSavingLesson"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CheckIcon class="h-4 w-4" />
              {{ isSavingLesson ? t('lessons.saving') : t('lessons.save') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
  
  <div class="bg-gray-50 dark:bg-gray-900 min-h-screen transition-colors">
    <!-- Main Content -->
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-4 pb-8">
      <VersionHistoryPanel
        v-if="isHistoryMode && historyContentType"
        :lesson-id="lesson.id"
        :lesson-hashid="lesson.hashid"
        :content-type="historyContentType"
        :selected-version-id="historySelectedVersionId"
        :active-compare="historyActiveCompare"
        @update:selected-version-id="onHistoryVersionChange"
        @update:active-compare="onHistoryCompareChange"
        @close="closeHistoryMode"
        @restored="refreshLesson"
      />

      <template v-else>
      <div class="mb-3 flex items-center justify-between gap-2">
        <!-- Back Button (no card, just like home page) -->
        <button
          @click="emit('close')"
          class="inline-flex items-center gap-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
        >
          <ArrowLeftIcon class="h-4 w-4" />
          {{ t('lessons.backToList') }}
        </button>

        <div v-if="showLessonPager" class="inline-flex items-center gap-1.5">
          <button
            @click="emit('previous')"
            :disabled="!props.hasPreviousLesson"
            :class="[
              'inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors',
              props.hasPreviousLesson
                ? 'border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800'
                : 'border-gray-200 text-gray-400 cursor-not-allowed dark:border-gray-700 dark:text-gray-500',
            ]"
          >
            <ChevronLeftIcon class="h-3.5 w-3.5" />
            {{ t('lessons.previousSession') }}
          </button>
          <button
            @click="emit('next')"
            :disabled="!props.hasNextLesson"
            :class="[
              'inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors',
              props.hasNextLesson
                ? 'border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-200 dark:hover:bg-gray-800'
                : 'border-gray-200 text-gray-400 cursor-not-allowed dark:border-gray-700 dark:text-gray-500',
            ]"
          >
            {{ t('lessons.nextSession') }}
            <ChevronRightIcon class="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      <!-- Processing Status Banner -->
      <div
        v-if="isProcessing"
        class="mb-6 flex items-center gap-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-300 dark:border-amber-700 px-4 py-3"
      >
        <svg class="h-5 w-5 text-amber-600 dark:text-amber-400 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
        </svg>
        <div>
          <span class="font-medium text-amber-800 dark:text-amber-300">
            {{ t('lessons.processingStatus') }}: {{ processStatusLabel }}
          </span>
          <span class="ml-2 text-sm text-amber-700 dark:text-amber-400">
            — {{ t('lessons.processingMessage') }}
          </span>
        </div>
      </div>

      <!-- Lesson Header -->
      <div class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 mb-6 transition-colors">
        <div class="mb-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="flex items-start gap-4 min-w-0">
              <DocumentTextIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-1" />
              <h1 class="text-3xl font-bold text-gray-900 dark:text-white break-words">
                {{ lesson.title }}
              </h1>
            </div>

            <div v-if="!isEditingLesson" class="flex items-center gap-2">
              <button
                v-if="canEditLesson"
                @click="startEditLesson"
                :disabled="isProcessing"
                :class="[
                  'inline-flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-md transition-colors',
                  isProcessing
                    ? 'text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-700 cursor-not-allowed opacity-50'
                    : 'text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
                ]"
              >
                <PencilIcon class="h-4 w-4" />
                {{ t('lessons.modifySession') }}
              </button>
              <button
                v-if="can('lessons', 'delete')"
                @click="confirmDelete"
                :disabled="isProcessing"
                :title="t('lessons.delete')"
                :aria-label="t('lessons.delete')"
                :class="[
                  'inline-flex items-center justify-center rounded-md p-2 transition-colors',
                  isProcessing
                    ? 'text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-700 cursor-not-allowed opacity-50'
                    : 'text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
                ]"
              >
                <TrashIcon class="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Left: lesson metadata/content -->
          <div class="lg:col-span-2">
            <div
              v-if="lessonCoursePath"
              class="mb-3 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300"
            >
              <FolderIcon class="h-4 w-4 flex-shrink-0 text-violet-500 dark:text-violet-400" />
              <span class="truncate">{{ lessonCoursePath }}</span>
            </div>

            <div v-if="lesson.brief" class="mb-4">
              <div class="min-w-0">
                <div class="mb-1 flex items-center gap-2">
                  <div class="text-sm font-semibold text-gray-500 dark:text-gray-400">
                    {{ t('lessons.brief') }}
                  </div>
                  <button
                    v-if="canEditLesson"
                    @click="openHistory('brief')"
                    class="inline-flex items-center gap-1 whitespace-nowrap rounded border border-gray-300 px-1.5 py-0.5 text-[11px] text-gray-600 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
                  >
                    <HistoryIcon class="h-3 w-3" />
                    {{ t('history.historyButton') }}
                  </button>
                </div>
                <div
                  class="text-sm text-gray-600 dark:text-gray-300 leading-relaxed prose prose-sm dark:prose-invert max-w-none"
                  v-html="renderMarkdown(lesson.brief)"
                ></div>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              <div class="flex items-center gap-2 text-sm">
                <CalendarIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('lessons.date') }}</div>
                  <div class="font-medium text-gray-900 dark:text-white">
                    {{ formatDate(lesson.date) }}
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-2 text-sm">
                <ClockIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('lessons.duration') }}</div>
                  <div class="font-medium text-gray-900 dark:text-white">
                    {{ formatDuration(lesson.duration) }}
                  </div>
                </div>
              </div>

              <div class="flex items-center gap-2 text-sm sm:col-span-2">
                <DocumentTextIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <div>
                  <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('lessons.file') }}</div>
                  <div class="font-medium text-gray-900 dark:text-white font-mono text-xs break-all">
                    {{ lesson.filename }}
                  </div>
                </div>
              </div>

              <div v-if="audioUrl" class="sm:col-span-2">
                <audio
                  :src="audioUrl"
                  controls
                  preload="metadata"
                  class="lesson-audio-player w-full sm:max-w-md"
                />
              </div>
            </div>

            <div v-if="lesson.themes && lesson.themes.length > 0" class="flex flex-wrap items-center gap-2 mb-4">
              <span class="text-xs font-medium text-gray-500 dark:text-gray-400">{{ t('lessons.themes') }}:</span>
              <span
                v-for="theme in lesson.themes"
                :key="theme.id"
                class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-indigo-100 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-300"
              >
                {{ theme.name }}
              </span>
            </div>

          </div>

          <!-- Right: workflow -->
          <div class="lg:col-span-1">
            <div class="mb-3 flex items-center justify-between gap-3">
              <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200">
                {{ t('lessons.workflow') }}
              </h3>
              <button
                v-if="!isEditingLesson && canEditLesson"
                @click="openProcessModal"
                :disabled="isProcessing"
                :class="[
                  'inline-flex items-center gap-2 px-3 py-1.5 text-xs font-semibold rounded-md transition-colors',
                  isProcessing
                    ? 'bg-indigo-400 text-white cursor-not-allowed opacity-50'
                    : 'text-white bg-indigo-600 hover:bg-indigo-700'
                ]"
              >
                <CogIcon class="h-3.5 w-3.5" />
                {{ t('lessons.processLesson') }}
              </button>
            </div>

            <div class="space-y-2">
              <div v-if="lesson.editors && lesson.editors.length > 0" class="flex items-center justify-between gap-3 py-1">
                <span class="text-sm font-medium text-slate-500 dark:text-slate-400">{{ t('lessons.editors') }}</span>
                <div class="flex flex-wrap items-center justify-end gap-1.5">
                  <span
                    v-for="editor in lesson.editors"
                    :key="editor.user_id"
                    class="inline-flex items-center px-2 py-1 rounded-md text-xs font-semibold border bg-sky-50 text-sky-700 border-sky-100 dark:bg-sky-900/30 dark:text-sky-300 dark:border-sky-800"
                  >
                    {{ getUserName(editor.user_id, editor.user_name) }}
                  </span>
                </div>
              </div>

              <div class="flex items-center justify-between gap-3 py-1">
                <span class="text-sm font-medium text-slate-500 dark:text-slate-400">
                  {{ t('lessons.sessionStatus') }}
                </span>
                <div class="relative flex-shrink-0">
                  <select
                    :value="lesson.status || 'draft'"
                    :disabled="isUpdatingStatus"
                    :class="[
                      'inline-flex items-center justify-between w-32 px-2 pr-6 py-1 text-xs font-semibold rounded-md border cursor-pointer appearance-none',
                      stepStatusBadgeClass(lessonStatusVisual),
                      isUpdatingStatus ? 'opacity-60 cursor-not-allowed' : '',
                    ]"
                    @change="onLessonStatusSelection($event)"
                  >
                    <option
                      v-for="target in LESSON_STATUS_VALUES"
                      :key="target"
                      :value="target"
                      :disabled="!isStatusSelectable(target)"
                    >
                      {{ t('lessons.status_' + target) }}
                    </option>
                  </select>
                  <ChevronDownIcon
                    class="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500 dark:text-slate-300"
                  />
                </div>
              </div>

              <span v-if="isUpdatingStatus" class="text-xs text-gray-400 dark:text-gray-500">
                {{ t('lessons.statusUpdating') }}
              </span>

            <div class="space-y-2 mb-4">
              <div
                v-for="step in pipelineSteps"
                :key="step.key"
                class="flex items-center justify-between gap-3 py-1"
              >
                <span class="text-sm font-medium text-slate-500 dark:text-slate-400 truncate">
                  {{ t('lessons.step_' + step.key) }}
                </span>
                <div v-if="canEditLesson" class="relative flex-shrink-0">
                  <select
                    :value="step.status"
                    :disabled="isUpdatingStepStatus || isProcessing"
                    :class="[
                      'inline-flex items-center justify-between w-32 px-2 pr-6 py-1 text-xs font-semibold rounded-md border cursor-pointer appearance-none',
                      stepStatusBadgeClass(step.status),
                      (isUpdatingStepStatus || isProcessing) ? 'opacity-60 cursor-not-allowed' : '',
                    ]"
                    @change="onStepStatusSelection(step.key, $event)"
                  >
                    <option :value="step.status">{{ t('lessons.stepStatus_' + step.status) }}</option>
                    <option
                      v-for="target in USER_EDITABLE_STEP_STATUSES"
                      :key="target"
                      :value="target"
                      :disabled="target === step.status"
                    >
                      {{ t('lessons.stepStatus_' + target) }}
                    </option>
                  </select>
                  <ChevronDownIcon
                    class="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-slate-500 dark:text-slate-300"
                  />
                </div>
                <span
                  v-else
                  :class="[
                    'inline-flex items-center justify-between w-32 px-2 py-1 text-xs font-semibold rounded-md border flex-shrink-0',
                    stepStatusBadgeClass(step.status),
                  ]"
                >
                  {{ t('lessons.stepStatus_' + step.status) }}
                </span>
              </div>
            </div>

            </div>
          </div>
        </div>
        
      </div>

      <!-- Content Section with Toggle -->
      <div v-if="availableViews.length > 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
        <!-- Toggle Switch & Audio Player -->
        <div class="border-b border-gray-200 dark:border-gray-700 p-4">
          <div class="flex items-center justify-between gap-4 flex-wrap">
            <div class="inline-flex rounded-lg bg-gray-100 dark:bg-gray-700 p-1">
              <button
                v-for="view in availableViews"
                :key="view.key"
                @click="activeView = view.key"
                :class="[
                  'px-4 py-2 text-sm font-medium rounded-md transition-all',
                  activeView === view.key
                    ? 'bg-white dark:bg-gray-800 text-indigo-600 dark:text-indigo-400 shadow-sm'
                    : 'text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'
                ]"
              >
                {{ view.label }}
              </button>
            </div>
            
            <div class="flex items-center gap-3">
              <!-- Export / Import buttons (summary tab) -->
              <button
                v-if="activeView === 'summary' && !isEditingSummary"
                @click="openLessonDocumentModal('export', 'summary')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <ArrowDownTrayIcon class="h-4 w-4" />
                {{ t('lessons.exportAction') }}
              </button>
              <button
                v-if="activeView === 'summary' && !isEditingSummary && canEditLesson && !isProcessing"
                @click="openLessonDocumentModal('import', 'summary')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <ArrowUpTrayIcon class="h-4 w-4" />
                {{ t('lessons.importAction') }}
              </button>
              <button
                v-if="activeView === 'summary' && canEditLesson && isSummaryAlignmentStale"
                @click="realignSummaryAlignment"
                :disabled="isRealigningSummary || isProcessing"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-md transition-colors"
              >
                <CogIcon class="h-4 w-4" />
                {{ isRealigningSummary ? t('lessons.realigning') : t('lessons.realignSummary') }}
              </button>
              
              <!-- Export / Import buttons (transcript tab) -->
              <button
                v-if="activeView === 'transcript' && !isEditingSummary"
                @click="openLessonDocumentModal('export', 'transcript')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <ArrowDownTrayIcon class="h-4 w-4" />
                {{ t('lessons.exportAction') }}
              </button>
              <button
                v-if="activeView === 'transcript' && !isEditingSummary && canEditLesson && !isProcessing"
                @click="openLessonDocumentModal('import', 'transcript')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <ArrowUpTrayIcon class="h-4 w-4" />
                {{ t('lessons.importAction') }}
              </button>
              
              <!-- Export / Import buttons (edited tab) -->
              <button
                v-if="activeView === 'edited' && !isEditingSummary"
                @click="openLessonDocumentModal('export', 'edited')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <ArrowDownTrayIcon class="h-4 w-4" />
                {{ t('lessons.exportAction') }}
              </button>
              <button
                v-if="activeView === 'edited' && !isEditingSummary && canEditLesson && !isProcessing"
                @click="openLessonDocumentModal('import', 'edited')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <ArrowUpTrayIcon class="h-4 w-4" />
                {{ t('lessons.importAction') }}
              </button>
              <button
                v-if="activeView === 'edited' && canEditLesson && !isProcessing"
                @click="startEditEditedMarkdown"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors print:hidden"
              >
                <PencilIcon class="h-4 w-4" />
                {{ t('lessons.modifyEdited') }}
              </button>
              <button
                v-if="activeView === 'edited' && !isEditingSummary && canEditLesson && isEditedAlignmentStale"
                @click="realignEditedMarkdown"
                :disabled="isRealigningEdited || isProcessing"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed rounded-md transition-colors"
              >
                <CogIcon class="h-4 w-4" />
                {{ isRealigningEdited ? t('lessons.realigning') : t('lessons.realignEdited') }}
              </button>
              
              <!-- Download Sources PDF Buttons and Stats (show for sources view) -->
              <button
                v-if="activeView === 'sources' && !isEditingSummary"
                @click="showSourceStatsModal = true"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors mr-2"
              >
                <ChartBarIcon class="h-4 w-4" />
                {{ t('lessons.sourceStats') }}
              </button>
              <button
                v-if="activeView === 'sources' && !isEditingSummary"
                @click="downloadSourcesPDF"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors mr-2"
              >
                <PrinterIcon class="h-4 w-4" />
                {{ t('lessons.downloadSourcesPDF') }}
              </button>
              <button
                v-if="activeView === 'sources' && !isEditingSummary"
                @click="downloadDetailedSourcesPDF"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <PrinterIcon class="h-4 w-4" />
                {{ t('lessons.downloadDetailedSourcesPDF') }}
              </button>
              
              <!-- Edit Button (show for summary view) -->
              <button
                v-if="activeView === 'summary' && !isEditingSummary && canEditLesson && !isProcessing"
                @click="startEditSummary"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors print:hidden"
              >
                <PencilIcon class="h-4 w-4" />
                {{ t('lessons.modifySummary') }}
              </button>
              <button
                v-if="canEditLesson && activeView === 'summary'"
                @click="openHistory('summary')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors print:hidden"
              >
                <HistoryIcon class="h-4 w-4" />
                {{ t('history.historyButton') }}
              </button>
              <button
                v-if="canEditLesson && activeView === 'transcript'"
                @click="openHistory('corrected_transcript')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors print:hidden"
              >
                <HistoryIcon class="h-4 w-4" />
                {{ t('history.historyButton') }}
              </button>
              <button
                v-if="canEditLesson && activeView === 'edited'"
                @click="openHistory('edited_transcript')"
                class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors print:hidden"
              >
                <HistoryIcon class="h-4 w-4" />
                {{ t('history.historyButton') }}
              </button>
              
              <!-- Audio Player Controls (show for transcript view) -->
              <div 
                v-if="activeView === 'transcript' && audioUrl"
                class="flex items-center gap-2 print:hidden"
              >
                <SpeakerWaveIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
                <button
                  @click="togglePlayPause"
                  class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
                >
                  <PlayIcon v-if="!isPlaying" class="h-4 w-4" />
                  <PauseIcon v-else class="h-4 w-4" />
                  {{ isPlaying ? t('lessons.pause') : t('lessons.play') }}
                </button>
              </div>
            </div>
          </div>
          
          <!-- Hidden Audio Element -->
          <audio
            v-if="audioUrl"
            ref="audioPlayer"
            :src="audioUrl"
            preload="metadata"
            @timeupdate="updateTime"
            @ended="onAudioEnded"
            @play="isPlaying = true"
            @pause="isPlaying = false"
            class="hidden"
          ></audio>
        </div>
        
        <!-- Content Panels -->
        <div class="p-6">
          <!-- Global floating now-playing bar -->
          <div
            v-if="isPlaying && (activeView === 'transcript' || activeView === 'edited' || (activeView === 'summary' && showSummaryWithEdited))"
            class="fixed top-4 left-1/2 -translate-x-1/2 z-50 w-[min(1100px,calc(100vw-2rem))] flex items-center justify-between gap-3 px-4 py-2 bg-indigo-50/95 dark:bg-indigo-900/80 border border-indigo-300 dark:border-indigo-700 rounded-lg shadow-lg backdrop-blur-sm print:hidden"
          >
            <div class="flex items-center gap-2 text-sm font-medium text-indigo-700 dark:text-indigo-300">
              <SpeakerWaveIcon class="h-4 w-4 animate-pulse" />
              <span>{{ t('lessons.nowPlaying') }}</span>
              <span class="font-mono text-xs">{{ formatTimestamp(currentTime) }}</span>
            </div>
            <div class="flex items-center gap-1">
              <button
                @click="togglePlayPause"
                class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-indigo-700 dark:text-indigo-300 bg-indigo-100 dark:bg-indigo-800/50 hover:bg-indigo-200 dark:hover:bg-indigo-800 rounded-md transition-colors"
              >
                <PauseIcon class="h-3.5 w-3.5" />
                {{ t('lessons.pause') }}
              </button>
              <button
                @click="stopAudio"
                class="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
              >
                <StopIcon class="h-3.5 w-3.5" />
                {{ t('lessons.stop') }}
              </button>
            </div>
          </div>
          <div
            v-if="isPlaying && (activeView === 'transcript' || activeView === 'edited' || (activeView === 'summary' && showSummaryWithEdited))"
            class="h-16 print:hidden"
          ></div>

          <!-- Summary View -->
          <div v-if="activeView === 'summary'">
            <div
              v-if="isSummaryAlignmentStale"
              class="mb-4 inline-flex items-center gap-2 px-3 py-2 text-xs text-amber-800 dark:text-amber-200 bg-amber-100 dark:bg-amber-900/30 rounded-md"
            >
              <ExclamationTriangleIcon class="h-4 w-4" />
              <span>{{ t('lessons.summaryAlignmentOutdated') }}</span>
              <button
                v-if="canEditLesson"
                @click="realignSummaryAlignment"
                :disabled="isRealigningSummary || isProcessing"
                class="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-amber-900 dark:text-amber-100 bg-amber-200 dark:bg-amber-800/60 hover:bg-amber-300 dark:hover:bg-amber-700/60 disabled:opacity-60 disabled:cursor-not-allowed rounded transition-colors"
              >
                <CogIcon class="h-3.5 w-3.5" />
                {{ isRealigningSummary ? t('lessons.realigning') : t('lessons.realignSummarySmall') }}
              </button>
            </div>
            <div class="flex items-center justify-end mb-4 print:hidden">
              <label class="inline-flex items-center gap-2 cursor-pointer select-none">
                <span class="text-sm text-gray-600 dark:text-gray-400">{{ t('lessons.showEditedVersion') }}</span>
                <button
                  type="button"
                  role="switch"
                  :aria-checked="showSummaryWithEdited"
                  @click="showSummaryWithEdited = !showSummaryWithEdited"
                  :class="[
                    showSummaryWithEdited ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600',
                    'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800'
                  ]"
                >
                  <span
                    :class="[
                      showSummaryWithEdited ? 'translate-x-4' : 'translate-x-0.5',
                      'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out mt-0.5'
                    ]"
                  />
                </button>
              </label>
            </div>

            <div v-if="showSummaryWithEdited && summaryComparisonRows.length > 0" class="space-y-3">
              <div class="sticky top-0 z-10 grid grid-cols-2 gap-4 py-2 bg-white/95 dark:bg-gray-800/95 backdrop-blur-sm border-b border-gray-200 dark:border-gray-700">
                <div class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {{ t('lessons.summary') }}
                </div>
                <div class="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {{ t('lessons.editedTranscript') }}
                </div>
              </div>
              <div
                v-for="(row, idx) in summaryComparisonRows"
                :key="`summary-aligned-${row.key}-${idx}`"
                class="grid grid-cols-2 gap-4 py-1.5 rounded-lg"
              >
                <div class="prose prose-sm dark:prose-invert max-w-none">
                  <div
                    v-if="row.summaryText"
                    class="text-gray-900 dark:text-gray-100 leading-relaxed"
                    v-html="renderMarkdown(row.summaryText)"
                  ></div>
                  <div
                    v-else
                    class="rounded-md px-2 py-1 text-xs italic text-gray-500 dark:text-gray-400"
                  >
                    {{ t('lessons.noSummaryMatchForEditedParagraph') }}
                  </div>
                </div>
                <div class="prose prose-sm dark:prose-invert max-w-none">
                  <div
                    v-for="(part, partIdx) in row.editedParts"
                    :key="`summary-aligned-edited-${idx}-${partIdx}`"
                    :class="[
                      'flex items-start gap-2 mb-3 last:mb-0 rounded-md px-2 py-2',
                      part.isUnmatched
                        ? 'border border-rose-300 bg-rose-50/60 dark:border-rose-700 dark:bg-rose-900/20'
                        : '',
                    ]"
                  >
                    <div class="mt-1 inline-flex items-center gap-1 text-indigo-600 dark:text-indigo-400 print:hidden">
                      <button
                        @click="isSummaryAlignedPartPlaying(part) ? togglePlayPause() : playFromTimestamp(part.start)"
                        class="inline-flex h-6 w-6 items-center justify-center rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/30 transition-colors"
                        :title="isSummaryAlignedPartPlaying(part) ? t('lessons.pause') : t('lessons.play')"
                      >
                        <PauseIcon v-if="isSummaryAlignedPartPlaying(part)" class="h-3.5 w-3.5" />
                        <PlayIcon v-else class="h-3.5 w-3.5" />
                      </button>
                      <span class="text-[11px] font-mono leading-none text-indigo-500 dark:text-indigo-300">
                        {{ formatTimestamp(part.start) }}
                      </span>
                    </div>
                    <div class="flex-1">
                      <div
                        v-if="part.isUnmatched"
                        class="mb-1 inline-flex items-center rounded-full border border-rose-300 bg-rose-100 px-2 py-0.5 text-[11px] font-medium text-rose-700 dark:border-rose-700 dark:bg-rose-900/40 dark:text-rose-300"
                      >
                        {{ t('lessons.possiblySkippedInSummary') }}
                      </div>
                      <div
                        class="text-gray-900 dark:text-gray-100 leading-relaxed"
                        v-html="renderMarkdown(part.text)"
                      ></div>
                    </div>
                  </div>
                  <div
                    v-if="row.editedParts.length === 0"
                    class="rounded-md border border-gray-200 dark:border-gray-700 px-2 py-1 text-xs italic text-gray-500 dark:text-gray-400"
                  >
                    {{ t('lessons.noAlignedEditedParagraph') }}
                  </div>
                </div>
              </div>
            </div>
            <div v-else 
              class="prose prose-indigo dark:prose-invert max-w-none"
              v-html="renderMarkdown(lesson.summary)"
            ></div>
          </div>

          <!-- Workflow History View -->
          <div v-else-if="activeView === 'workflow'">
            <div v-if="workflowAuditLoading" class="text-sm text-gray-500 dark:text-gray-400">
              {{ t('history.loadingWorkflowHistory') }}
            </div>
            <div v-else-if="workflowAuditLog.length === 0" class="text-sm text-gray-500 dark:text-gray-400">
              {{ t('history.noWorkflowEvents') }}
            </div>
            <div v-else class="overflow-x-auto">
              <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead class="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">
                      {{ t('audit.timestamp') }}
                    </th>
                    <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">
                      {{ t('audit.actor') }}
                    </th>
                    <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">
                      {{ t('audit.action') }}
                    </th>
                    <th class="px-3 py-2 text-left text-xs text-gray-500 dark:text-gray-400">
                      {{ t('audit.payload') }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
                  <tr v-for="row in workflowAuditLog" :key="row.id">
                    <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                      {{ new Date(row.occurred_at).toLocaleString() }}
                    </td>
                    <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                      {{ workflowActorName(row.actor_id) }} ({{ workflowActorRole(row.actor_role) }})
                    </td>
                    <td class="px-3 py-2 text-xs text-gray-700 dark:text-gray-300">
                      {{ workflowActionLabel(row.action) }}
                    </td>
                    <td class="px-3 py-2 text-xs">
                      <button
                        @click="toggleWorkflowPayload(row.id)"
                        class="rounded border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700"
                      >
                        {{ workflowExpandedPayload.has(row.id) ? t('audit.hideJson') : t('audit.showJson') }}
                      </button>
                      <pre
                        v-if="workflowExpandedPayload.has(row.id)"
                        class="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2 text-xs text-gray-800 dark:bg-gray-900 dark:text-gray-200"
                      >{{ JSON.stringify(row.payload, null, 2) }}</pre>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          
          <!-- Unified Transcript View with Diffs -->
          <div v-else-if="activeView === 'transcript'">
            <div v-if="unifiedTranscript.length > 0" class="space-y-4 scroll-smooth relative">
              <div
                v-for="segment in unifiedTranscript"
                :key="segment.index"
                :data-segment-index="segment.index"
                :class="[
                  'flex gap-3 p-4 rounded-lg border transition-all print:border-0 print:p-2',
                  isSegmentActive(segment)
                    ? 'bg-indigo-50 dark:bg-indigo-900/20 border-indigo-400 dark:border-indigo-600 print:bg-white'
                    : segment.hasDiff
                      ? 'bg-green-50 dark:bg-green-900/10 border-green-200 dark:border-green-800 hover:border-green-300 dark:hover:border-green-700 print:bg-white'
                      : 'bg-gray-50 dark:bg-gray-900 border-gray-200 dark:border-gray-700 hover:border-indigo-300 dark:hover:border-indigo-700 print:bg-white'
                ]"
              >
                <button
                  v-if="audioUrl"
                  @click="playFromTimestamp(segment.start)"
                  class="flex-shrink-0 p-1.5 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors print:hidden"
                  :title="t('lessons.playSegment')"
                >
                  <PlayIcon class="h-4 w-4" />
                </button>
                <div class="flex-shrink-0 text-xs font-mono text-indigo-600 dark:text-indigo-400 font-semibold pt-0.5 print:hidden">
                  {{ formatTimestamp(segment.start) }} - {{ formatTimestamp(segment.end) }}
                </div>
                <div class="flex-1 space-y-2">
                  <!-- Edit Mode -->
                  <div v-if="editingSegmentIndex === segment.index" class="space-y-2">
                    <textarea
                      v-model="editedSegmentText"
                      class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
                      rows="3"
                      @keydown.esc="cancelEditSegment"
                    ></textarea>
                    <div class="flex gap-2">
                      <button
                        @click="saveSegment"
                        :disabled="isSavingSegment"
                        class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded transition-colors"
                      >
                        <CheckIcon class="h-3 w-3" />
                        {{ isSavingSegment ? t('lessons.saving') : t('lessons.save') }}
                      </button>
                      <button
                        @click="cancelEditSegment"
                        :disabled="isSavingSegment"
                        class="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded transition-colors"
                      >
                        <XMarkIcon class="h-3 w-3" />
                        {{ t('lessons.cancel') }}
                      </button>
                    </div>
                  </div>
                  
                  <!-- View Mode -->
                  <div v-else>
                    <div class="flex items-start gap-2">
                      <div class="flex-1">
                        <!-- Corrected Text -->
                        <div class="text-sm text-gray-900 dark:text-gray-100 print:text-black">
                          <span v-if="segment.hasDiff" class="inline-block px-1.5 py-0.5 text-xs font-semibold text-green-700 dark:text-green-400 bg-green-100 dark:bg-green-900/30 rounded mr-2 print:hidden">
                            {{ t('lessons.corrected') }}
                          </span>
                          {{ segment.correctedText }}
                        </div>
                        
                        <!-- Original Text (if different) -->
                        <div v-if="segment.hasDiff" class="text-sm text-gray-500 dark:text-gray-400 italic pl-4 border-l-2 border-gray-300 dark:border-gray-600 print:hidden mt-2">
                          <span class="inline-block px-1.5 py-0.5 text-xs font-semibold text-gray-600 dark:text-gray-400 bg-gray-200 dark:bg-gray-700 rounded mr-2">
                            {{ t('lessons.original') }}
                          </span>
                          {{ segment.originalText }}
                        </div>
                      </div>
                      
                      <!-- Edit Button -->
                      <button
                        v-if="canEditLesson && !isProcessing && lesson.corrected_transcript && lesson.corrected_transcript.length > 0"
                        @click="startEditSegment(segment.index, segment.correctedText)"
                        class="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors print:hidden"
                        :title="t('lessons.editSegment')"
                      >
                        <PencilIcon class="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <!-- No transcript message -->
            <div v-else class="text-center py-12">
              <p class="text-gray-500 dark:text-gray-400">
                {{ t('lessons.noTranscripts') }}
              </p>
            </div>
          </div>
          
          <!-- Sources View -->
          <div v-else-if="activeView === 'sources'">
            <div v-if="allSources.length > 0" class="space-y-6 max-h-[600px] overflow-auto scroll-smooth print:max-h-none">
              <div
                v-for="(typeGroup, typeIndex) in allSources"
                :key="typeIndex"
                class="p-5 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 transition-all"
              >
                <!-- Type Name -->
                <div class="font-semibold text-lg text-gray-900 dark:text-white mb-4 pb-3 border-b border-gray-200 dark:border-gray-700">
                  {{ typeGroup.type }}
                </div>
                
                <!-- Sources List -->
                <div class="space-y-2">
                  <div
                    v-for="(source, sourceIndex) in typeGroup.sources"
                    :key="sourceIndex"
                    @click="openSourceModal(source.editedPart, source)"
                    class="flex items-start gap-3 p-3 rounded-md bg-gray-50 dark:bg-gray-900 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors cursor-pointer"
                  >
                    <!-- Search icon -->
                    <div class="flex-shrink-0 p-1.5 rounded-md text-indigo-600 dark:text-indigo-400">
                      <MagnifyingGlassIcon class="h-4 w-4" />
                    </div>
                    
                    <!-- Work, Reference, Standard Slug, Translation Text, Original Text, and Confidence -->
                    <div class="flex-1 text-sm text-gray-700 dark:text-gray-300">
                      <div class="flex items-center gap-2 flex-wrap mb-1">
                        <span v-if="source.work" class="italic font-medium">{{ source.work }}</span>
                        <span v-if="source.work && source.ref">, </span>
                        <span v-if="source.ref" class="text-gray-500 dark:text-gray-400">{{ source.ref }}</span>
                        <span v-if="source.standard_slug" class="text-xs text-gray-400 dark:text-gray-500 font-mono">({{ source.standard_slug }})</span>
                        <!-- Verification status icon -->
                        <span v-if="source.verification_status && ['exactly_found', 'paraphrase_or_similar'].includes(source.verification_status) && source.verification_confidence !== null && source.verification_confidence > 0.9" 
                          class="text-green-600 dark:text-green-400"
                          title="Verified (confidence > 90%)">
                          <CheckIcon class="h-5 w-5" />
                        </span>
                        <span v-else-if="!source.verification_status || ['not_found', 'reference_exists_but_text_differs'].includes(source.verification_status) || (source.verification_confidence !== null && source.verification_confidence <= 0.9) || source.slug_retrieved === false"
                          class="text-yellow-600 dark:text-yellow-400"
                          :title="!source.verification_status || ['not_found', 'reference_exists_but_text_differs'].includes(source.verification_status) ? 'Citation not found or differs' : source.verification_confidence !== null ? `Verification confidence: ${(source.verification_confidence * 100).toFixed(0)}%` : 'Not verified'">
                          <ExclamationTriangleIcon class="h-5 w-5" />
                        </span>
                      </div>
                      <div v-if="source.translation_text" class="italic mb-1">
                        "{{ source.translation_text }}"
                      </div>
                      <div v-if="source.original_text" class="text-gray-600 dark:text-gray-400 italic text-xs">
                        <span class="font-medium">Original:</span> "{{ source.original_text }}"
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-12">
              <p class="text-gray-500 dark:text-gray-400">
                {{ t('lessons.noSources') }}
              </p>
            </div>
          </div>

          <!-- Edited Transcript View -->
          <div v-else-if="activeView === 'edited'">
            <!-- Toggle for side-by-side transcript -->
            <div class="flex items-center justify-end mb-4 print:hidden">
              <div
                v-if="isEditedAlignmentStale"
                class="inline-flex items-center gap-2 mr-3 px-2.5 py-1 text-xs text-amber-800 dark:text-amber-200 bg-amber-100 dark:bg-amber-900/30 rounded-md"
              >
                <ExclamationTriangleIcon class="h-4 w-4" />
                <span>{{ t('lessons.alignmentOutdated') }}</span>
                <button
                  v-if="canEditLesson"
                  @click="realignEditedMarkdown"
                  :disabled="isRealigningEdited || isProcessing"
                  class="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-amber-900 dark:text-amber-100 bg-amber-200 dark:bg-amber-800/60 hover:bg-amber-300 dark:hover:bg-amber-700/60 disabled:opacity-60 disabled:cursor-not-allowed rounded transition-colors"
                >
                  <CogIcon class="h-3.5 w-3.5" />
                  {{ isRealigningEdited ? t('lessons.realigning') : t('lessons.realignEditedSmall') }}
                </button>
              </div>
              <label class="inline-flex items-center gap-2 cursor-pointer select-none">
                <span
                  class="text-sm text-gray-600 dark:text-gray-400"
                >{{ t('lessons.sideBySideTranscript') }}</span>
                <button
                  type="button"
                  role="switch"
                  :aria-checked="showSideBySideTranscript"
                  @click="showSideBySideTranscript = !showSideBySideTranscript"
                  :class="[
                    showSideBySideTranscript ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600',
                    'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800'
                  ]"
                >
                  <span
                    :class="[
                      showSideBySideTranscript ? 'translate-x-4' : 'translate-x-0.5',
                      'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out mt-0.5'
                    ]"
                  />
                </button>
              </label>
              <label
                v-if="hasSourcesExtracted"
                class="inline-flex items-center gap-2 cursor-pointer select-none ml-5"
              >
                <span
                  class="text-sm text-gray-600 dark:text-gray-400"
                >{{ t('lessons.showSources') }}</span>
                <button
                  type="button"
                  role="switch"
                  :aria-checked="showSourcesInEdited"
                  @click="showSourcesInEdited = !showSourcesInEdited"
                  :class="[
                    showSourcesInEdited ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600',
                    'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-gray-800'
                  ]"
                >
                  <span
                    :class="[
                      showSourcesInEdited ? 'translate-x-4' : 'translate-x-0.5',
                      'pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out mt-0.5'
                    ]"
                  />
                </button>
              </label>
            </div>

            <div v-if="editedParts.length > 0" class="scroll-smooth relative">
              <!-- Side-by-side layout: one row per paragraph -->
              <div v-if="showSideBySideTranscript">
                <div
                  v-for="row in editedSideBySideRows"
                  :key="row.key"
                  :data-paragraph-index="row.editedPart?.index ?? null"
                  :class="[
                    'grid grid-cols-2 gap-4 py-1.5 print:py-1 rounded-lg transition-colors',
                    row.editedPart && isEditedPartPlaying(row.editedPart) ? 'bg-indigo-50 dark:bg-indigo-900/20' : '',
                    row.isUnmatchedTranscriptRow ? 'border border-rose-300 dark:border-rose-700 bg-rose-50/70 dark:bg-rose-900/15 px-2' : '',
                  ]"
                >
                  <!-- Left: Edited paragraph + sources -->
                  <div>
                    <div v-if="row.editedPart" class="flex gap-3">
                      <!-- Play/Pause Button -->
                      <button
                        v-if="audioUrl"
                        @click="togglePlayEditedPart(row.editedPart)"
                        class="flex-shrink-0 p-1.5 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors print:hidden mt-1"
                        :title="isEditedPartPlaying(row.editedPart) ? t('lessons.pause') : t('lessons.playSegment')"
                      >
                        <PlayIcon v-if="!isEditedPartPlaying(row.editedPart)" class="h-4 w-4" />
                        <PauseIcon v-else class="h-4 w-4" />
                      </button>
                      
                      <!-- Edited Text (view mode) -->
                      <div v-if="editingParagraphIndex !== row.editedPart.index" class="flex-1">
                        <div class="prose prose-sm dark:prose-invert max-w-none">
                          <div 
                            class="text-gray-900 dark:text-gray-100 leading-relaxed whitespace-pre-wrap print:text-black"
                            v-html="renderMarkdown(showSourcesInEdited ? addSourceMarkers(row.editedPart.text, getSourcesForParagraph(row.editedPart.index) as any, getGlobalSourceIndex(row.editedPart.index)) : row.editedPart.text)"
                          ></div>
                        </div>
                      </div>

                      <!-- Edited Text (edit mode) -->
                      <div v-else class="flex-1 space-y-2">
                        <textarea
                          v-model="editedParagraphText"
                          class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-y"
                          rows="6"
                          @keydown.esc="cancelEditParagraph"
                        ></textarea>
                        <div class="flex gap-2">
                          <button
                            @click="saveParagraph"
                            :disabled="isSavingParagraph"
                            class="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
                          >
                            <CheckIcon class="h-3.5 w-3.5" />
                            {{ isSavingParagraph ? t('lessons.saving') : t('lessons.save') }}
                          </button>
                          <button
                            @click="cancelEditParagraph"
                            :disabled="isSavingParagraph"
                            class="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded-md transition-colors"
                          >
                            <XMarkIcon class="h-3.5 w-3.5" />
                            {{ t('lessons.cancel') }}
                          </button>
                        </div>
                      </div>

                      <!-- Edit Paragraph Button -->
                      <button
                        v-if="canEditLesson && !isProcessing && editingParagraphIndex !== row.editedPart.index"
                        @click="startEditParagraph(row.editedPart.index, row.editedPart.text)"
                        class="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors print:hidden"
                        :title="t('lessons.editParagraph')"
                      >
                        <PencilIcon class="h-4 w-4" />
                      </button>
                    </div>

                    <!-- Sources -->
                    <div v-if="row.editedPart && showSourcesInEdited && getSourcesForParagraph(row.editedPart.index).length > 0" class="space-y-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 print:border-gray-300">
                      <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                        {{ t('lessons.sources') }}
                      </div>
                      <div
                        v-for="(source, srcIndex) in getSourcesForParagraph(row.editedPart.index)"
                        :key="srcIndex"
                        @click="openSourceModal(row.editedPart, source)"
                        class="flex gap-3 p-3 rounded-md bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 print:bg-gray-50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors print:cursor-default"
                      >
                        <div class="flex-shrink-0 text-green-600 dark:text-green-400 font-bold text-sm">
                          [{{ getGlobalSourceIndex(row.editedPart.index) + srcIndex + 1 }}]
                        </div>
                        <div class="flex-1 text-sm">
                          <div class="flex items-center gap-2 mb-1">
                            <div class="font-semibold text-gray-900 dark:text-white">
                              <span v-if="source.type" class="text-gray-600 dark:text-gray-400">{{ source.type }}</span><span v-if="source.type && source.work"> — </span><span v-if="source.work" class="italic">{{ source.work }}</span>
                            </div>
                            <!-- Verification status icon -->
                            <span v-if="source.verification_status && ['exactly_found', 'paraphrase_or_similar'].includes(source.verification_status) && source.verification_confidence !== null && source.verification_confidence > 0.9" 
                              class="text-green-600 dark:text-green-400"
                              title="Verified (confidence > 90%)">
                              <CheckIcon class="h-5 w-5" />
                            </span>
                            <span v-else-if="!source.verification_status || ['not_found', 'reference_exists_but_text_differs'].includes(source.verification_status) || (source.verification_confidence !== null && source.verification_confidence <= 0.9) || source.slug_retrieved === false"
                              class="text-yellow-600 dark:text-yellow-400"
                              :title="!source.verification_status || ['not_found', 'reference_exists_but_text_differs'].includes(source.verification_status) ? 'Citation not found or differs' : source.verification_confidence !== null ? `Verification confidence: ${(source.verification_confidence * 100).toFixed(0)}%` : 'Not verified'">
                              <ExclamationTriangleIcon class="h-5 w-5" />
                            </span>
                          </div>
                          <div v-if="source.ref" class="text-xs text-gray-500 dark:text-gray-400 mb-1">
                            {{ source.ref }}<span v-if="source.standard_slug" class="text-gray-400 dark:text-gray-500 font-mono ml-2">({{ source.standard_slug }})</span>
                          </div>
                          <div v-if="source.translation_text" class="text-gray-700 dark:text-gray-300 italic mb-1">
                            "{{ source.translation_text }}"
                          </div>
                          <div v-if="source.original_text" class="text-gray-600 dark:text-gray-400 italic text-xs mt-1">
                            <span class="font-medium">Original:</span> "{{ source.original_text }}"
                          </div>
                        </div>
                      </div>
                    </div>
                    <div v-else-if="row.isUnmatchedTranscriptRow" class="h-full flex items-center">
                      <div class="w-full rounded-md border border-rose-300 dark:border-rose-700 bg-rose-100/70 dark:bg-rose-900/30 px-3 py-2 text-sm text-rose-700 dark:text-rose-300 italic">
                        {{ t('lessons.noMatchedEditedParagraph') }}
                      </div>
                    </div>
                  </div>

                  <!-- Right: Corresponding transcript segments -->
                  <div class="pl-4">
                    <!-- Time Range -->
                    <div v-if="row.transcriptSegments.length > 0 || row.editedPart" class="flex items-center gap-2 mb-2">
                      <ClockIcon class="h-3.5 w-3.5 text-gray-400 dark:text-gray-500" />
                      <div class="text-xs text-gray-500 dark:text-gray-400">
                        {{
                          row.transcriptSegments.length > 0
                            ? `${formatTimestamp(row.transcriptSegments[0].start)} – ${formatTimestamp(row.transcriptSegments[row.transcriptSegments.length - 1].end)}`
                            : `${formatTimestamp(row.editedPart?.start ?? null)} – ${formatTimestamp(row.editedPart?.end ?? null)}`
                        }}
                      </div>
                    </div>
                    <!-- Transcript Segments -->
                    <div class="space-y-1">
                      <div 
                        v-for="segment in row.transcriptSegments"
                        :key="segment.index"
                        :class="[
                          'text-sm leading-relaxed rounded-md px-2 py-1',
                          row.isUnmatchedTranscriptRow
                            ? 'text-rose-800 dark:text-rose-200 border border-rose-300 dark:border-rose-700 bg-rose-50 dark:bg-rose-900/20'
                            : 'text-gray-700 dark:text-gray-300',
                        ]"
                      >
                        <span class="text-xs font-mono text-indigo-500 dark:text-indigo-400 mr-2">{{ formatTimestamp(segment.start) }}</span>{{ segment.text }}
                      </div>
                      <div v-if="row.transcriptSegments.length === 0" class="text-sm text-gray-400 dark:text-gray-500 italic py-2">
                        {{ t('lessons.noTranscripts') }}
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Standard layout (no side-by-side) -->
              <div v-else>
                <div
                  v-for="(part, index) in editedParts"
                  :key="index"
                  :data-paragraph-index="index"
                  :class="[
                    'print:py-0.5 rounded-lg transition-colors',
                    isEditedPartPlaying(part) ? 'bg-indigo-50 dark:bg-indigo-900/20' : ''
                  ]"
                >
                  <!-- Controls and Text -->
                  <div class="flex gap-2">
                    <!-- Play/Pause Button -->
                    <button
                      v-if="audioUrl"
                      @click="togglePlayEditedPart(part)"
                      class="flex-shrink-0 p-1.5 rounded-md hover:bg-indigo-100 dark:hover:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400 transition-colors print:hidden mt-1"
                      :title="isEditedPartPlaying(part) ? t('lessons.pause') : t('lessons.playSegment')"
                    >
                      <PlayIcon v-if="!isEditedPartPlaying(part)" class="h-4 w-4" />
                      <PauseIcon v-else class="h-4 w-4" />
                    </button>
                    
                    <!-- Edited Text (view mode) -->
                    <div v-if="editingParagraphIndex !== index" class="flex-1">
                      <div class="prose prose-sm dark:prose-invert max-w-none">
                        <div 
                          class="text-gray-900 dark:text-gray-100 leading-normal whitespace-pre-wrap print:text-black"
                          v-html="renderMarkdown(showSourcesInEdited ? addSourceMarkers(part.text, getSourcesForParagraph(index) as any, getGlobalSourceIndex(index)) : part.text)"
                        ></div>
                      </div>
                    </div>

                    <!-- Edited Text (edit mode) -->
                    <div v-else class="flex-1 space-y-2">
                      <textarea
                        v-model="editedParagraphText"
                        class="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-y"
                        rows="6"
                        @keydown.esc="cancelEditParagraph"
                      ></textarea>
                      <div class="flex gap-2">
                        <button
                          @click="saveParagraph"
                          :disabled="isSavingParagraph"
                          class="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
                        >
                          <CheckIcon class="h-3.5 w-3.5" />
                          {{ isSavingParagraph ? t('lessons.saving') : t('lessons.save') }}
                        </button>
                        <button
                          @click="cancelEditParagraph"
                          :disabled="isSavingParagraph"
                          class="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded-md transition-colors"
                        >
                          <XMarkIcon class="h-3.5 w-3.5" />
                          {{ t('lessons.cancel') }}
                        </button>
                      </div>
                    </div>

                    <!-- Edit Paragraph Button -->
                    <button
                      v-if="canEditLesson && !isProcessing && editingParagraphIndex !== index"
                      @click="startEditParagraph(index, part.text)"
                      class="flex-shrink-0 p-1 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors print:hidden"
                      :title="t('lessons.editParagraph')"
                    >
                      <PencilIcon class="h-4 w-4" />
                    </button>
                  </div>
                  
                  <!-- Sources -->
                  <div v-if="showSourcesInEdited && getSourcesForParagraph(index).length > 0" class="space-y-2 mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 print:border-gray-300">
                    <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2">
                      {{ t('lessons.sources') }}
                    </div>
                    <div
                      v-for="(source, srcIndex) in getSourcesForParagraph(index)"
                      :key="srcIndex"
                      @click="openSourceModal(part, source)"
                      class="flex gap-3 p-3 rounded-md bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 print:bg-gray-50 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors print:cursor-default"
                    >
                      <div class="flex-shrink-0 text-green-600 dark:text-green-400 font-bold text-sm">
                        [{{ getGlobalSourceIndex(index) + srcIndex + 1 }}]
                      </div>
                      <div class="flex-1 text-sm">
                        <div class="flex items-center gap-2 mb-1">
                          <div class="font-semibold text-gray-900 dark:text-white">
                            <span v-if="source.type" class="text-gray-600 dark:text-gray-400">{{ source.type }}</span><span v-if="source.type && source.work"> — </span><span v-if="source.work" class="italic">{{ source.work }}</span>
                          </div>
                          <!-- Verification status icon -->
                          <span v-if="source.verification_status && ['exactly_found', 'paraphrase_or_similar'].includes(source.verification_status) && source.verification_confidence !== null && source.verification_confidence > 0.9" 
                            class="text-green-600 dark:text-green-400"
                            title="Verified (confidence > 90%)">
                            <CheckIcon class="h-5 w-5" />
                          </span>
                          <span v-else-if="!source.verification_status || ['not_found', 'reference_exists_but_text_differs'].includes(source.verification_status) || (source.verification_confidence !== null && source.verification_confidence <= 0.9) || source.slug_retrieved === false"
                            class="text-yellow-600 dark:text-yellow-400"
                            :title="!source.verification_status || ['not_found', 'reference_exists_but_text_differs'].includes(source.verification_status) ? 'Citation not found or differs' : source.verification_confidence !== null ? `Verification confidence: ${(source.verification_confidence * 100).toFixed(0)}%` : 'Not verified'">
                            <ExclamationTriangleIcon class="h-5 w-5" />
                          </span>
                        </div>
                        <div v-if="source.ref" class="text-xs text-gray-500 dark:text-gray-400 mb-1">
                          {{ source.ref }}<span v-if="source.standard_slug" class="text-gray-400 dark:text-gray-500 font-mono ml-2">({{ source.standard_slug }})</span>
                        </div>
                        <div v-if="source.translation_text" class="text-gray-700 dark:text-gray-300 italic mb-1">
                          "{{ source.translation_text }}"
                        </div>
                        <div v-if="source.original_text" class="text-gray-600 dark:text-gray-400 italic text-xs mt-1">
                          <span class="font-medium">Original:</span> "{{ source.original_text }}"
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="text-center py-12">
              <p class="text-gray-500 dark:text-gray-400">
                {{ t('lessons.noEditedTranscript') }}
              </p>
            </div>
          </div>
        </div>
      </div>

      <!-- No Content Message -->
      <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 text-center transition-colors">
        <p class="text-gray-500 dark:text-gray-400">
          {{ t('lessons.noContent') }}
        </p>
      </div>
      </template>
    </div>

    <!-- Source Modal -->
    <Dialog
      :open="showSourceModal"
      @close="showSourceModal = false"
      class="relative z-50"
    >
      <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel class="w-full max-w-6xl bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-h-[90vh] overflow-auto">
          <div class="p-6">
            <DialogTitle class="text-xl font-bold text-gray-900 dark:text-white mb-4">
              {{ t('lessons.sourceDetails') }}
            </DialogTitle>
            
            <div class="space-y-6">
              <!-- Edited Part Text -->
              <div class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">{{ t('lessons.editedText') }}</h3>
                <div class="prose prose-sm dark:prose-invert max-w-none">
                  <div class="text-gray-900 dark:text-gray-100 leading-relaxed whitespace-pre-wrap" v-html="renderMarkdown(selectedSourceEditedText)"></div>
                </div>
              </div>

              <!-- Source Information -->
              <div v-if="selectedSource" class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Source Information</h3>
                <div class="space-y-2 text-sm">
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Type:</span> <span class="text-gray-900 dark:text-white">{{ selectedSource.type || 'N/A' }}</span></div>
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Work:</span> <span class="text-gray-900 dark:text-white">{{ selectedSource.work || 'N/A' }}</span></div>
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Reference:</span> <span class="text-gray-900 dark:text-white">{{ selectedSource.ref || 'N/A' }}</span></div>
                  <div><span class="font-medium text-gray-700 dark:text-gray-300">Slug:</span> <span class="text-gray-900 dark:text-white font-mono text-xs">{{ selectedSource.standard_slug || 'N/A' }}</span></div>
                  <div v-if="selectedSource.cited_excerpt">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Cited Excerpt (in edited text):</span>
                    <div class="text-gray-900 dark:text-white mt-1 bg-yellow-50 dark:bg-yellow-900/20 p-2 rounded border border-yellow-200 dark:border-yellow-800">
                      "{{ selectedSource.cited_excerpt }}"
                    </div>
                  </div>
                  <div v-if="selectedSource.original_text">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Original Text:</span>
                    <div class="text-gray-900 dark:text-white italic mt-1">{{ selectedSource.original_text }}</div>
                  </div>
                  <div v-if="selectedSource.translation_text">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Translation Text:</span>
                    <div class="text-gray-900 dark:text-white italic mt-1">{{ selectedSource.translation_text }}</div>
                  </div>
                  <div v-if="selectedSource.confidence !== null && selectedSource.confidence !== undefined">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Initial Confidence:</span>
                    <span :class="[
                      'px-2 py-0.5 rounded text-xs font-medium ml-2',
                      selectedSource.confidence >= 0.7 ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' :
                      selectedSource.confidence >= 0.4 ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400' :
                      'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                    ]">
                      {{ (selectedSource.confidence * 100).toFixed(0) }}%
                    </span>
                  </div>
                </div>
              </div>

              <!-- Verification Status -->
              <div v-if="selectedSource && selectedSource.slug_retrieved !== null && selectedSource.slug_retrieved !== undefined" class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">Verification Status</h3>
                <div class="space-y-2 text-sm">
                  <div>
                    <span class="font-medium text-gray-700 dark:text-gray-300">Slug Retrieved:</span>
                    <span :class="selectedSource.slug_retrieved ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'" class="ml-2">
                      {{ selectedSource.slug_retrieved ? '✅ Yes' : '❌ No' }}
                    </span>
                  </div>
                  <div v-if="selectedSource.slug_retrieved">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Verification Status:</span>
                    <span :class="selectedSource.verification_status && ['exactly_found', 'paraphrase_or_similar', 'partially_found'].includes(selectedSource.verification_status) ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'" class="ml-2">
                      {{ selectedSource.verification_status ? selectedSource.verification_status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'Not verified' }}
                    </span>
                  </div>
                  <div v-if="selectedSource.verification_confidence !== null && selectedSource.verification_confidence !== undefined">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Verification Confidence:</span>
                    <span :class="[
                      'px-2 py-0.5 rounded text-xs font-medium ml-2',
                      selectedSource.verification_confidence >= 0.7 ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400' :
                      selectedSource.verification_confidence >= 0.4 ? 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-400' :
                      'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-400'
                    ]">
                      {{ (selectedSource.verification_confidence * 100).toFixed(0) }}%
                    </span>
                  </div>
                  <div v-if="selectedSource.verification_explanation">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Explanation:</span>
                    <div class="text-gray-900 dark:text-white mt-1">{{ selectedSource.verification_explanation }}</div>
                  </div>
                  <div v-if="selectedSource.matched_text">
                    <span class="font-medium text-gray-700 dark:text-gray-300">Matched Text:</span>
                    <div class="text-gray-900 dark:text-white italic mt-1">{{ selectedSource.matched_text }}</div>
                  </div>
                </div>
              </div>

              <!-- Sefaria Text -->
              <div v-if="selectedSource && selectedSource.standard_slug" class="bg-gray-50 dark:bg-gray-900 p-4 rounded-lg">
                <div class="flex items-center justify-between mb-3">
                  <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
                    Text from Sefaria ({{ selectedSource.standard_slug }})
                  </h3>
                  <!-- Language toggle -->
                  <div v-if="hasSefariaText && !isLoadingSefaria" class="flex rounded-lg overflow-hidden border border-gray-300 dark:border-gray-600 text-sm">
                    <button
                      @click="sefariaDisplayMode = 'he'"
                      :class="sefariaDisplayMode === 'he' ? 'bg-indigo-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'"
                      class="px-3 py-1 transition-colors font-medium"
                    >{{ t('lessons.sefariaHebrew') }}</button>
                    <button
                      @click="sefariaDisplayMode = 'both'"
                      :class="sefariaDisplayMode === 'both' ? 'bg-indigo-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'"
                      class="px-3 py-1 transition-colors border-l border-r border-gray-300 dark:border-gray-600 font-medium"
                    >{{ t('lessons.sefariaHebrewEnglish') }}</button>
                    <button
                      @click="sefariaDisplayMode = 'en'"
                      :class="sefariaDisplayMode === 'en' ? 'bg-indigo-600 text-white' : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'"
                      class="px-3 py-1 transition-colors font-medium"
                    >{{ t('lessons.sefariaEnglish') }}</button>
                  </div>
                </div>

                <div v-if="isLoadingSefaria" class="text-center py-4">
                  <div class="text-gray-500 dark:text-gray-400">Loading...</div>
                </div>

                <!-- Single language mode (Hebrew or English) -->
                <div v-else-if="hasSefariaText && sefariaDisplayMode !== 'both'" class="prose prose-sm dark:prose-invert max-w-none">
                  <div 
                    class="leading-relaxed whitespace-pre-wrap max-h-96 overflow-auto"
                    :class="sefariaDisplayMode === 'he' ? 'text-right text-gray-900 dark:text-gray-100' : 'text-gray-900 dark:text-gray-100'"
                    :dir="sefariaDisplayMode === 'he' ? 'rtl' : 'ltr'"
                    v-html="selectedSource && selectedSource.matched_text ? highlightMatchedText(sefariaDisplayText, selectedSource.matched_text as string) : sefariaDisplayText"
                  ></div>
                </div>

                <!-- Interleaved Hebrew + English mode -->
                <div v-else-if="hasSefariaText && sefariaDisplayMode === 'both'" class="max-h-96 overflow-auto">
                  <div
                    v-for="(pair, idx) in sefariaInterleavedLines"
                    :key="idx"
                    class="mb-3 pb-3"
                    :class="idx < sefariaInterleavedLines.length - 1 ? 'border-b border-gray-200 dark:border-gray-700' : ''"
                  >
                    <!-- Hebrew line -->
                    <div
                      v-if="pair.he"
                      dir="rtl"
                      class="text-right text-gray-900 dark:text-gray-100 leading-relaxed text-base mb-1"
                      v-html="selectedSource && selectedSource.matched_text ? highlightMatchedText(pair.he, selectedSource.matched_text as string) : pair.he"
                    ></div>
                    <!-- English line -->
                    <div
                      v-if="pair.en"
                      class="text-gray-600 dark:text-gray-400 leading-relaxed text-sm italic"
                      v-html="selectedSource && selectedSource.matched_text ? highlightMatchedText(pair.en, selectedSource.matched_text as string) : pair.en"
                    ></div>
                  </div>
                </div>

                <div v-else class="text-gray-500 dark:text-gray-400 italic">
                  No text available
                </div>
              </div>
            </div>
            
            <div class="mt-6 flex justify-end">
              <button
                @click="showSourceModal = false"
                class="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
              >
                {{ t('lessons.close') }}
              </button>
            </div>
          </div>
        </DialogPanel>
      </div>
    </Dialog>

    <!-- Source Stats Modal -->
    <Dialog
      :open="showSourceStatsModal"
      @close="showSourceStatsModal = false"
      class="relative z-50"
    >
      <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel class="w-full max-w-4xl bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-h-[90vh] overflow-auto">
          <div class="p-6">
            <DialogTitle class="text-2xl font-bold text-gray-900 dark:text-white mb-6 pb-4 border-b border-gray-200 dark:border-gray-700">
              {{ t('lessons.sourceStatistics') }}
            </DialogTitle>
            
            <div class="space-y-6">
            <!-- Total Statistics -->
            <div class="bg-indigo-50 dark:bg-indigo-900/20 p-4 rounded-lg border border-indigo-200 dark:border-indigo-800">
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('lessons.totalStatistics') }}
              </h3>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div class="text-center">
                  <div class="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
                    {{ totalStats.total }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.totalSources') }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-2xl font-bold text-blue-600 dark:text-blue-400">
                    {{ totalStats.slugRetrieved }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.slugRetrieved') }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-2xl font-bold text-green-600 dark:text-green-400">
                    {{ totalStats.citationFound }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.citationFound') }}
                  </div>
                </div>
                <div class="text-center">
                  <div class="text-2xl font-bold text-emerald-600 dark:text-emerald-400">
                    {{ totalStats.checked }}
                  </div>
                  <div class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {{ t('lessons.checked') }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Statistics by Type -->
            <div>
              <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('lessons.statisticsByType') }}
              </h3>
              <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead class="bg-gray-50 dark:bg-gray-900">
                    <tr>
                      <th class="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.type') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.total') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.slugRetrieved') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.citationFound') }}
                      </th>
                      <th class="px-4 py-3 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        {{ t('lessons.checked') }}
                      </th>
                    </tr>
                  </thead>
                  <tbody class="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    <tr
                      v-for="stats in sourceStats"
                      :key="stats.type"
                      class="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                    >
                      <td class="px-4 py-3 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                        {{ stats.type }}
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-gray-700 dark:text-gray-300">
                        {{ stats.total }}
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-blue-600 dark:text-blue-400">
                        {{ stats.slugRetrieved }}
                        <span v-if="stats.total > 0" class="text-xs text-gray-500 dark:text-gray-400 ml-1">
                          ({{ ((stats.slugRetrieved / stats.total) * 100).toFixed(0) }}%)
                        </span>
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-green-600 dark:text-green-400">
                        {{ stats.citationFound }}
                        <span v-if="stats.total > 0" class="text-xs text-gray-500 dark:text-gray-400 ml-1">
                          ({{ ((stats.citationFound / stats.total) * 100).toFixed(0) }}%)
                        </span>
                      </td>
                      <td class="px-4 py-3 whitespace-nowrap text-sm text-center text-emerald-600 dark:text-emerald-400">
                        {{ stats.checked }}
                        <span v-if="stats.total > 0" class="text-xs text-gray-500 dark:text-gray-400 ml-1">
                          ({{ ((stats.checked / stats.total) * 100).toFixed(0) }}%)
                        </span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            </div>
            
            <div class="mt-6 flex justify-end">
              <button
                @click="showSourceStatsModal = false"
                class="px-4 py-2 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-300 rounded-lg transition-colors"
              >
                {{ t('lessons.close') }}
              </button>
            </div>
          </div>
        </DialogPanel>
      </div>
    </Dialog>

    <!-- Draft Restore Dialog -->
    <Dialog
      :open="showDraftRestoreDialog"
      @close="handleDraftRestoreDecision(false)"
      class="relative z-[60]"
    >
      <div class="fixed inset-0 bg-black/40" aria-hidden="true" />
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <DialogPanel class="w-full max-w-md rounded-xl bg-white dark:bg-gray-800 shadow-2xl">
          <div class="px-6 py-5">
            <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ draftRestoreTitle }}
            </DialogTitle>
            <p class="mt-2 text-sm text-gray-600 dark:text-gray-300">
              {{ draftRestoreMessage }}
            </p>
            <div class="mt-6 flex items-center justify-end gap-3">
              <button
                @click="handleDraftRestoreDecision(false)"
                class="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              >
                {{ t('lessons.startFromServerVersion') }}
              </button>
              <button
                @click="handleDraftRestoreDecision(true)"
                class="inline-flex items-center px-4 py-2 rounded-md text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition-colors"
              >
                {{ t('lessons.restoreDraft') }}
              </button>
            </div>
          </div>
        </DialogPanel>
      </div>
    </Dialog>

    <!-- Summary Editor Page -->
    <div
      v-if="isEditingSummary"
      class="fixed inset-0 z-50 bg-white dark:bg-gray-900 flex flex-col"
    >
      <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white">
          {{ t('lessons.modifySummary') }}
        </h2>
        <button
          @click="closeSummaryEditorPage"
          :disabled="isSavingSummary"
          class="inline-flex items-center justify-center p-2 rounded-md text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 disabled:opacity-50"
        >
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>

      <div
        v-if="isSavingSummary"
        class="mx-6 mt-4 px-3 py-2 text-sm text-indigo-800 dark:text-indigo-200 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-800 rounded-md"
      >
        {{ t('lessons.savingAndRealigningSummary') }}
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        <MilkdownEditor
          v-model="editedSummary"
          placeholder="Enter summary in markdown format..."
          :disabled="isSavingSummary"
        />
      </div>

      <div class="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
        <div class="flex items-center justify-end gap-3">
          <button
            @click="cancelEditSummary"
            :disabled="isSavingSummary"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded-md transition-colors"
          >
            <XMarkIcon class="h-4 w-4" />
            {{ t('lessons.cancel') }}
          </button>
          <button
            @click="saveSummary"
            :disabled="isSavingSummary"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
          >
            <CheckIcon class="h-4 w-4" />
            {{ isSavingSummary ? t('lessons.saving') : t('lessons.save') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Edited Markdown Editor Page -->
    <div
      v-if="isEditingEditedMarkdown"
      class="fixed inset-0 z-50 bg-white dark:bg-gray-900 flex flex-col"
    >
      <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white">
          {{ t('lessons.modifyEdited') }}
        </h2>
        <button
          @click="closeEditedMarkdownEditorPage"
          :disabled="isSavingEditedMarkdown"
          class="inline-flex items-center justify-center p-2 rounded-md text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 disabled:opacity-50"
        >
          <XMarkIcon class="h-5 w-5" />
        </button>
      </div>

      <div
        v-if="isSavingEditedMarkdown"
        class="mx-6 mt-4 px-3 py-2 text-sm text-indigo-800 dark:text-indigo-200 bg-indigo-50 dark:bg-indigo-900/30 border border-indigo-200 dark:border-indigo-800 rounded-md"
      >
        {{ t('lessons.savingAndRealigning') }}
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        <MilkdownEditor
          v-model="editedMarkdownDraft"
          placeholder="Enter edited transcript in markdown format..."
          :disabled="isSavingEditedMarkdown"
        />
      </div>

      <div class="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-6 py-4">
        <div class="flex items-center justify-end gap-3">
          <button
            @click="cancelEditEditedMarkdown"
            :disabled="isSavingEditedMarkdown"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-50 rounded-md transition-colors"
          >
            <XMarkIcon class="h-4 w-4" />
            {{ t('lessons.cancel') }}
          </button>
          <button
            @click="saveEditedMarkdown"
            :disabled="isSavingEditedMarkdown"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
          >
            <CheckIcon class="h-4 w-4" />
            {{ isSavingEditedMarkdown ? t('lessons.saving') : t('lessons.save') }}
          </button>
        </div>
      </div>
    </div>

    <LessonDocumentModal
      :is-open="showLessonDocumentModal"
      :mode="lessonDocumentMode"
      :view-type="lessonDocumentView"
      :submitting="isSubmittingLessonDocument"
      :default-format="defaultLessonExportFormat"
      :default-fields="defaultLessonExportFields"
      @close="closeLessonDocumentModal"
      @export="handleLessonExport"
      @import="handleLessonImport"
    />
  </div>
</template>

<style>
.lesson-audio-player {
  color-scheme: light;
}

.lesson-audio-player::-webkit-media-controls-enclosure {
  background-color: rgb(255 255 255);
}

.lesson-audio-player::-webkit-media-controls-panel {
  background-color: rgb(255 255 255);
}

.dark .lesson-audio-player {
  color-scheme: dark;
}

.dark .lesson-audio-player::-webkit-media-controls-enclosure {
  background-color: rgb(31 41 55);
  border-radius: 9999px;
}

.dark .lesson-audio-player::-webkit-media-controls-panel {
  background-color: rgb(31 41 55);
}
</style>

