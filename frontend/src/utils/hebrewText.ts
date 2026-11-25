/**
 * Display Hebrew terms of a lesson text according to the user's Hebrew display
 * settings, using the glossary.
 *
 * Works on markdown before it is rendered: each Hebrew term found in the text
 * is replaced by inline HTML (`<span class="he-term" data-he-term="{id}">`)
 * showing the chosen primary form, plus the supplementary form in a
 * `.he-supp` span. "First occurrence only" and the tooltip are handled on the
 * rendered DOM by `HebrewTermsLayer.vue`.
 *
 * Keys mirror backend `hebrew_text.py` (normalize_hebrew / hebrew_consonants).
 */
import type { HebrewDisplaySettings, LessonHebrewTerm } from '@/api/types'

const LETTER = 'א-ת'
const POINTS = '֑-ׇֽֿׁׂׅׄ'
/** From the first to the last Hebrew letter (with its points), plus an optional closing geresh. */
const HEBREW_SPAN_RE = new RegExp(`[${LETTER}](?:[\\s\\S]*[${LETTER}])?[${POINTS}]*['’׳]?`)
const CANTILLATION_RE = /[֑-֯]/g
const METEG = 'ֽ'
const NIQQUD_RE = /[ְ-ׇּֽֿׁׂׅׄ]/g
/** Every point and cantillation mark (maqaf, paseq, sof pasuq and nun hafukha are kept). */
const ALL_POINTS_RE = new RegExp(`[${POINTS}]`, 'g')
const WHITESPACE_RE = /\s+/g
const GERESH = '׳'
const GERSHAYIM = '״'
const SINGLE_QUOTES = "'‘’‛`´ʹʼ"
const DOUBLE_QUOTES = '"“”„‟ʺ'

