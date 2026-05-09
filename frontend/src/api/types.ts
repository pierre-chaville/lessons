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
  parent_id: number | null
  sort_order: number
  lessons?: LessonListItem[]
}

export interface CourseTreeNode {
  id: number
  hashid: string
  name: string
  description: string | null
  parent_id: number | null
  sort_order: number
  lesson_count: number
  children: CourseTreeNode[]
}

export interface CourseCreate {
  name: string
  description?: string | null
  parent_id?: number | null
}

export interface CourseUpdate {
  name?: string
  description?: string | null
  parent_id?: number | null
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
  edition_done?: boolean
  sources_done?: boolean
  summary_done?: boolean
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

// ── Versioning / Audit ───────────────────────────────────────────────────────

export type ContentType =
  | 'title'
  | 'corrected_transcript'
  | 'edited_transcript'
  | 'brief'
  | 'summary'

export type VersionSource = 'human' | 'pipeline' | 'restore'

export interface LessonVersion {
  id: string
  lesson_id: number
  content_type: ContentType
  version_number: number
  version_source: VersionSource
  created_at: string
  last_edited_at: string | null
  edit_count: number
  is_sealed: boolean
  sealed_at: string | null
  sealed_reason: string | null
  created_by_id: string | null
  change_summary: string | null
  parent_version_id: string | null
  restored_from_id: string | null
  is_current: boolean
  content?: unknown
}

export interface StructuredSegmentDiff {
  segment_index: number
  status: 'unchanged' | 'added' | 'removed' | 'modified'
  text_diff: string
}

export type VersionDiffResponse =
  | { type: 'text'; diff: string }
  | { type: 'structured'; segments: StructuredSegmentDiff[] }

export interface AuditLogRow {
  id: number
  occurred_at: string
  actor_id: string | null
  actor_role: string
  entity_type: string
  entity_id: string
  action: string
  payload: Record<string, unknown>
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

// ── Booklets ──────────────────────────────────────────────────────────────────

export type BookletStatus = 'draft' | 'ready' | 'archived'
export type BookletItemType = 'lesson' | 'chapter'

export type BookletTemplateField =
  | 'title'
  | 'date'
  | 'duration'
  | 'corrected_transcript'
  | 'edited_transcript'
  | 'brief'
  | 'summary'
  | 'status'
  | 'themes'
  | 'course'

export interface Booklet {
  id: number
  title: string
  subtitle: string | null
  description: string | null
  status: BookletStatus
  cover_metadata: Record<string, unknown>
  template_data: BookletTemplateField[]
  template: string
  course_id: number | null
  created_at: string
  updated_at: string
  created_by_id: string | null
}

export interface BookletItem {
  id: number
  booklet_id: number
  position: number
  item_type: BookletItemType
  lesson_id: number | null
  custom_title: string | null
  custom_intro: string | null
  include_brief: boolean
  chapter_title: string | null
  chapter_subtitle: string | null
  chapter_body: string | null
  chapter_starts_new_page: boolean
  is_included: boolean
  added_at: string
  added_by_id: string | null
  lesson_title: string | null
  lesson_status: string | null
}

export interface BookletLessonItem {
  id: number
  booklet_id: number
  lesson_id: number
  position: number
  custom_title: string | null
  custom_intro: string | null
  include_brief: boolean
  is_included: boolean
  added_at: string
  added_by_id: string | null
  lesson_title: string | null
  lesson_status: string | null
}

export interface BookletDetail extends Booklet {
  items: BookletItem[]
  lessons: BookletLessonItem[]
}

export interface BookletListResponse {
  items: Booklet[]
  total: number
  offset: number
  limit: number
}

export interface BookletCreate {
  title: string
  subtitle?: string | null
  description?: string | null
  cover_metadata?: Record<string, unknown>
  template_data?: BookletTemplateField[]
  template?: string
  course_id?: number | null
}

export interface BookletUpdate {
  title?: string
  subtitle?: string | null
  description?: string | null
  cover_metadata?: Record<string, unknown>
  template_data?: BookletTemplateField[]
  template?: string
  course_id?: number | null
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

export interface SummaryConfig {
  prompts: SummaryPromptConfig[]
}

export interface EditionPromptConfig {
  name: string
  text: string
  model_preset_id: number | null
  max_tokens: number
}

export interface EditionConfig {
  prompts: EditionPromptConfig[]
}

export interface CorrectionPromptConfig {
  name: string
  text: string
  model_preset_id: number | null
  max_tokens: number
}

export interface CorrectionConfig {
  prompts: CorrectionPromptConfig[]
}

export interface ExtractionPromptConfig {
  name: string
  text: string
  model_preset_id: number | null
  max_tokens: number
}

export interface ExtractionConfig {
  prompts: ExtractionPromptConfig[]
}

export interface SourcesPromptConfig {
  name: string
  text: string
  model_preset_id: number | null
  max_tokens: number
}

export interface SourcesConfig {
  prompts: SourcesPromptConfig[]
}

export interface BriefConfig {
  model_preset_id: number | null
  max_tokens: number
  prompt: string
}

export interface SummaryPromptConfig {
  name: string
  text: string
  model_preset_id: number | null
  max_length: number
}

export interface TranscribeConfig {
  model: string
  language: string
}

export interface AppConfig {
  correction: CorrectionConfig
  edition: EditionConfig
  extraction: ExtractionConfig
  sources: SourcesConfig
  source_types: Record<string, string>
  summary: SummaryConfig
  brief: BriefConfig
  transcribe: TranscribeConfig
}

export interface ModelPreset {
  id: number
  name: string
  provider: string
  model_id: string
  temperature: number
  cost_input_per_m_tokens: number
  cost_output_per_m_tokens: number
  thinking_mode: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ModelPresetCreate {
  name: string
  provider: string
  model_id: string
  temperature: number
  cost_input_per_m_tokens: number
  cost_output_per_m_tokens: number
  thinking_mode: Record<string, unknown>
}

export interface ModelPresetUpdate {
  name?: string
  provider?: string
  model_id?: string
  temperature?: number
  cost_input_per_m_tokens?: number
  cost_output_per_m_tokens?: number
  thinking_mode?: Record<string, unknown>
}
