<script setup lang="ts">
import { ref, onMounted, nextTick, watch, onBeforeUnmount } from 'vue'
import { useI18n } from 'vue-i18n'
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/vue'
import {
  CogIcon,
  MicrophoneIcon,
  PencilIcon,
  DocumentTextIcon,
  BookOpenIcon,
  MagnifyingGlassIcon,
  TrashIcon,
  ClockIcon,
} from '@heroicons/vue/24/outline'
import { configApi } from '@/api/config'
import { modelPresetsApi } from '@/api/modelPresets'
import { usePermissions } from '@/composables/usePermissions'
import type { AppConfig, ModelPreset } from '@/api/types'
import MilkdownEditor from '@/components/MilkdownEditor.vue'
import PreferenceVersionHistoryPanel from '@/components/PreferenceVersionHistoryPanel.vue'
import { marked } from 'marked'
import { parse, stringify } from 'yaml'

const { t } = useI18n()
const { can } = usePermissions()
const DEFAULT_RAG_LLM_PROMPT = `You are an AI assistant for a corpus of Torah lessons.

Answer the user's question using only the provided lesson excerpts. If the excerpts do not contain enough information, say so clearly.

When you use information from an excerpt, cite it inline with its bracket number, for example [1] or [2]. Write the answer in the same language as the user's question.

Question:
{question}

Lesson excerpts:
{context}
`

const config = ref<AppConfig>({
  correction: {
    prompts: [{ name: 'Default', text: '', model_preset_id: null, max_tokens: 16000 }],
  },
  edition: {
    prompts: [{ name: 'Default', text: '', model_preset_id: null, max_tokens: 16000 }],
  },
  extraction: {
    prompts: [{ name: 'Default', text: '', model_preset_id: null, max_tokens: 4000 }],
  },
  sources: {
    prompts: [{ name: 'Default', text: '', model_preset_id: null, max_tokens: 4000 }],
  },
  source_types: {},
  summary: {
    prompts: [{ name: 'Default', text: '', model_preset_id: null, max_tokens: 1200 }],
  },
  brief: { model_preset_id: null, max_tokens: 1000, prompt: '' },
  transcribe: {
    model: 'nova-3',
    language: 'fr',
    audience_segment_prefix: '[audience]',
  },
  alignment: {
    edited_min_score: 0.2,
    summary_min_score: 0.2,
  },
  rag: {
    chunk_target_chars: 1100,
    chunk_max_chars: 1500,
    embedding_model: 'google/gemini-embedding-001',
    retrieval_k: 40,
    full_text_search_k: 40,
    reranking_model: 'cohere/rerank-4-pro',
    reranking_top_n: 8,
    llm_model: 'openai/gpt-5.4',
    llm_prompt: DEFAULT_RAG_LLM_PROMPT,
  },
})

const isLoading = ref(true)
const isSaving = ref(false)
const saveMessage = ref('')
const saveError = ref('')
const AUTO_SAVE_DEBOUNCE_MS = 1000
let autoSaveTimeout: ReturnType<typeof setTimeout> | null = null
let autoSaveMessageTimeout: ReturnType<typeof setTimeout> | null = null
const isConfigInitialized = ref(false)
const isHydratingConfig = ref(false)
const hasPendingAutoSave = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)
const modelPresets = ref<ModelPreset[]>([])
type PromptGroupKey = 'correction' | 'edition' | 'extraction' | 'sources' | 'summary'
type PromptEditorTarget = { kind: 'brief' } | { kind: 'rag' } | { kind: 'group'; group: PromptGroupKey; index: number }

const isPromptEditorOpen = ref(false)
const promptEditorTitle = ref('')
const promptEditorDraft = ref('')
const promptEditorTarget = ref<PromptEditorTarget | null>(null)
const promptEditorMode = ref<'visual' | 'markdown'>('visual')
const expandedPromptPreviews = ref<Record<string, boolean>>({})
const isHistoryOpen = ref(false)
const selectedPreferenceVersionId = ref<string | null>(null)
const activePreferenceCompare = ref<{
  versionAId: string
  versionBId: string
  fromVersionNumber?: number | null
  toVersionNumber?: number | null
} | null>(null)

const renderMarkdown = (markdown: string | null | undefined): string => {
  if (!markdown) return ''
  return marked(markdown) as string
}

const promptPreviewKey = (group: PromptGroupKey | 'brief' | 'rag', index?: number): string => {
  if (group === 'brief') return 'brief'
  if (group === 'rag') return 'rag'
  return `${group}-${index ?? 0}`
}

const isPromptPreviewLong = (text: string | null | undefined): boolean => {
  if (!text) return false
  return text.split(/\r?\n/).length > 3
}

const isPromptPreviewExpanded = (group: PromptGroupKey | 'brief' | 'rag', index?: number): boolean => {
  return !!expandedPromptPreviews.value[promptPreviewKey(group, index)]
}

const togglePromptPreview = (group: PromptGroupKey | 'brief' | 'rag', index?: number) => {
  const key = promptPreviewKey(group, index)
  expandedPromptPreviews.value[key] = !expandedPromptPreviews.value[key]
}

