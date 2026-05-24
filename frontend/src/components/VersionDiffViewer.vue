<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import DiffMatchPatch from 'diff-match-patch'
import { useI18n } from 'vue-i18n'
import type { ContentType, VersionDiffResponse } from '@/api/types'
import { lessonsApi } from '@/api/lessons'

type DiffRowKind = 'file' | 'hunk' | 'context' | 'add' | 'del'
type DiffRow = {
  kind: DiffRowKind
  oldLine: number | null
  newLine: number | null
  text: string
}

type StructuredDiffBlock = {
  segmentIndex: number
  rows: RenderedDiffRow[]
}

type RenderedDiffRow = DiffRow & { html: string }
type CompareMode = 'github' | 'redlines'

const props = defineProps<{
  lessonHashid: string
  versionAId: string
  versionBId: string
  contentType: ContentType
}>()

const { t } = useI18n()
const loading = ref(false)
const error = ref<string | null>(null)
const diff = ref<VersionDiffResponse | null>(null)
const compareMode = ref<CompareMode>('redlines')
const versionAText = ref('')
const versionBText = ref('')
const isLoadingRedlines = ref(false)
const dmp = new DiffMatchPatch()

const escapeHtml = (value: string): string =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')

const tokenizeWithWhitespace = (value: string): string[] =>
  value.split(/(\s+)/).filter((chunk) => chunk.length > 0)

const toDiffChars = (
  tokens: string[],
  tokenToCode: Map<string, number>,
  codeToToken: string[],
): string => {
  let out = ''
  for (const token of tokens) {
    let code = tokenToCode.get(token)
    if (code === undefined) {
      code = codeToToken.length
      tokenToCode.set(token, code)
      codeToToken.push(token)
    }
    out += String.fromCharCode(code)
  }
  return out
}

const wordDiff = (before: string, after: string): diff_match_patch.Diff[] => {
  const tokenToCode = new Map<string, number>()
  const codeToToken: string[] = []
  const beforeChars = toDiffChars(tokenizeWithWhitespace(before), tokenToCode, codeToToken)
  const afterChars = toDiffChars(tokenizeWithWhitespace(after), tokenToCode, codeToToken)
  const rawDiffs = dmp.diff_main(beforeChars, afterChars, false)
  dmp.diff_cleanupSemantic(rawDiffs)
  return rawDiffs.map(([op, chars]) => [
    op,
    [...chars].map((ch) => codeToToken[ch.charCodeAt(0)] ?? '').join(''),
  ])
}

const diffOpClass = {
  insert: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  delete: 'bg-red-100 text-red-800 line-through dark:bg-red-900/40 dark:text-red-200',
}

const rowHtmlFromWordDiff = (
  diffs: diff_match_patch.Diff[],
  mode: 'old' | 'new',
): string => diffs
  .map(([op, token]) => {
    const escaped = escapeHtml(token)
    if (op === 0) return escaped
    if (mode === 'old' && op === -1) {
      return `<del class="${diffOpClass.delete} rounded-sm px-0.5">${escaped}</del>`
    }
    if (mode === 'new' && op === 1) {
      return `<ins class="${diffOpClass.insert} rounded-sm px-0.5 no-underline">${escaped}</ins>`
    }
    return ''
  })
  .join('')

const defaultRowHtml = (row: DiffRow): string => {
  const escaped = escapeHtml(row.text)
  if (row.kind === 'add') {
    return `<ins class="${diffOpClass.insert} rounded-sm px-0.5 no-underline">${escaped}</ins>`
  }
  if (row.kind === 'del') {
    return `<del class="${diffOpClass.delete} rounded-sm px-0.5">${escaped}</del>`
  }
  return escaped
}

const renderRowsWithWordDiff = (rows: DiffRow[]): RenderedDiffRow[] => {
  const rendered: RenderedDiffRow[] = []

  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i]
    const next = rows[i + 1]
    if (row.kind === 'del' && next?.kind === 'add') {
      const diffs = wordDiff(row.text, next.text)
      rendered.push({ ...row, html: rowHtmlFromWordDiff(diffs, 'old') })
      rendered.push({ ...next, html: rowHtmlFromWordDiff(diffs, 'new') })
      i += 1
      continue
    }

    rendered.push({ ...row, html: defaultRowHtml(row) })
  }

  return rendered
}

const normalizeVersionContentToText = (content: unknown): string => {
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (item && typeof item === 'object' && 'text' in item) {
          const text = (item as { text?: unknown }).text
          return typeof text === 'string' ? text : ''
        }
        return typeof item === 'string' ? item : ''
      })
      .join('\n')
  }
  if (content && typeof content === 'object' && 'markdown' in content) {
    const markdown = (content as { markdown?: unknown }).markdown
    return typeof markdown === 'string' ? markdown : ''
  }
  if (content == null) return ''
  return String(content)
}

