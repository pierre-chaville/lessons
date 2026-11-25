<script setup lang="ts">
/**
 * Wraps lesson text rendered by `renderHebrewTerms` (see utils/hebrewText.ts):
 * - "first occurrence only": hides the supplementary form of repeated terms,
 *   in document order, inside this element;
 * - tooltip on every glossary term (hover, focus, click/tap) with all its forms.
 *
 * Headless UI has no tooltip: one shared floating panel is used for all terms
 * (a lesson can contain hundreds), driven by event delegation.
 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ArrowTopRightOnSquareIcon } from '@heroicons/vue/24/outline'
import { useI18n } from 'vue-i18n'

import type { LessonHebrewTerm } from '@/api/types'
import { useHebrewDisplay } from '@/composables/useHebrewDisplay'
import { sefariaUrl } from '@/utils/sefaria'

const props = defineProps<{
  terms: ReadonlyMap<number, LessonHebrewTerm>
}>()

const TOOLTIP_ID = `he-term-tooltip-${Math.random().toString(36).slice(2, 8)}`
const HIDE_DELAY_MS = 200
const GAP_PX = 6
const MARGIN_PX = 8

const { t } = useI18n()
const { settings } = useHebrewDisplay()

const root = ref<HTMLElement | null>(null)
const tooltip = ref<HTMLElement | null>(null)
const activeTerm = ref<LessonHebrewTerm | null>(null)
const position = ref({ top: 0, left: 0 })
let anchor: HTMLElement | null = null
let pinned = false
let hideTimer: ReturnType<typeof setTimeout> | null = null
let observer: MutationObserver | null = null

const termElement = (target: EventTarget | null): HTMLElement | null =>
  target instanceof Element ? target.closest<HTMLElement>('.he-term[data-he-term]') : null

const inTooltip = (target: EventTarget | null): boolean =>
  target instanceof Node && !!tooltip.value?.contains(target)

/** Supplementary form on the first occurrence of each term only (when chosen). */
const applyFrequency = () => {
  if (!root.value) return
  const firstOnly = settings.value.frequency === 'first'
  const seen = new Set<string>()
  root.value.querySelectorAll<HTMLElement>('.he-term[data-he-term]').forEach((element) => {
    const id = element.dataset.heTerm ?? ''
    const supplement = element.querySelector<HTMLElement>('.he-supp')
    if (supplement) supplement.hidden = firstOnly && seen.has(id)
    seen.add(id)
  })
}

const cancelHide = () => {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = null
}

const hide = () => {
  cancelHide()
  anchor?.removeAttribute('aria-describedby')
  anchor = null
  pinned = false
  activeTerm.value = null
}

const scheduleHide = () => {
  if (pinned) return
  cancelHide()
  hideTimer = setTimeout(hide, HIDE_DELAY_MS)
}

const place = () => {
  if (!anchor || !tooltip.value) return
  if (!anchor.isConnected) {
    hide()
    return
  }
  const rect = anchor.getBoundingClientRect()
  const { offsetWidth: width, offsetHeight: height } = tooltip.value
  let top = rect.bottom + GAP_PX
  if (top + height > window.innerHeight - MARGIN_PX && rect.top - height - GAP_PX > MARGIN_PX) {
    top = rect.top - height - GAP_PX
  }
  const left = Math.min(Math.max(MARGIN_PX, rect.left), window.innerWidth - width - MARGIN_PX)
  position.value = { top, left: Math.max(MARGIN_PX, left) }
}

const show = async (element: HTMLElement) => {
  const term = props.terms.get(Number(element.dataset.heTerm))
  if (!term) return
  cancelHide()
  if (anchor !== element) {
    anchor?.removeAttribute('aria-describedby')
    pinned = false
  }
  anchor = element
  anchor.setAttribute('aria-describedby', TOOLTIP_ID)
  activeTerm.value = term
  await nextTick()
  place()
}

const onMouseOver = (event: MouseEvent) => {
  const element = termElement(event.target)
  if (element) void show(element)
}

const onMouseOut = (event: MouseEvent) => {
  const element = termElement(event.target)
  if (element && termElement(event.relatedTarget) !== element && !inTooltip(event.relatedTarget)) scheduleHide()
}

const onFocusIn = (event: FocusEvent) => {
  const element = termElement(event.target)
  if (element) void show(element)
}

const onFocusOut = (event: FocusEvent) => {
  if (termElement(event.target) && !inTooltip(event.relatedTarget)) scheduleHide()
}

/** Click / tap / Enter keeps the tooltip open (touch screens have no hover). */
const togglePinned = (element: HTMLElement) => {
  if (pinned && anchor === element) {
    hide()
    return
  }
  void show(element).then(() => {
    if (activeTerm.value) pinned = true
  })
}