const normalizeConfigShape = () => {
  if (!config.value.transcribe) {
    config.value.transcribe = {
      model: 'nova-3',
      language: 'fr',
      audience_segment_prefix: '[audience]',
    }
  }
  if (!config.value.transcribe.model) config.value.transcribe.model = 'nova-3'
  if (!config.value.transcribe.language) config.value.transcribe.language = 'fr'
  if (!config.value.transcribe.audience_segment_prefix) {
    if (config.value.transcribe.removed_audience_segment_text) {
      config.value.transcribe.audience_segment_prefix = config.value.transcribe.removed_audience_segment_text
    } else {
      config.value.transcribe.audience_segment_prefix = '[audience]'
    }
  }
  if (!config.value.alignment) {
    config.value.alignment = { edited_min_score: 0.2, summary_min_score: 0.2 }
  }
  if (typeof config.value.alignment.edited_min_score !== 'number') {
    config.value.alignment.edited_min_score = 0.2
  }
  if (typeof config.value.alignment.summary_min_score !== 'number') {
    config.value.alignment.summary_min_score = 0.2
  }
  config.value.alignment.edited_min_score = Math.max(0, Math.min(1, config.value.alignment.edited_min_score))
  config.value.alignment.summary_min_score = Math.max(0, Math.min(1, config.value.alignment.summary_min_score))
  if (!config.value.rag) {
    config.value.rag = {
      chunk_target_chars: 1100,
      chunk_max_chars: 1500,
      embedding_model: 'google/gemini-embedding-001',
      retrieval_k: 40,
      full_text_search_k: 40,
      reranking_model: 'cohere/rerank-4-pro',
      reranking_top_n: 8,
      llm_model: 'openai/gpt-5.4',
      llm_prompt: DEFAULT_RAG_LLM_PROMPT,
    }
  }
  const rag = config.value.rag
  if (typeof rag.chunk_target_chars !== 'number') rag.chunk_target_chars = 1100
  if (typeof rag.chunk_max_chars !== 'number') rag.chunk_max_chars = 1500
  if (typeof rag.retrieval_k !== 'number') rag.retrieval_k = 40
  if (typeof rag.full_text_search_k !== 'number') rag.full_text_search_k = 40
  if (typeof rag.reranking_top_n !== 'number') rag.reranking_top_n = 8
  rag.chunk_target_chars = Math.max(1, Math.floor(rag.chunk_target_chars))
  rag.chunk_max_chars = Math.max(rag.chunk_target_chars, Math.floor(rag.chunk_max_chars))
  rag.retrieval_k = Math.max(1, Math.floor(rag.retrieval_k))
  rag.full_text_search_k = Math.max(1, Math.floor(rag.full_text_search_k))
  rag.reranking_top_n = Math.max(1, Math.min(rag.retrieval_k + rag.full_text_search_k, Math.floor(rag.reranking_top_n)))
  if (!rag.embedding_model?.trim()) rag.embedding_model = 'google/gemini-embedding-001'
  if (!rag.reranking_model?.trim()) rag.reranking_model = 'cohere/rerank-4-pro'
  if (!rag.llm_model?.trim()) rag.llm_model = 'openai/gpt-5.4'
  if (!rag.llm_prompt?.trim()) rag.llm_prompt = DEFAULT_RAG_LLM_PROMPT
  if (!config.value.brief) config.value.brief = { model_preset_id: null, max_tokens: 1000, prompt: '' }
  // Backward compatibility: migrate legacy summary.brief to top-level brief.
  const summaryWithLegacyBrief = config.value.summary as typeof config.value.summary & {
    brief?: {
      model_preset_id?: number | null
      max_tokens?: number
      prompt?: string
      provider?: string
      model?: string
      temperature?: number
    }
  }
  if (!config.value.brief.prompt && summaryWithLegacyBrief.brief) {
    config.value.brief = {
      model_preset_id:
        typeof summaryWithLegacyBrief.brief.model_preset_id === 'number'
          ? summaryWithLegacyBrief.brief.model_preset_id
          : null,
      max_tokens:
        typeof summaryWithLegacyBrief.brief.max_tokens === 'number'
          ? summaryWithLegacyBrief.brief.max_tokens
          : 1000,
      prompt: summaryWithLegacyBrief.brief.prompt ?? '',
    }
  }
  if (summaryWithLegacyBrief.brief) {
    delete summaryWithLegacyBrief.brief
  }
  const briefWithLegacyFields = config.value.brief as typeof config.value.brief & {
    provider?: string
    model?: string
    temperature?: number
  }
  if (typeof config.value.brief.model_preset_id !== 'number') {
    config.value.brief.model_preset_id = null
  }
  if (typeof config.value.brief.max_tokens !== 'number') {
    config.value.brief.max_tokens = 1000
  }
  if (typeof config.value.brief.prompt !== 'string') {
    config.value.brief.prompt = ''
  }
  delete briefWithLegacyFields.provider
  delete briefWithLegacyFields.model
  delete briefWithLegacyFields.temperature
  const legacySummaryMaxTokens =
    typeof (config.value.summary as { max_tokens?: unknown }).max_tokens === 'number'
      ? (config.value.summary as { max_tokens: number }).max_tokens
      : typeof (config.value.summary as { max_length?: unknown }).max_length === 'number'
        ? (config.value.summary as { max_length: number }).max_length * 4
        : 1200
  if (!config.value.summary.prompts || config.value.summary.prompts.length === 0) {
    config.value.summary.prompts = [{ name: 'Default', text: '', model_preset_id: null, max_tokens: legacySummaryMaxTokens }]
  } else {
    config.value.summary.prompts = config.value.summary.prompts.map((prompt) => ({
      ...prompt,
      model_preset_id:
        typeof prompt.model_preset_id === 'number' ? prompt.model_preset_id : null,
      max_tokens:
        typeof prompt.max_tokens === 'number'
          ? prompt.max_tokens
          : typeof (prompt as { max_length?: unknown }).max_length === 'number'
            ? ((prompt as { max_length: number }).max_length * 4)
            : legacySummaryMaxTokens,
    }))
  }
  // Remove legacy summary-level model settings now replaced by prompt-level presets.
  const summaryWithLegacyFields = config.value.summary as typeof config.value.summary & {
    provider?: string
    model?: string
    temperature?: number
    max_tokens?: number
    prompt?: string
    max_length?: number
  }
  delete summaryWithLegacyFields.provider
  delete summaryWithLegacyFields.model
  delete summaryWithLegacyFields.temperature
  delete summaryWithLegacyFields.max_tokens
  delete summaryWithLegacyFields.prompt
  delete summaryWithLegacyFields.max_length
  if (!config.value.source_types) config.value.source_types = {}
  const legacyExtractionMaxTokens =
    typeof (config.value.extraction as { max_tokens?: unknown }).max_tokens === 'number'
      ? (config.value.extraction as { max_tokens: number }).max_tokens
      : 4000
  if (!config.value.extraction.prompts || config.value.extraction.prompts.length === 0) {
    const legacyExtractionPrompt = (config.value.extraction as { prompt?: unknown }).prompt
    config.value.extraction.prompts = [{
      name: 'Default',
      text: typeof legacyExtractionPrompt === 'string' ? legacyExtractionPrompt : '',
      model_preset_id: null,
      max_tokens: legacyExtractionMaxTokens,
    }]
  } else {
    config.value.extraction.prompts = config.value.extraction.prompts.map((prompt) => ({
      ...prompt,
      model_preset_id:
        typeof prompt.model_preset_id === 'number' ? prompt.model_preset_id : null,
      max_tokens:
        typeof prompt.max_tokens === 'number' ? prompt.max_tokens : legacyExtractionMaxTokens,
    }))
  }
  const extractionWithLegacyFields = config.value.extraction as typeof config.value.extraction & {
    provider?: string
    model?: string
    temperature?: number
    max_tokens?: number
    prompt?: string
  }
  delete extractionWithLegacyFields.provider
  delete extractionWithLegacyFields.model
  delete extractionWithLegacyFields.temperature
  delete extractionWithLegacyFields.max_tokens
  delete extractionWithLegacyFields.prompt

  const legacySourcesMaxTokens =
    typeof (config.value.sources as { max_tokens?: unknown }).max_tokens === 'number'
      ? (config.value.sources as { max_tokens: number }).max_tokens
      : 4000
  if (!config.value.sources.prompts || config.value.sources.prompts.length === 0) {
    const legacySourcesPrompt = (config.value.sources as { prompt?: unknown }).prompt
    config.value.sources.prompts = [{
      name: 'Default',
      text: typeof legacySourcesPrompt === 'string' ? legacySourcesPrompt : '',
      model_preset_id: null,
      max_tokens: legacySourcesMaxTokens,
    }]
  } else {
    config.value.sources.prompts = config.value.sources.prompts.map((prompt) => ({
      ...prompt,
      model_preset_id:
        typeof prompt.model_preset_id === 'number' ? prompt.model_preset_id : null,
      max_tokens:
        typeof prompt.max_tokens === 'number' ? prompt.max_tokens : legacySourcesMaxTokens,
    }))
  }
  const sourcesWithLegacyFields = config.value.sources as typeof config.value.sources & {
    provider?: string
    model?: string
    temperature?: number
    max_tokens?: number
    prompt?: string
  }
  delete sourcesWithLegacyFields.provider
  delete sourcesWithLegacyFields.model
  delete sourcesWithLegacyFields.temperature
  delete sourcesWithLegacyFields.max_tokens
  delete sourcesWithLegacyFields.prompt
  const legacyEditionMaxTokens =
    typeof (config.value.edition as { max_tokens?: unknown }).max_tokens === 'number'
      ? (config.value.edition as { max_tokens: number }).max_tokens
      : 16000
  if (!config.value.edition.prompts || config.value.edition.prompts.length === 0) {
    config.value.edition.prompts = [{ name: 'Default', text: '', model_preset_id: null, max_tokens: legacyEditionMaxTokens }]
  } else {
    config.value.edition.prompts = config.value.edition.prompts.map((prompt) => ({
      ...prompt,
      model_preset_id:
        typeof prompt.model_preset_id === 'number' ? prompt.model_preset_id : null,
      max_tokens:
        typeof prompt.max_tokens === 'number' ? prompt.max_tokens : legacyEditionMaxTokens,
    }))
  }
  const editionWithLegacyFields = config.value.edition as typeof config.value.edition & {
    provider?: string
    model?: string
    temperature?: number
    max_tokens?: number
    prompt?: string
  }
  delete editionWithLegacyFields.provider
  delete editionWithLegacyFields.model
  delete editionWithLegacyFields.temperature
  delete editionWithLegacyFields.max_tokens
  delete editionWithLegacyFields.prompt

  const legacyCorrectionMaxTokens =
    typeof (config.value.correction as { max_tokens?: unknown }).max_tokens === 'number'
      ? (config.value.correction as { max_tokens: number }).max_tokens
      : 16000
  if (!config.value.correction.prompts || config.value.correction.prompts.length === 0) {
    config.value.correction.prompts = [{ name: 'Default', text: '', model_preset_id: null, max_tokens: legacyCorrectionMaxTokens }]
  } else {
    config.value.correction.prompts = config.value.correction.prompts.map((prompt) => ({
      ...prompt,
      model_preset_id:
        typeof prompt.model_preset_id === 'number' ? prompt.model_preset_id : null,
      max_tokens:
        typeof prompt.max_tokens === 'number' ? prompt.max_tokens : legacyCorrectionMaxTokens,
    }))
  }
  const correctionWithLegacyFields = config.value.correction as typeof config.value.correction & {
    provider?: string
    model?: string
    temperature?: number
    max_tokens?: number
    prompt?: string
  }
  delete correctionWithLegacyFields.provider
  delete correctionWithLegacyFields.model
  delete correctionWithLegacyFields.temperature
  delete correctionWithLegacyFields.max_tokens
  delete correctionWithLegacyFields.prompt
}