const redlineHtml = computed(() => {
  if (!versionAText.value && !versionBText.value) return ''
  const diffs = wordDiff(versionAText.value, versionBText.value)
  return diffs
    .map(([op, token]) => {
      const escaped = escapeHtml(token)
      if (op === 1) {
        return `<ins class="${diffOpClass.insert} rounded-sm px-0.5 no-underline">${escaped}</ins>`
      }
      if (op === -1) {
        return `<del class="${diffOpClass.delete} rounded-sm px-0.5">${escaped}</del>`
      }
      return escaped
    })
    .join('')
})

const hasRedlineChanges = computed(() => versionAText.value !== versionBText.value)

const textRows = computed(() => {
  if (!diff.value || diff.value.type !== 'text') return []
  return renderRowsWithWordDiff(parseUnifiedDiff(diff.value.diff))
})

const parseUnifiedDiff = (rawDiff: string): DiffRow[] => {
  const rows: DiffRow[] = []
  let oldLine = 0
  let newLine = 0

  for (const line of rawDiff.split('\n')) {
    if (line.startsWith('@@')) {
      const match = /@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(line)
      if (match) {
        oldLine = Number(match[1])
        newLine = Number(match[2])
      }
      rows.push({ kind: 'hunk', oldLine: null, newLine: null, text: line })
      continue
    }

    if (line.startsWith('---') || line.startsWith('+++')) {
      rows.push({ kind: 'file', oldLine: null, newLine: null, text: line })
      continue
    }

    if (line.startsWith('+')) {
      rows.push({
        kind: 'add',
        oldLine: null,
        newLine,
        text: line.slice(1),
      })
      newLine += 1
      continue
    }

    if (line.startsWith('-')) {
      rows.push({
        kind: 'del',
        oldLine,
        newLine: null,
        text: line.slice(1),
      })
      oldLine += 1
      continue
    }

    const normalized = line.startsWith(' ') ? line.slice(1) : line
    rows.push({
      kind: 'context',
      oldLine,
      newLine,
      text: normalized,
    })
    oldLine += 1
    newLine += 1
  }

  return rows
}

const rowsFromPlainText = (value: string, mode: 'add' | 'del' | 'context'): DiffRow[] => {
  const lines = value.split('\n')
  return lines.map((line, index) => ({
    kind: mode,
    oldLine: mode === 'add' ? null : index + 1,
    newLine: mode === 'del' ? null : index + 1,
    text: line,
  }))
}

const structuredBlocks = computed<StructuredDiffBlock[]>(() => {
  if (!diff.value || diff.value.type !== 'structured') return []

  return diff.value.segments
    .filter((segment) => segment.status !== 'unchanged')
    .map((segment) => {
      let rows: DiffRow[] = []
      if (segment.status === 'modified') {
        rows = parseUnifiedDiff(segment.text_diff)
      } else if (segment.status === 'added') {
        rows = rowsFromPlainText(segment.text_diff, 'add')
      } else if (segment.status === 'removed') {
        rows = rowsFromPlainText(segment.text_diff, 'del')
      }
      return {
        segmentIndex: segment.segment_index,
        rows: renderRowsWithWordDiff(rows),
      }
    })
})

const rowClass = (kind: DiffRowKind): string => {
  if (kind === 'add') return 'bg-green-50 text-green-900 dark:bg-green-900/20 dark:text-green-100'
  if (kind === 'del') return 'bg-red-50 text-red-900 dark:bg-red-900/20 dark:text-red-100'
  if (kind === 'hunk') return 'bg-blue-50 text-blue-800 dark:bg-blue-900/20 dark:text-blue-200'
  if (kind === 'file') return 'bg-gray-100 text-gray-700 dark:bg-gray-700/60 dark:text-gray-200'
  return 'bg-white text-gray-800 dark:bg-gray-800 dark:text-gray-200'
}

const markerForKind = (kind: DiffRowKind): string => {
  if (kind === 'add') return '+'
  if (kind === 'del') return '-'
  if (kind === 'hunk') return '@'
  return ' '
}

const fetchDiff = async () => {
  if (!props.versionAId || !props.versionBId) return
  loading.value = true
  error.value = null
  try {
    diff.value = await lessonsApi.getVersionDiff(props.lessonHashid, props.versionAId, props.versionBId)
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('history.diffLoadFailed')
  } finally {
    loading.value = false
  }
}

const fetchVersionTexts = async () => {
  if (!props.versionAId || !props.versionBId) return
  isLoadingRedlines.value = true
  try {
    const [versionA, versionB] = await Promise.all([
      lessonsApi.getVersion(props.lessonHashid, props.versionAId),
      lessonsApi.getVersion(props.lessonHashid, props.versionBId),
    ])
    versionAText.value = normalizeVersionContentToText(versionA.content)
    versionBText.value = normalizeVersionContentToText(versionB.content)
  } catch {
    versionAText.value = ''
    versionBText.value = ''
  } finally {
    isLoadingRedlines.value = false
  }
}

watch(
  () => [props.lessonHashid, props.versionAId, props.versionBId, props.contentType],
  fetchDiff,
  { immediate: true },
)

watch(
  () => [props.lessonHashid, props.versionAId, props.versionBId, props.contentType],
  fetchVersionTexts,
  { immediate: true },
)
</script>