const onClick = (event: MouseEvent) => {
  const element = termElement(event.target)
  if (element) togglePinned(element)
}

const onKeyDown = (event: KeyboardEvent) => {
  const element = termElement(event.target)
  if (element && (event.key === 'Enter' || event.key === ' ')) {
    event.preventDefault()
    togglePinned(element)
  }
}

const onDocumentKeyDown = (event: KeyboardEvent) => {
  if (event.key !== 'Escape' || !activeTerm.value) return
  const element = anchor
  hide()
  element?.focus()
}

const onDocumentPointerDown = (event: PointerEvent) => {
  if (activeTerm.value && !termElement(event.target) && !inTooltip(event.target)) hide()
}

const onViewportChange = () => {
  if (activeTerm.value) place()
}

watch(() => settings.value.frequency, () => nextTick(applyFrequency))

onMounted(() => {
  applyFrequency()
  // Text re-rendered (v-html, tab content, settings): re-apply on the new DOM.
  observer = new MutationObserver(() => {
    applyFrequency()
    if (anchor && !anchor.isConnected) hide()
  })
  if (root.value) observer.observe(root.value, { childList: true, subtree: true, characterData: true })
  document.addEventListener('keydown', onDocumentKeyDown)
  document.addEventListener('pointerdown', onDocumentPointerDown)
  window.addEventListener('scroll', onViewportChange, true)
  window.addEventListener('resize', onViewportChange)
})

onBeforeUnmount(() => {
  observer?.disconnect()
  cancelHide()
  document.removeEventListener('keydown', onDocumentKeyDown)
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  window.removeEventListener('scroll', onViewportChange, true)
  window.removeEventListener('resize', onViewportChange)
})
</script>

<template>
  <div
    ref="root"
    @mouseover="onMouseOver"
    @mouseout="onMouseOut"
    @focusin="onFocusIn"
    @focusout="onFocusOut"
    @click="onClick"
    @keydown="onKeyDown"
  >
    <slot />
  </div>

  <Teleport to="body">
    <div
      v-if="activeTerm"
      :id="TOOLTIP_ID"
      ref="tooltip"
      role="tooltip"
      class="fixed z-50 w-72 max-w-[calc(100vw-1rem)] rounded-lg border border-gray-200 bg-white p-3 text-sm shadow-lg dark:border-gray-700 dark:bg-gray-800"
      :style="{ top: `${position.top}px`, left: `${position.left}px` }"
      @mouseenter="cancelHide"
      @mouseleave="scheduleHide"
    >
      <div class="flex items-start justify-between gap-2">
        <span class="rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600 dark:bg-gray-700 dark:text-gray-300">
          {{ t(`glossary.types.${activeTerm.type}`) }}
        </span>
        <p class="text-right text-xl leading-snug text-gray-900 dark:text-gray-100" dir="rtl" lang="he">
          {{ activeTerm.hebrew }}
        </p>
      </div>
      <dl class="mt-2 space-y-1">
        <div v-if="activeTerm.translit" class="flex gap-2">
          <dt class="w-24 flex-shrink-0 text-xs text-gray-500 dark:text-gray-400">{{ t('hebrewDisplay.tooltip.translit') }}</dt>
          <dd class="italic text-gray-800 dark:text-gray-200">{{ activeTerm.translit }}</dd>
        </div>
        <div v-if="activeTerm.translation" class="flex gap-2">
          <dt class="w-24 flex-shrink-0 text-xs text-gray-500 dark:text-gray-400">{{ t('hebrewDisplay.tooltip.translation') }}</dt>
          <dd class="text-gray-800 dark:text-gray-200">{{ activeTerm.translation }}</dd>
        </div>
      </dl>
      <a
        v-if="activeTerm.sefaria_ref || activeTerm.sefaria_title"
        :href="sefariaUrl(activeTerm.sefaria_ref || activeTerm.sefaria_title || '')"
        target="_blank"
        rel="noopener"
        class="mt-2 inline-flex items-center gap-1 text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
      >
        {{ t('hebrewDisplay.tooltip.sefaria', { ref: activeTerm.sefaria_ref || activeTerm.sefaria_title }) }}
        <ArrowTopRightOnSquareIcon class="h-3.5 w-3.5" aria-hidden="true" />
      </a>
      <p v-if="!activeTerm.validated" class="mt-2 text-[11px] italic text-gray-400 dark:text-gray-500">
        {{ t('hebrewDisplay.tooltip.notValidated') }}
      </p>
    </div>
  </Teleport>
</template>