onMounted(async () => {
  await Promise.all([loadConfig(), loadModelPresets()])
})

onBeforeUnmount(() => {
  if (autoSaveTimeout) clearTimeout(autoSaveTimeout)
  if (autoSaveMessageTimeout) clearTimeout(autoSaveMessageTimeout)
})

const loadConfig = async () => {
  try {
    isLoading.value = true
    isHydratingConfig.value = true
    const data = await configApi.get()
    config.value = data
    normalizeConfigShape()
    isConfigInitialized.value = true
  } catch {
    saveError.value = t('preferences.loadFailed')
  } finally {
    isHydratingConfig.value = false
    isLoading.value = false
  }
}

const loadModelPresets = async () => {
  try {
    modelPresets.value = await modelPresetsApi.list()
  } catch {
    // Keep page functional even when presets cannot be fetched.
    modelPresets.value = []
  }
}

const saveConfig = async (showSuccess = false) => {
  try {
    isSaving.value = true
    saveError.value = ''
    await configApi.update(config.value)
    if (showSuccess) {
      saveMessage.value = t('preferences.saveSuccess')
      if (autoSaveMessageTimeout) clearTimeout(autoSaveMessageTimeout)
      autoSaveMessageTimeout = setTimeout(() => { saveMessage.value = '' }, 3000)
    }
  } catch {
    saveError.value = t('preferences.saveFailed')
  } finally {
    isSaving.value = false
    if (hasPendingAutoSave.value) {
      hasPendingAutoSave.value = false
      queueAutoSave()
    }
  }
}

const openPreferencesHistory = async () => {
  if (autoSaveTimeout) {
    clearTimeout(autoSaveTimeout)
    autoSaveTimeout = null
    await saveConfig()
  }
  selectedPreferenceVersionId.value = null
  activePreferenceCompare.value = null
  isHistoryOpen.value = true
}

const closePreferencesHistory = () => {
  isHistoryOpen.value = false
  selectedPreferenceVersionId.value = null
  activePreferenceCompare.value = null
}

const onPreferencesRestored = async () => {
  await loadConfig()
  saveMessage.value = t('preferences.restoreSuccess')
  if (autoSaveMessageTimeout) clearTimeout(autoSaveMessageTimeout)
  autoSaveMessageTimeout = setTimeout(() => { saveMessage.value = '' }, 3000)
}

const queueAutoSave = () => {
  if (!can('configuration', 'update')) return
  if (!isConfigInitialized.value || isHydratingConfig.value || isLoading.value) return
  if (isSaving.value) {
    hasPendingAutoSave.value = true
    return
  }
  if (autoSaveTimeout) clearTimeout(autoSaveTimeout)
  autoSaveTimeout = setTimeout(async () => {
    autoSaveTimeout = null
    await saveConfig()
  }, AUTO_SAVE_DEBOUNCE_MS)
}