/** HTML tags (doubt tags, source markers...) and link targets are never part of a term. */
const MASKED_RE = /<(?:[^>"']|"[^"]*"|'[^']*')*>|\]\([^)]*\)/g
const PARAGRAPH_BREAK_RE = /\n\s*\n/
/** Punctuation allowed between the words of a multi-word term (quotations). */
const INNER_PUNCTUATION_RE = /^[,;:.?!׃"'’“”׳״]*$/
/** Longest term looked up (mirrors backend MAX_LOOKUP_WORDS). */
const MAX_TERM_WORDS = 40
/** Skipped when looking back for a sentence start. */
const SENTENCE_LEAD_RE = /[ \t*_>#+`«"“(\-]/
const SENTENCE_END_RE = /[.!?…:]/

export function normalizeHebrew(text: string): string {
  let value = (text || '').normalize('NFC').replace(CANTILLATION_RE, '').split(METEG).join('')
  value = Array.from(value, (char) =>
    SINGLE_QUOTES.includes(char) ? GERESH : DOUBLE_QUOTES.includes(char) ? GERSHAYIM : char,
  ).join('')
  return value.replace(WHITESPACE_RE, ' ').trim().normalize('NFC')
}

export function hebrewConsonants(text: string): string {
  return normalizeHebrew(text).replace(NIQQUD_RE, '').normalize('NFC')
}

/** Hebrew text without niqqud nor cantillation (display form for fluent readers). */
export function stripHebrewPoints(text: string): string {
  return (text || '').normalize('NFC').replace(ALL_POINTS_RE, '')
}

export interface HebrewTermIndex {
  byNorm: Map<string, LessonHebrewTerm>
  byConsonants: Map<string, LessonHebrewTerm>
  byId: Map<number, LessonHebrewTerm>
}

/** Lookup maps; on a key shared by several entries, a validated entry wins. */
export function buildHebrewTermIndex(terms: readonly LessonHebrewTerm[]): HebrewTermIndex {
  const index: HebrewTermIndex = { byNorm: new Map(), byConsonants: new Map(), byId: new Map() }
  const put = (map: Map<string, LessonHebrewTerm>, key: string, term: LessonHebrewTerm) => {
    const existing = map.get(key)
    if (!existing || (!existing.validated && term.validated)) map.set(key, term)
  }
  for (const term of terms) {
    index.byId.set(term.id, term)
    put(index.byNorm, term.hebrew_norm, term)
    put(index.byConsonants, term.hebrew_cons, term)
  }
  return index
}

interface HebrewToken {
  start: number // index of the Hebrew span in the text
  end: number
  span: string
  prefix: string // non-Hebrew characters of the word before / after the span
  suffix: string
  gapBefore: string // characters between the previous word and this one
}

/** Runs of consecutive Hebrew words of a paragraph (positions in the original text). */
function findHebrewRuns(text: string): HebrewToken[][] {
  const masked = text.replace(MASKED_RE, (match) => ' '.repeat(match.length))
  const runs: HebrewToken[][] = []
  let current: HebrewToken[] = []
  let previousEnd = 0
  for (const word of masked.matchAll(/\S+/g)) {
    const wordStart = word.index ?? 0
    const gap = masked.slice(previousEnd, wordStart)
    const originalGap = text.slice(previousEnd, wordStart)
    previousEnd = wordStart + word[0].length
    const match = HEBREW_SPAN_RE.exec(word[0])
    if (!match || PARAGRAPH_BREAK_RE.test(gap)) {
      if (current.length) runs.push(current)
      current = []
    }
    if (!match) continue
    const start = wordStart + match.index
    current.push({
      start,
      end: start + match[0].length,
      span: match[0],
      prefix: word[0].slice(0, match.index),
      suffix: word[0].slice(match.index + match[0].length),
      // A masked tag in the gap is not plain whitespace: the words cannot be joined.
      gapBefore: originalGap === gap ? gap : '<tag>',
    })
  }
  if (current.length) runs.push(current)
  return runs
}

/** Words `a` and `b` (consecutive) can belong to the same term. */
const joinable = (a: HebrewToken, b: HebrewToken): boolean =>
  INNER_PUNCTUATION_RE.test(a.suffix) && INNER_PUNCTUATION_RE.test(b.prefix) && /^\s+$/.test(b.gapBefore)

const lookup = (index: HebrewTermIndex, expression: string): LessonHebrewTerm | undefined =>
  index.byNorm.get(normalizeHebrew(expression)) ?? index.byConsonants.get(hebrewConsonants(expression))

interface TermMatch {
  start: number
  end: number
  original: string
  term: LessonHebrewTerm | null
}

/** Longest glossary match first, left to right; unmatched words are returned one by one. */
function matchRun(text: string, run: HebrewToken[], index: HebrewTermIndex): TermMatch[] {
  const matches: TermMatch[] = []
  let i = 0
  while (i < run.length) {
    let found: TermMatch | null = null
    let maxEnd = i + 1
    while (maxEnd < Math.min(run.length, i + MAX_TERM_WORDS) && joinable(run[maxEnd - 1], run[maxEnd])) maxEnd += 1
    for (let j = maxEnd; j > i && !found; j -= 1) {
      const term = lookup(index, run.slice(i, j).map((token) => token.span).join(' '))
      if (term) {
        found = { start: run[i].start, end: run[j - 1].end, original: '', term }
        i = j
      }
    }
    if (!found) {
      found = { start: run[i].start, end: run[i].end, original: '', term: null }
      i += 1
    }
    found.original = text.slice(found.start, found.end)
    matches.push(found)
  }
  return matches
}

const HTML_ESCAPES: Record<string, string> = {
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  // Markdown syntax characters, so inserted values are never parsed as markdown.
  '*': '&#42;', _: '&#95;', '`': '&#96;', '[': '&#91;', ']': '&#93;', '\\': '&#92;', '~': '&#126;',
}
const escapeHtml = (value: string): string => value.replace(/[&<>"'*_`[\]\\~]/g, (char) => HTML_ESCAPES[char])

const capitalize = (value: string): string => (value ? value.charAt(0).toLocaleUpperCase() + value.slice(1) : value)

/** Lowercase particles inside proper names ("Rabbi Chimon bar Yo'haï"). */
const NAME_PARTICLES = new Set(['bar', 'ben', 'bat', 'bne', 'ibn', 'de', 'ha', 'ou', 've'])

/** Proper-name capitalization: every word, except particles after the first word. */
const capitalizeName = (value: string): string =>
  value
    .split(' ')
    .map((word, position) => (position > 0 && NAME_PARTICLES.has(word.toLowerCase()) ? word : capitalize(word)))
    .join(' ')

/** True when the term starts a sentence, a line or the text. */
function isSentenceStart(text: string, position: number): boolean {
  for (let k = position - 1; k >= 0; k -= 1) {
    const char = text[k]
    if (char === '\n') return true
    if (SENTENCE_LEAD_RE.test(char)) continue
    return SENTENCE_END_RE.test(char)
  }
  return true
}

const hebrewHtml = (value: string): string => `<bdi lang="he" dir="rtl">${escapeHtml(value)}</bdi>`

const TERM_CLASS =
  'he-term cursor-help rounded-sm underline decoration-dotted decoration-indigo-400 underline-offset-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:decoration-indigo-500'
const SUPPLEMENT_CLASS = 'he-supp text-gray-500 dark:text-gray-400'

/** HTML of one glossary term in the user's display mode. */
function renderTerm(term: LessonHebrewTerm, settings: HebrewDisplaySettings, sentenceStart: boolean): string {
  const vocalized = term.hebrew
  const unvocalized = stripHebrewPoints(term.hebrew)
  const hebrewForm = settings.primary === 'unvocalized' ? unvocalized : vocalized
  const quotationInHebrew = term.type === 'quotation' && settings.quotations_in_hebrew
  let translit = term.translit
  if (translit && term.case_flag === 'capitalize') translit = capitalizeName(translit)
  else if (translit && sentenceStart) translit = capitalize(translit)

  // Primary form: a transliteration falls back to Hebrew while the entry has none.
  const primaryIsLatin = settings.primary === 'translit' && !quotationInHebrew && !!translit
  const primary = primaryIsLatin ? escapeHtml(translit as string) : hebrewHtml(hebrewForm)

  let supplement: string | null = null
  if (settings.supplement === 'translation' && term.translation) {
    supplement = escapeHtml(term.translation)
  } else if (settings.supplement === 'alternate') {
    // A long quotation is never transliterated: it stays in Hebrew only.
    if (primaryIsLatin) supplement = hebrewHtml(vocalized)
    else if (term.translit && !quotationInHebrew && term.type !== 'quotation') supplement = escapeHtml(term.translit)
  }

  const supplementHtml = supplement ? `<span class="${SUPPLEMENT_CLASS}"> (${supplement})</span>` : ''
  return `<span class="${TERM_CLASS}" data-he-term="${term.id}" tabindex="0">${primary}${supplementHtml}</span>`
}

/**
 * Markdown with every Hebrew term rendered in the user's display mode.
 * Words not found in the glossary stay as written (without points for
 * "Hebrew without niqqud").
 */
export function renderHebrewTerms(
  markdown: string,
  index: HebrewTermIndex,
  settings: HebrewDisplaySettings,
): string {
  if (!markdown) return markdown
  let output = ''
  let cursor = 0
  for (const run of findHebrewRuns(markdown)) {
    for (const match of matchRun(markdown, run, index)) {
      output += markdown.slice(cursor, match.start)
      if (match.term) {
        output += renderTerm(match.term, settings, isSentenceStart(markdown, match.start))
      } else {
        output += settings.primary === 'unvocalized' ? stripHebrewPoints(match.original) : match.original
      }
      cursor = match.end
    }
  }
  return output + markdown.slice(cursor)
}
