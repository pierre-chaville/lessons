import { computed, ref, watch } from 'vue'

import { meApi } from '@/api/me'
import type {
  HebrewDisplaySettings,
  HebrewPrimaryForm,
  HebrewSupplementForm,
  HebrewSupplementFrequency,
} from '@/api/types'

export type { HebrewDisplaySettings, HebrewPrimaryForm, HebrewSupplementForm, HebrewSupplementFrequency }

export type HebrewDisplayPresetId = 'beginner' | 'standard' | 'bilingual' | 'advanced' | 'fluent'

export type HebrewDisplayForms = Pick<HebrewDisplaySettings, 'primary' | 'supplement' | 'frequency'>

export const HEBREW_PRIMARY_FORMS: readonly HebrewPrimaryForm[] = ['translit', 'vocalized', 'unvocalized']
export const HEBREW_SUPPLEMENT_FORMS: readonly HebrewSupplementForm[] = ['none', 'alternate', 'translation']
export const HEBREW_SUPPLEMENT_FREQUENCIES: readonly HebrewSupplementFrequency[] = ['first', 'every']

/** Presets set the three forms; the quotation setting is independent. */
export const HEBREW_DISPLAY_PRESETS: Readonly<Record<HebrewDisplayPresetId, HebrewDisplayForms>> = {
  beginner: { primary: 'translit', supplement: 'translation', frequency: 'first' },
  standard: { primary: 'translit', supplement: 'none', frequency: 'first' },
  bilingual: { primary: 'translit', supplement: 'alternate', frequency: 'first' },
  advanced: { primary: 'vocalized', supplement: 'none', frequency: 'first' },
  fluent: { primary: 'unvocalized', supplement: 'none', frequency: 'first' },
}
export const HEBREW_DISPLAY_PRESET_IDS = Object.keys(HEBREW_DISPLAY_PRESETS) as HebrewDisplayPresetId[]
export const DEFAULT_HEBREW_DISPLAY_PRESET: HebrewDisplayPresetId = 'standard'

/** Local cache: settings show up immediately on load, before the server answers. */
const CACHE_KEY = 'hebrewDisplay'
const SAVE_DEBOUNCE_MS = 400

const defaultSettings = (): HebrewDisplaySettings => ({
  ...HEBREW_DISPLAY_PRESETS[DEFAULT_HEBREW_DISPLAY_PRESET],
  quotations_in_hebrew: true,
})

const pick = <T extends string>(value: unknown, allowed: readonly T[], fallback: T): T =>
  allowed.includes(value as T) ? (value as T) : fallback

/** Invalid or missing values fall back to the defaults. */
function sanitize(value: unknown): HebrewDisplaySettings {
  const defaults = defaultSettings()
  if (!value || typeof value !== 'object') return defaults
  const saved = value as Partial<Record<keyof HebrewDisplaySettings, unknown>>
  return {
    primary: pick(saved.primary, HEBREW_PRIMARY_FORMS, defaults.primary),
    supplement: pick(saved.supplement, HEBREW_SUPPLEMENT_FORMS, defaults.supplement),
    frequency: pick(saved.frequency, HEBREW_SUPPLEMENT_FREQUENCIES, defaults.frequency),
    quotations_in_hebrew:
      typeof saved.quotations_in_hebrew === 'boolean' ? saved.quotations_in_hebrew : defaults.quotations_in_hebrew,
  }
}

function readCache(): HebrewDisplaySettings {
  try {
    const raw = localStorage.getItem(CACHE_KEY)
    return raw ? sanitize(JSON.parse(raw)) : defaultSettings()
  } catch {
    return defaultSettings()
  }
}

function writeCache(value: HebrewDisplaySettings): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(value))
  } catch {
    // Storage unavailable (private mode...): the server copy is still saved.
  }
}

/** Frequency only matters when a supplementary form is shown. */
const sameForms = (a: HebrewDisplayForms, b: HebrewDisplayForms): boolean =>
  a.primary === b.primary &&
  a.supplement === b.supplement &&
  (a.supplement === 'none' || a.frequency === b.frequency)

// Module-level state: one setting for the whole app, shared by every component.
const settings = ref<HebrewDisplaySettings>(readCache())
/** Server copy loaded: changes are saved to the server only after that, never over it blindly. */
const serverLoaded = ref(false)
const saveFailed = ref(false)
let loadPromise: Promise<void> | null = null
let applyingServerValue = false
let saveTimer: ReturnType<typeof setTimeout> | null = null

async function saveToServer(): Promise<void> {
  try {
    await meApi.updateHebrewDisplay(settings.value)
    saveFailed.value = false
  } catch {
    saveFailed.value = true
  }
}

watch(
  settings,
  (value) => {
    writeCache(value)
    if (applyingServerValue || !serverLoaded.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(saveToServer, SAVE_DEBOUNCE_MS)
  },
  // Sync: runs inside the assignment, so `applyingServerValue` is still set for server values.
  { deep: true, flush: 'sync' },
)

/**
 * Load the signed-in user's settings from the server (once per page load).
 * Never saved yet → defaults. On failure the cached settings stay in use and
 * the next call retries.
 */
function loadFromServer(): Promise<void> {
  if (!loadPromise) {
    loadPromise = meApi
      .getPreferences()
      .then((preferences) => {
        applyingServerValue = true
        try {
          settings.value = sanitize(preferences.hebrew_display)
        } finally {
          applyingServerValue = false
        }
        serverLoaded.value = true
      })
      .catch(() => {
        loadPromise = null
      })
  }
  return loadPromise
}

/**
 * How Hebrew terms are displayed in lessons — saved on the user's account
 * (shared across devices), cached in this browser.
 *
 * @example
 * const { settings, activePreset, applyPreset, loadFromServer } = useHebrewDisplay()
 */
export function useHebrewDisplay() {
  /** The preset matching the current forms, or `null` when customized. */
  const activePreset = computed<HebrewDisplayPresetId | null>(
    () => HEBREW_DISPLAY_PRESET_IDS.find((id) => sameForms(HEBREW_DISPLAY_PRESETS[id], settings.value)) ?? null,
  )

  const applyPreset = (id: HebrewDisplayPresetId): void => {
    settings.value = { ...settings.value, ...HEBREW_DISPLAY_PRESETS[id] }
  }

  const update = (patch: Partial<HebrewDisplaySettings>): void => {
    settings.value = { ...settings.value, ...patch }
  }

  return { settings, activePreset, applyPreset, update, loadFromServer, serverLoaded, saveFailed }
}
