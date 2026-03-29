/**
 * TypeScript interfaces mirroring the FastAPI backend response schemas.
 * Field names use snake_case as returned by the API — no transformation.
 */

// ── Shared sub-types ──────────────────────────────────────────────────────────

export interface Source {
  type: string | null
  work: string | null
  ref: string | null
  standard_slug: string | null
  original_text: string | null
  translation_text: string | null
  cited_excerpt: string | null
  confidence: number | null
  slug_retrieved: boolean | null
  verification_status:
    | 'exactly_found'
    | 'paraphrase_or_similar'
    | 'partially_found'
    | 'not_found'
    | 'reference_exists_but_text_differs'
    | null
  verification_confidence: number | null
  verification_explanation: string | null
  matched_text: string | null
}

/** Source row from the lesson_source table, linked to a specific lesson & paragraph. */
export interface LessonSource extends Source {
  id: number
  lesson_id: number
  paragraph_index: number
}

export interface Segment {
  start: number
  end: number
  text: string
}

export interface EditedParagraph {
  start: number
  end: number
  text: string
  sources?: Source[]  // kept for backward compat but may be empty
}

// ── Course ────────────────────────────────────────────────────────────────────

export interface Course {
  id: number
  hashid: string
  name: string
  description: string | null
  lessons?: LessonListItem[]
}

export interface CourseCreate {
  name: string
  description?: string | null
}

export interface CourseUpdate {
  name?: string
  description?: string | null
}

// ── Theme ─────────────────────────────────────────────────────────────────────

export interface Theme {
  id: number
  hashid: string
  name: string
}

export interface ThemeCreate {
  name: string
}

export interface ThemeUpdate {
  name?: string
}

// ── Lesson ────────────────────────────────────────────────────────────────────

export type LessonStatus = 'draft' | 'in_progress' | 'review_requested' | 'revision_requested' | 'validated'

export interface LessonEditorAssignment {
  user_id: string
  assigned_at: string
  assigned_by: string | null
}

/** Lightweight shape returned by GET /lessons (list view). */
export interface LessonListItem {
  id: number
  hashid: string
  title: string
  date: string
  duration: number | null
  brief: string | null
  status: LessonStatus
  process_status: string | null
  filename: string
  themes: Theme[]
  course: Course | null
  editors: LessonEditorAssignment[]
}

/** Full shape returned by GET /lessons/:hashid. */
export interface LessonDetail {
  id: number
  hashid: string
  title: string
  filename: string
  course_id: number | null
  date: string
  duration: number | null
  transcript: Segment[] | null
  corrected_transcript: Segment[] | null
  edited_transcript: EditedParagraph[] | null
  brief: string | null
  summary: string | null
  status: LessonStatus
  process_status: string | null
  theme_ids: number[]
  themes: Theme[]
  course: Course | null
  sources: LessonSource[]
  editors: LessonEditorAssignment[]
  transcript_metadata: Record<string, unknown> | null
  correction_metadata: Record<string, unknown> | null
  summary_metadata: Record<string, unknown> | null
  edited_metadata: Record<string, unknown> | null
}

export interface LessonCreate {
  title: string
  filename: string
  course_id?: number | null
  date?: string | null
  duration?: number | null
  theme_ids?: number[] | null
  editor_ids?: string[] | null
}

export interface LessonUpdate {
  title?: string
  filename?: string
  course_id?: number | null
  date?: string | null
  duration?: number | null
  transcript?: Segment[] | null
  corrected_transcript?: Segment[] | null
  edited_transcript?: EditedParagraph[] | null
  brief?: string | null
  summary?: string | null
  process_status?: string | null
  theme_ids?: number[] | null
  editor_ids?: string[] | null
  transcript_metadata?: Record<string, unknown> | null
  correction_metadata?: Record<string, unknown> | null
  summary_metadata?: Record<string, unknown> | null
  edited_metadata?: Record<string, unknown> | null
}

/** Response from GET /lessons/:hashid/audio-url */
export interface AudioUrlResponse {
  url: string
}

// ── Upload ────────────────────────────────────────────────────────────────────

/** Response from POST /upload/audio */
export interface UploadAudioResponse {
  filename: string
  original_filename: string
}

// ── Task ──────────────────────────────────────────────────────────────────────

export type TaskType =
  | 'transcription'
  | 'correction'
  | 'edition'
  | 'extraction'
  | 'sources'
  | 'summary'

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface Task {
  id: number
  task_type: TaskType
  status: TaskStatus
  start_date: string | null
  end_date: string | null
  duration: number | null
  parameters: Record<string, unknown> | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
}

export interface TaskCreate {
  task_type: TaskType
  parameters?: Record<string, unknown> | null
}

// ── Search ────────────────────────────────────────────────────────────────────

export interface SearchMatchSegment {
  start: number
  end: number
  text: string
  score: number
  exact: boolean
}

export interface SearchLessonResult {
  id: number
  hashid: string
  title: string
  date: string
  duration: number | null
  brief: string | null
  filename: string
  themes: Theme[]
  course: Course | null
  matches: SearchMatchSegment[]
  match_count: number
  best_score: number
}

export interface SearchParams {
  q: string
  course_id?: number
  theme_id?: number
}

// ── Config ────────────────────────────────────────────────────────────────────

export interface LLMConfig {
  provider: string
  model: string
  prompt: string
  prompts?: NamedPrompt[]
  temperature: number
  max_tokens: number
}

export interface NamedPrompt {
  name: string
  text: string
}

/** @deprecated Use NamedPrompt instead */
export type SummaryPrompt = NamedPrompt

export interface SummaryConfig {
  provider: string
  model: string
  prompt: string
  temperature: number
  max_tokens: number
  max_length: number
  prompts: NamedPrompt[]
  brief: LLMConfig
}

export interface WhisperConfig {
  compute_type: string
  device: string
  model_size: string
}

export interface TranscribeConfig {
  beam_size: number
  initial_prompt: string
  language: string
  vad_filter: boolean
}

export interface AppConfig {
  correction: LLMConfig
  edition: LLMConfig
  extraction: LLMConfig
  sources: LLMConfig
  source_types: Record<string, string>
  summary: SummaryConfig
  transcribe: TranscribeConfig
  whisper: WhisperConfig
}