const exportConfigYaml = () => {
  try {
    saveMessage.value = ''
    saveError.value = ''
    const yamlContent = stringify(config.value)
    const blob = new Blob([yamlContent], { type: 'application/x-yaml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'preferences.yaml'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    saveMessage.value = t('preferences.exportSuccess')
    setTimeout(() => { saveMessage.value = '' }, 3000)
  } catch {
    saveError.value = t('preferences.exportFailed')
  }
}

const openImportDialog = () => {
  importInputRef.value?.click()
}

const importConfigYaml = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  try {
    saveMessage.value = ''
    saveError.value = ''
    const yamlContent = await file.text()
    const parsed = parse(yamlContent)
    if (!parsed || typeof parsed !== 'object') {
      throw new Error('Invalid YAML content')
    }

    const importedConfig = parsed as AppConfig
    await configApi.update(importedConfig)
    isHydratingConfig.value = true
    config.value = importedConfig
    normalizeConfigShape()
    isHydratingConfig.value = false
    saveMessage.value = t('preferences.importSuccess')
    if (autoSaveMessageTimeout) clearTimeout(autoSaveMessageTimeout)
    autoSaveMessageTimeout = setTimeout(() => { saveMessage.value = '' }, 3000)
  } catch {
    saveError.value = t('preferences.importFailed')
  } finally {
    isHydratingConfig.value = false
    input.value = ''
  }
}

const addExtractionPrompt = () => {
  config.value.extraction.prompts.push({ name: '', text: '', model_preset_id: null, max_tokens: 4000 })
}

const removeExtractionPrompt = (index: number) => {
  if (config.value.extraction.prompts.length > 1) {
    config.value.extraction.prompts.splice(index, 1)
  }
}

const addSourcesPrompt = () => {
  config.value.sources.prompts.push({ name: '', text: '', model_preset_id: null, max_tokens: 4000 })
}

const removeSourcesPrompt = (index: number) => {
  if (config.value.sources.prompts.length > 1) {
    config.value.sources.prompts.splice(index, 1)
  }
}

const addCorrectionPrompt = () => {
  config.value.correction.prompts.push({ name: '', text: '', model_preset_id: null, max_tokens: 16000 })
}

const removeCorrectionPrompt = (index: number) => {
  if (config.value.correction.prompts.length > 1) {
    config.value.correction.prompts.splice(index, 1)
  }
}

const addSummaryPrompt = () => {
  config.value.summary.prompts.push({ name: '', text: '', model_preset_id: null, max_tokens: 1200 })
}

const removeSummaryPrompt = (index: number) => {
  if (config.value.summary.prompts.length > 1) {
    config.value.summary.prompts.splice(index, 1)
  }
}

const addEditionPrompt = () => {
  config.value.edition.prompts.push({ name: '', text: '', model_preset_id: null, max_tokens: 16000 })
}

const removeEditionPrompt = (index: number) => {
  if (config.value.edition.prompts.length > 1) {
    config.value.edition.prompts.splice(index, 1)
  }
}

const addSourceType = async () => {
  if (!config.value.source_types) config.value.source_types = {}
  let newTypeName = 'New Type'
  let counter = 1
  const currentTypes = { ...config.value.source_types }
  while (currentTypes[newTypeName] !== undefined) {
    newTypeName = `New Type ${counter++}`
  }
  config.value.source_types = { ...currentTypes, [newTypeName]: '' }
  await nextTick()
}

const removeSourceType = (type: string) => {
  if (config.value.source_types?.[type] !== undefined) {
    const updated = { ...config.value.source_types }
    delete updated[type]
    config.value.source_types = updated
  }
}

const updateSourceType = (oldType: string, newType: string, description: string) => {
  if (!config.value.source_types) config.value.source_types = {}
  const updated = { ...config.value.source_types }
  if (oldType !== newType) delete updated[oldType]
  updated[newType] = description
  config.value.source_types = updated
}

const getPromptList = (group: PromptGroupKey) => config.value[group].prompts

const movePrompt = (group: PromptGroupKey, index: number, direction: 'up' | 'down') => {
  const prompts = getPromptList(group)
  const targetIndex = direction === 'up' ? index - 1 : index + 1
  if (targetIndex < 0 || targetIndex >= prompts.length) return
  const [item] = prompts.splice(index, 1)
  prompts.splice(targetIndex, 0, item)
}

const openPromptEditor = (group: PromptGroupKey, index: number) => {
  const prompt = getPromptList(group)[index]
  if (!prompt) return
  promptEditorDraft.value = prompt.text || ''
  promptEditorMode.value = 'visual'
  promptEditorTarget.value = { kind: 'group', group, index }
  promptEditorTitle.value = prompt.name?.trim()
    ? `${t('preferences.editPromptWysiwyg')} - ${prompt.name}`
    : t('preferences.editPromptWysiwyg')
  isPromptEditorOpen.value = true
}

const openBriefPromptEditor = () => {
  promptEditorDraft.value = config.value.brief.prompt || ''
  promptEditorMode.value = 'visual'
  promptEditorTarget.value = { kind: 'brief' }
  promptEditorTitle.value = t('preferences.editPromptWysiwyg')
  isPromptEditorOpen.value = true
}

const openRagPromptEditor = () => {
  promptEditorDraft.value = config.value.rag.llm_prompt || ''
  promptEditorMode.value = 'visual'
  promptEditorTarget.value = { kind: 'rag' }
  promptEditorTitle.value = t('preferences.editPromptWysiwyg')
  isPromptEditorOpen.value = true
}

const closePromptEditor = () => {
  isPromptEditorOpen.value = false
  promptEditorTarget.value = null
}

const savePromptEditor = () => {
  const target = promptEditorTarget.value
  if (!target) return

  if (target.kind === 'brief') {
    config.value.brief.prompt = promptEditorDraft.value
  } else if (target.kind === 'rag') {
    config.value.rag.llm_prompt = promptEditorDraft.value
  } else {
    const prompt = getPromptList(target.group)[target.index]
    if (prompt) prompt.text = promptEditorDraft.value
  }

  closePromptEditor()
}

watch(
  config,
  () => {
    queueAutoSave()
  },
  { deep: true },
)
</script>

<template>
  <!-- Access guard: configuration is only visible to publisher/admin -->
  <div v-if="!can('configuration', 'read')" class="h-full flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-8">
    <p class="text-gray-500 dark:text-gray-400">{{ t('auth.noAccessDesc') }}</p>
  </div>

  <div v-else class="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
    <!-- Header -->
    <div class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <CogIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400" />
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ t('preferences.title') }}
          </h1>
        </div>
        
        <div class="flex items-center gap-3">
          <!-- Success/Error Messages -->
          <div v-if="isSaving" class="text-sm text-indigo-600 dark:text-indigo-400 font-medium">
            {{ t('preferences.saving') }}
          </div>
          <div v-if="saveMessage" class="text-sm text-green-600 dark:text-green-400 font-medium">
            {{ saveMessage }}
          </div>
          <div v-if="saveError" class="text-sm text-red-600 dark:text-red-400 font-medium">
            {{ saveError }}
          </div>
          
          <input
            ref="importInputRef"
            type="file"
            accept=".yaml,.yml,text/yaml,application/x-yaml"
            class="hidden"
            @change="importConfigYaml"
          />

          <button
            @click="openPreferencesHistory"
            :disabled="isSaving || isLoading"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
          >
            <ClockIcon class="h-4 w-4" />
            {{ t('history.historyButton') }}
          </button>

          <!-- Export Button (admin only) -->
          <button
            v-if="can('configuration', 'update')"
            @click="exportConfigYaml"
            :disabled="isSaving || isLoading"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
          >
            {{ t('preferences.exportYaml') }}
          </button>

          <!-- Import Button (admin only) -->
          <button
            v-if="can('configuration', 'update')"
            @click="openImportDialog"
            :disabled="isSaving || isLoading"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
          >
            {{ t('preferences.importYaml') }}
          </button>

        </div>
      </div>
    </div>

    <!-- Content -->
    <div v-if="isLoading" class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <CogIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 animate-spin mx-auto mb-4" />
        <p class="text-gray-600 dark:text-gray-400">{{ t('preferences.loading') }}</p>
      </div>
    </div>

    <div v-else-if="isHistoryOpen" class="flex-1 overflow-y-auto p-6">
      <div class="max-w-6xl mx-auto">
        <PreferenceVersionHistoryPanel
          v-model:selected-version-id="selectedPreferenceVersionId"
          v-model:active-compare="activePreferenceCompare"
          @close="closePreferencesHistory"
          @restored="onPreferencesRestored"
        />
      </div>
    </div>

    <div v-else class="flex-1 overflow-y-auto p-6">
      <div class="max-w-5xl mx-auto">
        <TabGroup>
          <TabList class="flex space-x-2 rounded-lg bg-gray-200 dark:bg-gray-700 p-1">
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <MicrophoneIcon class="h-5 w-5" />
                {{ t('preferences.transcription') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <PencilIcon class="h-5 w-5" />
                {{ t('preferences.correction') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <DocumentTextIcon class="h-5 w-5" />
                {{ t('preferences.edition') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <BookOpenIcon class="h-5 w-5" />
                {{ t('preferences.sources') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <DocumentTextIcon class="h-5 w-5" />
                {{ t('preferences.summary') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <DocumentTextIcon class="h-5 w-5" />
                {{ t('preferences.brief') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <MagnifyingGlassIcon class="h-5 w-5" />
                {{ t('preferences.rag') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <CogIcon class="h-5 w-5" />
                {{ t('preferences.alignment') }}
              </div>
            </Tab>
          </TabList>

          <TabPanels class="mt-6">
            <!-- Transcription Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.transcriptionSettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Deepgram Model -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.model') }}
                  </label>
                  <input
                    v-model="config.transcribe.model"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    placeholder="nova-3"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.modelDesc') }}
                  </p>
                </div>

                <!-- Language -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.language') }}
                  </label>
                  <input
                    v-model="config.transcribe.language"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.languageDesc') }}
                  </p>
                </div>

                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.audienceSegmentPrefix') }}
                  </label>
                  <input
                    v-model="config.transcribe.audience_segment_prefix"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.audienceSegmentPrefixDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Correction Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.correctionSettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Prompts -->
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      {{ t('preferences.correctionPrompts') }}
                    </label>
                    <button
                      @click="addCorrectionPrompt"
                      type="button"
                      class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                    >
                      + {{ t('preferences.addPrompt') }}
                    </button>
                  </div>
                  
                  <div class="space-y-4">
                    <div
                      v-for="(prompt, index) in config.correction.prompts"
                      :key="index"
                      class="border border-gray-300 dark:border-gray-600 rounded-md p-4 bg-gray-50 dark:bg-gray-900/30"
                    >
                      <div class="flex items-center gap-3 mb-3">
                        <input
                          v-model="prompt.name"
                          type="text"
                          :placeholder="t('preferences.promptName')"
                          class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm font-medium"
                        />
                        <select
                          v-model="prompt.model_preset_id"
                          class="min-w-52 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm"
                        >
                          <option :value="null">{{ t('preferences.selectModelPreset') }}</option>
                          <option
                            v-for="preset in modelPresets"
                            :key="preset.id"
                            :value="preset.id"
                          >
                            {{ preset.name }}
                          </option>
                        </select>
                        <button
                          type="button"
                          @click="movePrompt('correction', index, 'up')"
                          :disabled="index === 0"
                          :title="t('preferences.moveUp')"
                          class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          @click="movePrompt('correction', index, 'down')"
                          :disabled="index === config.correction.prompts.length - 1"
                          :title="t('preferences.moveDown')"
                          class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          ↓
                        </button>
                        <button
                          v-if="config.correction.prompts.length > 1"
                          @click="removeCorrectionPrompt(index)"
                          type="button"
                          class="px-3 py-2 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                        >
                          {{ t('preferences.remove') }}
                        </button>
                      </div>
                      <div class="space-y-2 mb-3">
                        <div class="flex justify-end">
                          <button
                            type="button"
                            @click="openPromptEditor('correction', index)"
                            class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                          >
                            {{ t('preferences.editPromptWysiwyg') }}
                          </button>
                        </div>
                        <button
                          type="button"
                          @click="openPromptEditor('correction', index)"
                          class="w-full text-left px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/60 transition-colors"
                        >
                          <div
                            v-if="prompt.text"
                            :class="[
                              'prose prose-sm max-w-none dark:prose-invert text-gray-900 dark:text-gray-100',
                              { 'prompt-preview-content--collapsed': !isPromptPreviewExpanded('correction', index) }
                            ]"
                            v-html="renderMarkdown(prompt.text)"
                          />
                          <p
                            v-else
                            class="text-sm text-gray-500 dark:text-gray-400 italic"
                          >
                            {{ t('preferences.emptyPromptClickToEdit') }}
                          </p>
                        </button>
                        <div v-if="isPromptPreviewLong(prompt.text)" class="flex justify-end">
                          <button
                            type="button"
                            @click="togglePromptPreview('correction', index)"
                            class="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                          >
                            {{ isPromptPreviewExpanded('correction', index) ? t('preferences.showLess') : t('preferences.showMore') }}
                          </button>
                        </div>
                      </div>
                      <div class="mt-3">
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          {{ t('preferences.maxTokens') }}
                        </label>
                        <input
                          v-model.number="prompt.max_tokens"
                          type="number"
                          min="256"
                          max="200000"
                          step="256"
                          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                        />
                        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {{ t('preferences.maxTokensDesc') }}
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.correctionPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Edition Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.editionSettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Prompts -->
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      {{ t('preferences.editionPrompts') }}
                    </label>
                    <button
                      @click="addEditionPrompt"
                      type="button"
                      class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                    >
                      + {{ t('preferences.addPrompt') }}
                    </button>
                  </div>
                  
                  <div class="space-y-4">
                    <div
                      v-for="(prompt, index) in config.edition.prompts"
                      :key="index"
                      class="border border-gray-300 dark:border-gray-600 rounded-md p-4 bg-gray-50 dark:bg-gray-900/30"
                    >
                      <div class="flex items-center gap-3 mb-3">
                        <input
                          v-model="prompt.name"
                          type="text"
                          :placeholder="t('preferences.promptName')"
                          class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm font-medium"
                        />
                        <select
                          v-model="prompt.model_preset_id"
                          class="min-w-52 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm"
                        >
                          <option :value="null">{{ t('preferences.selectModelPreset') }}</option>
                          <option
                            v-for="preset in modelPresets"
                            :key="preset.id"
                            :value="preset.id"
                          >
                            {{ preset.name }}
                          </option>
                        </select>
                        <button
                          type="button"
                          @click="movePrompt('edition', index, 'up')"
                          :disabled="index === 0"
                          :title="t('preferences.moveUp')"
                          class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          @click="movePrompt('edition', index, 'down')"
                          :disabled="index === config.edition.prompts.length - 1"
                          :title="t('preferences.moveDown')"
                          class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          ↓
                        </button>
                        <button
                          v-if="config.edition.prompts.length > 1"
                          @click="removeEditionPrompt(index)"
                          type="button"
                          class="px-3 py-2 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                        >
                          {{ t('preferences.remove') }}
                        </button>
                      </div>
                      <div class="space-y-2 mb-3">
                        <div class="flex justify-end">
                          <button
                            type="button"
                            @click="openPromptEditor('edition', index)"
                            class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                          >
                            {{ t('preferences.editPromptWysiwyg') }}
                          </button>
                        </div>
                        <button
                          type="button"
                          @click="openPromptEditor('edition', index)"
                          class="w-full text-left px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/60 transition-colors"
                        >
                          <div
                            v-if="prompt.text"
                            :class="[
                              'prose prose-sm max-w-none dark:prose-invert text-gray-900 dark:text-gray-100',
                              { 'prompt-preview-content--collapsed': !isPromptPreviewExpanded('edition', index) }
                            ]"
                            v-html="renderMarkdown(prompt.text)"
                          />
                          <p
                            v-else
                            class="text-sm text-gray-500 dark:text-gray-400 italic"
                          >
                            {{ t('preferences.emptyPromptClickToEdit') }}
                          </p>
                        </button>
                        <div v-if="isPromptPreviewLong(prompt.text)" class="flex justify-end">
                          <button
                            type="button"
                            @click="togglePromptPreview('edition', index)"
                            class="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                          >
                            {{ isPromptPreviewExpanded('edition', index) ? t('preferences.showLess') : t('preferences.showMore') }}
                          </button>
                        </div>
                      </div>
                      <div class="mt-3">
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          {{ t('preferences.maxTokens') }}
                        </label>
                        <input
                          v-model.number="prompt.max_tokens"
                          type="number"
                          min="256"
                          max="200000"
                          step="256"
                          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                        />
                        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {{ t('preferences.maxTokensDesc') }}
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.editionPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Sources Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-6">
                {{ t('preferences.sourcesSettings') }}
              </h2>
              
              <div class="space-y-8">
                <!-- Source Types Reference -->
                <div class="border-b border-gray-200 dark:border-gray-700 pb-6">
                  <h3 class="text-md font-semibold text-gray-900 dark:text-white mb-4">
                    {{ t('preferences.sourceTypes') }}
                  </h3>
                  
                  <div class="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                    <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
                      {{ t('preferences.sourceTypesDesc') }}
                    </p>
                    <div v-if="config.source_types && Object.keys(config.source_types || {}).length > 0" class="space-y-2">
                      <div
                        v-for="(description, type, index) in config.source_types"
                        :key="type"
                        class="flex items-center gap-2 p-2 bg-white dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700"
                      >
                        <input
                          :value="type"
                          @input="(e) => updateSourceType(type, e.target.value, description)"
                          type="text"
                          class="w-32 px-2 py-1 text-sm font-semibold text-gray-900 dark:text-white bg-transparent border-b border-gray-300 dark:border-gray-600 focus:border-indigo-500 dark:focus:border-indigo-400 focus:outline-none"
                          :placeholder="t('preferences.sourceTypeName')"
                        />
                        <input
                          :value="description"
                          @input="(e) => updateSourceType(type, type, e.target.value)"
                          type="text"
                          class="flex-1 px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-transparent border-b border-gray-300 dark:border-gray-600 focus:border-indigo-500 dark:focus:border-indigo-400 focus:outline-none"
                          :placeholder="t('preferences.sourceTypeDescription')"
                        />
                        <button
                          @click="removeSourceType(type)"
                          type="button"
                          class="px-2 py-1.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 rounded-md transition-colors shadow-sm flex items-center justify-center flex-shrink-0"
                          :title="t('preferences.remove')"
                        >
                          <TrashIcon class="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    <div v-else class="text-sm text-gray-500 dark:text-gray-400 italic text-center py-4">
                      {{ t('preferences.noSourceTypes') }}
                    </div>
                    
                    <!-- Add Type button at the end -->
                    <div class="mt-4 flex justify-end">
                      <button
                        @click="addSourceType"
                        type="button"
                        class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 rounded-md transition-colors shadow-sm flex items-center gap-2"
                      >
                        <span>+</span>
                        {{ t('preferences.addSourceType') }}
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Source Extraction Section -->
                <div class="border-b border-gray-200 dark:border-gray-700 pb-6">
                  <h3 class="text-md font-semibold text-gray-900 dark:text-white mb-4">
                    {{ t('preferences.sourceExtraction') }}
                  </h3>
                  
                  <div class="space-y-6">
                    <!-- Prompts -->
                    <div>
                      <div class="flex items-center justify-between mb-2">
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                          {{ t('preferences.extractionPrompts') }}
                        </label>
                        <button
                          @click="addExtractionPrompt"
                          type="button"
                          class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                        >
                          + {{ t('preferences.addPrompt') }}
                        </button>
                      </div>
                      
                      <div class="space-y-4">
                        <div
                          v-for="(prompt, index) in config.extraction.prompts"
                          :key="index"
                          class="border border-gray-300 dark:border-gray-600 rounded-md p-4 bg-gray-50 dark:bg-gray-900/30"
                        >
                          <div class="flex items-center gap-3 mb-3">
                            <input
                              v-model="prompt.name"
                              type="text"
                              :placeholder="t('preferences.promptName')"
                              class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm font-medium"
                            />
                            <select
                              v-model="prompt.model_preset_id"
                              class="min-w-52 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm"
                            >
                              <option :value="null">{{ t('preferences.selectModelPreset') }}</option>
                              <option
                                v-for="preset in modelPresets"
                                :key="preset.id"
                                :value="preset.id"
                              >
                                {{ preset.name }}
                              </option>
                            </select>
                            <button
                              type="button"
                              @click="movePrompt('extraction', index, 'up')"
                              :disabled="index === 0"
                              :title="t('preferences.moveUp')"
                              class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              @click="movePrompt('extraction', index, 'down')"
                              :disabled="index === config.extraction.prompts.length - 1"
                              :title="t('preferences.moveDown')"
                              class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              ↓
                            </button>
                            <button
                              v-if="(config.extraction.prompts?.length ?? 0) > 1"
                              @click="removeExtractionPrompt(index)"
                              type="button"
                              class="px-3 py-2 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                            >
                              {{ t('preferences.remove') }}
                            </button>
                          </div>
                          <div class="space-y-2 mb-3">
                            <div class="flex justify-end">
                              <button
                                type="button"
                                @click="openPromptEditor('extraction', index)"
                                class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                              >
                                {{ t('preferences.editPromptWysiwyg') }}
                              </button>
                            </div>
                            <button
                              type="button"
                              @click="openPromptEditor('extraction', index)"
                              class="w-full text-left px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/60 transition-colors"
                            >
                              <div
                                v-if="prompt.text"
                                :class="[
                                  'prose prose-sm max-w-none dark:prose-invert text-gray-900 dark:text-gray-100',
                                  { 'prompt-preview-content--collapsed': !isPromptPreviewExpanded('extraction', index) }
                                ]"
                                v-html="renderMarkdown(prompt.text)"
                              />
                              <p
                                v-else
                                class="text-sm text-gray-500 dark:text-gray-400 italic"
                              >
                                {{ t('preferences.emptyPromptClickToEdit') }}
                              </p>
                            </button>
                            <div v-if="isPromptPreviewLong(prompt.text)" class="flex justify-end">
                              <button
                                type="button"
                                @click="togglePromptPreview('extraction', index)"
                                class="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                              >
                                {{ isPromptPreviewExpanded('extraction', index) ? t('preferences.showLess') : t('preferences.showMore') }}
                              </button>
                            </div>
                          </div>
                          <div class="mt-3">
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                              {{ t('preferences.maxTokens') }}
                            </label>
                            <input
                              v-model.number="prompt.max_tokens"
                              type="number"
                              min="256"
                              max="200000"
                              step="256"
                              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                            />
                          </div>
                        </div>
                      </div>
                      
                      <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.extractionPromptDesc') }}
                      </p>
                    </div>
                  </div>
                </div>

                <!-- Source Verification Section -->
                <div>
                  <h3 class="text-md font-semibold text-gray-900 dark:text-white mb-4">
                    {{ t('preferences.sourceVerification') }}
                  </h3>
                  
                  <div class="space-y-6">
                    <!-- Prompts -->
                    <div>
                      <div class="flex items-center justify-between mb-2">
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                          {{ t('preferences.sourcesPrompts') }}
                        </label>
                        <button
                          @click="addSourcesPrompt"
                          type="button"
                          class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                        >
                          + {{ t('preferences.addPrompt') }}
                        </button>
                      </div>
                      
                      <div class="space-y-4">
                        <div
                          v-for="(prompt, index) in config.sources.prompts"
                          :key="index"
                          class="border border-gray-300 dark:border-gray-600 rounded-md p-4 bg-gray-50 dark:bg-gray-900/30"
                        >
                          <div class="flex items-center gap-3 mb-3">
                            <input
                              v-model="prompt.name"
                              type="text"
                              :placeholder="t('preferences.promptName')"
                              class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm font-medium"
                            />
                            <select
                              v-model="prompt.model_preset_id"
                              class="min-w-52 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm"
                            >
                              <option :value="null">{{ t('preferences.selectModelPreset') }}</option>
                              <option
                                v-for="preset in modelPresets"
                                :key="preset.id"
                                :value="preset.id"
                              >
                                {{ preset.name }}
                              </option>
                            </select>
                            <button
                              type="button"
                              @click="movePrompt('sources', index, 'up')"
                              :disabled="index === 0"
                              :title="t('preferences.moveUp')"
                              class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              ↑
                            </button>
                            <button
                              type="button"
                              @click="movePrompt('sources', index, 'down')"
                              :disabled="index === config.sources.prompts.length - 1"
                              :title="t('preferences.moveDown')"
                              class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                            >
                              ↓
                            </button>
                            <button
                              v-if="(config.sources.prompts?.length ?? 0) > 1"
                              @click="removeSourcesPrompt(index)"
                              type="button"
                              class="px-3 py-2 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                            >
                              {{ t('preferences.remove') }}
                            </button>
                          </div>
                          <div class="space-y-2 mb-3">
                            <div class="flex justify-end">
                              <button
                                type="button"
                                @click="openPromptEditor('sources', index)"
                                class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                              >
                                {{ t('preferences.editPromptWysiwyg') }}
                              </button>
                            </div>
                            <button
                              type="button"
                              @click="openPromptEditor('sources', index)"
                              class="w-full text-left px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/60 transition-colors"
                            >
                              <div
                                v-if="prompt.text"
                                :class="[
                                  'prose prose-sm max-w-none dark:prose-invert text-gray-900 dark:text-gray-100',
                                  { 'prompt-preview-content--collapsed': !isPromptPreviewExpanded('sources', index) }
                                ]"
                                v-html="renderMarkdown(prompt.text)"
                              />
                              <p
                                v-else
                                class="text-sm text-gray-500 dark:text-gray-400 italic"
                              >
                                {{ t('preferences.emptyPromptClickToEdit') }}
                              </p>
                            </button>
                            <div v-if="isPromptPreviewLong(prompt.text)" class="flex justify-end">
                              <button
                                type="button"
                                @click="togglePromptPreview('sources', index)"
                                class="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                              >
                                {{ isPromptPreviewExpanded('sources', index) ? t('preferences.showLess') : t('preferences.showMore') }}
                              </button>
                            </div>
                          </div>
                          <div class="mt-3">
                            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                              {{ t('preferences.maxTokens') }}
                            </label>
                            <input
                              v-model.number="prompt.max_tokens"
                              type="number"
                              min="256"
                              max="200000"
                              step="256"
                              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                            />
                          </div>
                        </div>
                      </div>
                      
                      <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.sourcesPromptDesc') }}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </TabPanel>

            <!-- Summary Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.summarySettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Prompts -->
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      {{ t('preferences.summaryPrompts') }}
                    </label>
                    <button
                      @click="addSummaryPrompt"
                      type="button"
                      class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                    >
                      + {{ t('preferences.addPrompt') }}
                    </button>
                  </div>
                  
                  <div class="space-y-4">
                    <div
                      v-for="(prompt, index) in config.summary.prompts"
                      :key="index"
                      class="border border-gray-300 dark:border-gray-600 rounded-md p-4 bg-gray-50 dark:bg-gray-900/30"
                    >
                      <div class="flex items-center gap-3 mb-3">
                        <input
                          v-model="prompt.name"
                          type="text"
                          :placeholder="t('preferences.promptName')"
                          class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm font-medium"
                        />
                        <select
                          v-model="prompt.model_preset_id"
                          class="min-w-52 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm"
                        >
                          <option :value="null">{{ t('preferences.selectModelPreset') }}</option>
                          <option
                            v-for="preset in modelPresets"
                            :key="preset.id"
                            :value="preset.id"
                          >
                            {{ preset.name }}
                          </option>
                        </select>
                        <button
                          type="button"
                          @click="movePrompt('summary', index, 'up')"
                          :disabled="index === 0"
                          :title="t('preferences.moveUp')"
                          class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          ↑
                        </button>
                        <button
                          type="button"
                          @click="movePrompt('summary', index, 'down')"
                          :disabled="index === config.summary.prompts.length - 1"
                          :title="t('preferences.moveDown')"
                          class="px-2 py-2 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        >
                          ↓
                        </button>
                        <button
                          v-if="config.summary.prompts.length > 1"
                          @click="removeSummaryPrompt(index)"
                          type="button"
                          class="px-3 py-2 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                        >
                          {{ t('preferences.remove') }}
                        </button>
                      </div>
                      <div class="space-y-2 mb-3">
                        <div class="flex justify-end">
                          <button
                            type="button"
                            @click="openPromptEditor('summary', index)"
                            class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                          >
                            {{ t('preferences.editPromptWysiwyg') }}
                          </button>
                        </div>
                        <button
                          type="button"
                          @click="openPromptEditor('summary', index)"
                          class="w-full text-left px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/60 transition-colors"
                        >
                          <div
                            v-if="prompt.text"
                            :class="[
                              'prose prose-sm max-w-none dark:prose-invert text-gray-900 dark:text-gray-100',
                              { 'prompt-preview-content--collapsed': !isPromptPreviewExpanded('summary', index) }
                            ]"
                            v-html="renderMarkdown(prompt.text)"
                          />
                          <p
                            v-else
                            class="text-sm text-gray-500 dark:text-gray-400 italic"
                          >
                            {{ t('preferences.emptyPromptClickToEdit') }}
                          </p>
                        </button>
                        <div v-if="isPromptPreviewLong(prompt.text)" class="flex justify-end">
                          <button
                            type="button"
                            @click="togglePromptPreview('summary', index)"
                            class="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                          >
                            {{ isPromptPreviewExpanded('summary', index) ? t('preferences.showLess') : t('preferences.showMore') }}
                          </button>
                        </div>
                      </div>
                      <div class="mt-3">
                        <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          {{ t('preferences.maxTokens') }}
                        </label>
                        <input
                          v-model.number="prompt.max_tokens"
                          type="number"
                          min="256"
                          max="200000"
                          step="256"
                          class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                        />
                        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          {{ t('preferences.maxTokensDesc') }}
                        </p>
                      </div>
                    </div>
                  </div>
                  
                  <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.summaryPromptDesc') }}
                  </p>
                </div>

              </div>
            </TabPanel>

            <!-- Brief Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.briefSettings') }}
              </h2>

              <div class="space-y-6">
                <!-- Model Preset -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.modelPresets') }}
                  </label>
                  <select
                    v-model="config.brief.model_preset_id"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option :value="null">{{ t('preferences.selectModelPreset') }}</option>
                    <option
                      v-for="preset in modelPresets"
                      :key="preset.id"
                      :value="preset.id"
                    >
                      {{ preset.name }}
                    </option>
                  </select>
                </div>

                <!-- Max Tokens -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.maxTokens') }}
                  </label>
                  <input
                    v-model.number="config.brief.max_tokens"
                    type="number"
                    min="256"
                    max="200000"
                    step="256"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.maxTokensDesc') }}
                  </p>
                </div>

                <!-- Prompt -->
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      {{ t('preferences.prompt') }}
                    </label>
                    <button
                      type="button"
                      @click="openBriefPromptEditor"
                      class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                    >
                      {{ t('preferences.editPromptWysiwyg') }}
                    </button>
                  </div>
                  <button
                    type="button"
                    @click="openBriefPromptEditor"
                    class="w-full text-left px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/60 transition-colors"
                  >
                    <div
                      v-if="config.brief.prompt"
                      :class="[
                        'prose prose-sm max-w-none dark:prose-invert text-gray-900 dark:text-gray-100',
                        { 'prompt-preview-content--collapsed': !isPromptPreviewExpanded('brief') }
                      ]"
                      v-html="renderMarkdown(config.brief.prompt)"
                    />
                    <p
                      v-else
                      class="text-sm text-gray-500 dark:text-gray-400 italic"
                    >
                      {{ t('preferences.emptyPromptClickToEdit') }}
                    </p>
                  </button>
                  <div v-if="isPromptPreviewLong(config.brief.prompt)" class="mt-2 flex justify-end">
                    <button
                      type="button"
                      @click="togglePromptPreview('brief')"
                      class="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      {{ isPromptPreviewExpanded('brief') ? t('preferences.showLess') : t('preferences.showMore') }}
                    </button>
                  </div>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.briefPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- RAG Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.ragSettings') }}
              </h2>

              <div class="space-y-6">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {{ t('preferences.ragChunkTargetChars') }}
                    </label>
                    <input
                      v-model.number="config.rag.chunk_target_chars"
                      type="number"
                      min="1"
                      step="50"
                      class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    />
                    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {{ t('preferences.ragChunkTargetCharsDesc') }}
                    </p>
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {{ t('preferences.ragChunkMaxChars') }}
                    </label>
                    <input
                      v-model.number="config.rag.chunk_max_chars"
                      type="number"
                      min="1"
                      step="50"
                      class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    />
                    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {{ t('preferences.ragChunkMaxCharsDesc') }}
                    </p>
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {{ t('preferences.ragRetrievalK') }}
                    </label>
                    <input
                      v-model.number="config.rag.retrieval_k"
                      type="number"
                      min="1"
                      step="1"
                      class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    />
                    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {{ t('preferences.ragRetrievalKDesc') }}
                    </p>
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {{ t('preferences.ragFullTextSearchK') }}
                    </label>
                    <input
                      v-model.number="config.rag.full_text_search_k"
                      type="number"
                      min="1"
                      step="1"
                      class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    />
                    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {{ t('preferences.ragFullTextSearchKDesc') }}
                    </p>
                  </div>

                  <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      {{ t('preferences.ragRerankingTopN') }}
                    </label>
                    <input
                      v-model.number="config.rag.reranking_top_n"
                      type="number"
                      min="1"
                      step="1"
                      class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    />
                    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {{ t('preferences.ragRerankingTopNDesc') }}
                    </p>
                  </div>
                </div>

                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.ragEmbeddingModel') }}
                  </label>
                  <input
                    v-model="config.rag.embedding_model"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    placeholder="google/gemini-embedding-001"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.ragEmbeddingModelDesc') }}
                  </p>
                </div>

                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.ragRerankingModel') }}
                  </label>
                  <input
                    v-model="config.rag.reranking_model"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    placeholder="cohere/rerank-4-pro"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.ragRerankingModelDesc') }}
                  </p>
                </div>

                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.ragLlmModel') }}
                  </label>
                  <input
                    v-model="config.rag.llm_model"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    placeholder="openai/gpt-5.4"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.ragLlmModelDesc') }}
                  </p>
                </div>

                <div>
                  <div class="flex items-center justify-between mb-2">
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      {{ t('preferences.ragLlmPrompt') }}
                    </label>
                    <button
                      type="button"
                      @click="openRagPromptEditor"
                      class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                    >
                      {{ t('preferences.editPromptWysiwyg') }}
                    </button>
                  </div>
                  <button
                    type="button"
                    @click="openRagPromptEditor"
                    class="w-full text-left px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 hover:bg-gray-50 dark:hover:bg-gray-600/60 transition-colors"
                  >
                    <div
                      v-if="config.rag.llm_prompt"
                      :class="[
                        'prose prose-sm max-w-none dark:prose-invert text-gray-900 dark:text-gray-100',
                        { 'prompt-preview-content--collapsed': !isPromptPreviewExpanded('rag') }
                      ]"
                      v-html="renderMarkdown(config.rag.llm_prompt)"
                    />
                    <p
                      v-else
                      class="text-sm text-gray-500 dark:text-gray-400 italic"
                    >
                      {{ t('preferences.emptyPromptClickToEdit') }}
                    </p>
                  </button>
                  <div v-if="isPromptPreviewLong(config.rag.llm_prompt)" class="mt-2 flex justify-end">
                    <button
                      type="button"
                      @click="togglePromptPreview('rag')"
                      class="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      {{ isPromptPreviewExpanded('rag') ? t('preferences.showLess') : t('preferences.showMore') }}
                    </button>
                  </div>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.ragLlmPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Alignment Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.alignmentSettings') }}
              </h2>

              <div class="space-y-6">
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.editedTranscriptAlignmentThreshold') }}
                  </label>
                  <input
                    v-model.number="config.alignment.edited_min_score"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.alignmentThresholdDesc') }}
                  </p>
                </div>

                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.summaryEditedAlignmentThreshold') }}
                  </label>
                  <input
                    v-model.number="config.alignment.summary_min_score"
                    type="number"
                    min="0"
                    max="1"
                    step="0.01"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.alignmentThresholdDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </div>
    </div>

    <div
      v-if="isPromptEditorOpen"
      class="fixed inset-0 z-50 bg-white dark:bg-gray-900 flex flex-col"
    >
      <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
          {{ promptEditorTitle }}
        </h3>
        <div class="flex items-center gap-2">
          <div class="inline-flex rounded-md border border-gray-300 dark:border-gray-600 overflow-hidden">
            <button
              type="button"
              @click="promptEditorMode = 'visual'"
              :class="[
                'px-3 py-1.5 text-xs font-medium transition-colors',
                promptEditorMode === 'visual'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
              ]"
            >
              {{ t('preferences.visualMode') }}
            </button>
            <button
              type="button"
              @click="promptEditorMode = 'markdown'"
              :class="[
                'px-3 py-1.5 text-xs font-medium transition-colors border-l border-gray-300 dark:border-gray-600',
                promptEditorMode === 'markdown'
                  ? 'bg-indigo-600 text-white'
                  : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
              ]"
            >
              {{ t('preferences.markdownMode') }}
            </button>
          </div>
          <button
            type="button"
            @click="closePromptEditor"
            class="px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md transition-colors"
          >
            {{ t('preferences.close') }}
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        <MilkdownEditor
          v-if="promptEditorMode === 'visual'"
          v-model="promptEditorDraft"
          :placeholder="t('preferences.promptText')"
        />
        <textarea
          v-else
          v-model="promptEditorDraft"
          :placeholder="t('preferences.promptText')"
          class="w-full h-full min-h-[24rem] px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
        ></textarea>
      </div>

      <div class="flex justify-end gap-2 px-6 py-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900">
        <button
          type="button"
          @click="closePromptEditor"
          class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors"
        >
          {{ t('preferences.cancel') }}
        </button>
        <button
          type="button"
          @click="savePromptEditor"
          class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors"
        >
          {{ t('preferences.save') }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Custom styles for range slider */
input[type="range"]::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #4f46e5;
  cursor: pointer;
}

input[type="range"]::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #4f46e5;
  cursor: pointer;
  border: none;
}

.prompt-preview-content--collapsed {
  max-height: 4.5em;
  overflow: hidden;
}
</style>