<template>
  <div class="rounded-lg border border-gray-200 bg-white p-3 dark:border-gray-700 dark:bg-gray-800">
    <div class="mb-3 flex items-center justify-end">
      <div class="inline-flex rounded-md border border-gray-300 p-0.5 dark:border-gray-600">
        <button
          class="rounded px-2.5 py-1 text-xs font-medium transition-colors"
          :class="compareMode === 'github'
            ? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
            : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'"
          @click="compareMode = 'github'"
        >
          {{ t('history.diffModeGithub') }}
        </button>
        <button
          class="rounded px-2.5 py-1 text-xs font-medium transition-colors"
          :class="compareMode === 'redlines'
            ? 'bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900'
            : 'text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-700'"
          @click="compareMode = 'redlines'"
        >
          {{ t('history.diffModeRedlines') }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">{{ t('history.loadingDiff') }}</div>
    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</div>
    <div v-else-if="compareMode === 'redlines' && isLoadingRedlines" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.loadingDiff') }}
    </div>
    <div v-else-if="compareMode === 'redlines' && !hasRedlineChanges" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.noDiffAvailable') }}
    </div>
    <div
      v-else-if="compareMode === 'redlines'"
      dir="auto"
      class="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md border border-gray-200 bg-gray-50 p-3 text-sm leading-6 text-gray-800 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
      v-html="redlineHtml"
    />
    <div v-else-if="diff?.type === 'text' && textRows.length === 0" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.noDiffAvailable') }}
    </div>
    <template v-else-if="diff">
      <div
        v-if="diff.type === 'text'"
        class="max-h-[65vh] overflow-auto rounded-md border border-gray-200 dark:border-gray-700"
      >
        <div class="sticky top-0 z-10 grid grid-cols-[2rem_3.25rem_3.25rem_1fr] border-b border-gray-200 bg-gray-100 text-[11px] font-semibold uppercase tracking-wide text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
          <div class="border-r border-gray-200 px-2 py-1 dark:border-gray-700"></div>
          <div class="border-r border-gray-200 px-2 py-1 text-right dark:border-gray-700">old</div>
          <div class="border-r border-gray-200 px-2 py-1 text-right dark:border-gray-700">new</div>
          <div class="px-2 py-1">content</div>
        </div>
        <div
          v-for="(row, idx) in textRows"
          :key="idx"
          class="grid grid-cols-[2rem_3.25rem_3.25rem_1fr] text-xs font-mono leading-5"
          :class="rowClass(row.kind)"
        >
          <div class="border-r border-gray-200 px-2 py-0.5 text-center text-gray-500 dark:border-gray-700 dark:text-gray-400">
            {{ markerForKind(row.kind) }}
          </div>
          <div class="border-r border-gray-200 px-2 py-0.5 text-right text-gray-500 dark:border-gray-700 dark:text-gray-400">
            {{ row.oldLine ?? '' }}
          </div>
          <div class="border-r border-gray-200 px-2 py-0.5 text-right text-gray-500 dark:border-gray-700 dark:text-gray-400">
            {{ row.newLine ?? '' }}
          </div>
          <div class="whitespace-pre-wrap px-2 py-0.5" v-html="row.html"></div>
        </div>
      </div>

      <div v-else class="max-h-[65vh] space-y-4 overflow-auto rounded-md border border-gray-200 p-2 dark:border-gray-700">
        <div class="sticky top-0 z-10 grid grid-cols-[2rem_3.25rem_3.25rem_1fr] border border-gray-200 bg-gray-100 text-[11px] font-semibold uppercase tracking-wide text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
          <div class="border-r border-gray-200 px-2 py-1 dark:border-gray-700"></div>
          <div class="border-r border-gray-200 px-2 py-1 text-right dark:border-gray-700">old</div>
          <div class="border-r border-gray-200 px-2 py-1 text-right dark:border-gray-700">new</div>
          <div class="px-2 py-1">content</div>
        </div>
        <div
          v-for="block in structuredBlocks"
          :key="block.segmentIndex"
          class="overflow-hidden rounded-md border border-gray-200 dark:border-gray-700"
        >
          <div class="border-b border-gray-200 bg-gray-50 px-3 py-2 text-xs font-semibold text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
            {{ t('history.segmentLabel', { index: block.segmentIndex }) }}
          </div>
          <div
            v-for="(row, idx) in block.rows"
            :key="idx"
            class="grid grid-cols-[2rem_3.25rem_3.25rem_1fr] text-xs font-mono leading-5"
            :class="rowClass(row.kind)"
          >
            <div class="border-r border-gray-200 px-2 py-0.5 text-center text-gray-500 dark:border-gray-700 dark:text-gray-400">
              {{ markerForKind(row.kind) }}
            </div>
            <div class="border-r border-gray-200 px-2 py-0.5 text-right text-gray-500 dark:border-gray-700 dark:text-gray-400">
              {{ row.oldLine ?? '' }}
            </div>
            <div class="border-r border-gray-200 px-2 py-0.5 text-right text-gray-500 dark:border-gray-700 dark:text-gray-400">
              {{ row.newLine ?? '' }}
            </div>
            <div class="whitespace-pre-wrap px-2 py-0.5" v-html="row.html"></div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
