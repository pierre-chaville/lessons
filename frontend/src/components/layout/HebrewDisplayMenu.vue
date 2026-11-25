<script setup lang="ts">
import { computed, onMounted } from 'vue'
import {
  Disclosure,
  DisclosureButton,
  DisclosurePanel,
  Popover,
  PopoverButton,
  PopoverPanel,
  RadioGroup,
  RadioGroupLabel,
  RadioGroupOption,
  Switch,
  SwitchGroup,
  SwitchLabel,
} from '@headlessui/vue'
import { ChevronDownIcon } from '@heroicons/vue/24/outline'
import { useI18n } from 'vue-i18n'

import HebrewDisplayCustomize from '@/components/layout/HebrewDisplayCustomize.vue'
import {
  HEBREW_DISPLAY_PRESETS,
  HEBREW_DISPLAY_PRESET_IDS,
  useHebrewDisplay,
} from '@/composables/useHebrewDisplay'
import type { HebrewDisplayForms, HebrewDisplayPresetId } from '@/composables/useHebrewDisplay'

// Sample term used to preview each display mode (a Hebrew term: not translated).
const SAMPLE_TERM = { translit: 'techouva', vocalized: 'תְּשׁוּבָה', unvocalized: 'תשובה' } as const

const { t } = useI18n()
const { settings, activePreset, applyPreset, update, loadFromServer, saveFailed } = useHebrewDisplay()

const currentLabel = computed(() =>
  activePreset.value ? t(`hebrewDisplay.presets.${activePreset.value}.name`) : t('hebrewDisplay.custom'),
)

const supplementOf = (forms: HebrewDisplayForms): string | null => {
  if (forms.supplement === 'translation') return t('hebrewDisplay.sampleTranslation')
  if (forms.supplement === 'alternate') {
    return forms.primary === 'translit' ? SAMPLE_TERM.vocalized : SAMPLE_TERM.translit
  }
  return null
}

/** Two occurrences of the sample term, to show the supplementary form and its frequency. */
const exampleOf = (forms: HebrewDisplayForms): string => {
  const primary = SAMPLE_TERM[forms.primary]
  const supplement = supplementOf(forms)
  const first = supplement ? `${primary} (${supplement})` : primary
  const next = supplement && forms.frequency === 'every' ? first : primary
  return t('hebrewDisplay.example', { first, next })
}

const currentExample = computed(() => exampleOf(settings.value))

onMounted(loadFromServer)
</script>

<template>
  <Popover class="relative">
    <PopoverButton
      :title="t('hebrewDisplay.buttonTitle', { mode: currentLabel })"
      :aria-label="t('hebrewDisplay.buttonTitle', { mode: currentLabel })"
      class="inline-flex items-center justify-center rounded-md p-2 text-gray-700 hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 dark:text-gray-300 dark:hover:bg-gray-700 transition-colors"
    >
      <span class="flex h-5 w-5 items-center justify-center text-base font-semibold leading-none" lang="he" aria-hidden="true">אב</span>
    </PopoverButton>

    <transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="transform opacity-0 scale-95"
      enter-to-class="transform opacity-100 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="transform opacity-100 scale-100"
      leave-to-class="transform opacity-0 scale-95"
    >
      <PopoverPanel
        class="absolute right-0 z-20 mt-2 max-h-[80vh] w-[22rem] max-w-[calc(100vw-2rem)] origin-top-right overflow-y-auto rounded-lg bg-white p-4 shadow-lg ring-1 ring-black/5 focus:outline-none dark:bg-gray-800 dark:ring-white/10"
      >
        <h2 class="text-sm font-semibold text-gray-900 dark:text-white">{{ t('hebrewDisplay.title') }}</h2>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ t('hebrewDisplay.description') }}</p>

        <RadioGroup
          :model-value="activePreset ?? undefined"
          class="mt-3"
          @update:model-value="(id: HebrewDisplayPresetId) => applyPreset(id)"
        >
          <RadioGroupLabel class="sr-only">{{ t('hebrewDisplay.presetsLabel') }}</RadioGroupLabel>
          <div class="space-y-1.5">
            <RadioGroupOption
              v-for="id in HEBREW_DISPLAY_PRESET_IDS"
              :key="id"
              v-slot="{ checked }"
              :value="id"
              as="template"
            >
              <div
                :class="[
                  checked
                    ? 'border-indigo-600 bg-indigo-50 dark:border-indigo-400 dark:bg-indigo-900/30'
                    : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-700/50',
                  'cursor-pointer rounded-md border px-3 py-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500',
                ]"
              >
                <div class="flex items-center justify-between gap-2">
                  <RadioGroupLabel as="span" class="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {{ t(`hebrewDisplay.presets.${id}.name`) }}
                  </RadioGroupLabel>
                  <span v-if="id === 'standard'" class="text-[11px] text-gray-500 dark:text-gray-400">
                    {{ t('hebrewDisplay.defaultBadge') }}
                  </span>
                </div>
                <p class="mt-0.5 text-xs text-gray-600 dark:text-gray-400" dir="auto">
                  {{ exampleOf(HEBREW_DISPLAY_PRESETS[id]) }}
                </p>
              </div>
            </RadioGroupOption>
          </div>
        </RadioGroup>

        <Disclosure v-slot="{ open }" :default-open="activePreset === null" as="div" class="mt-3 border-t border-gray-200 pt-3 dark:border-gray-700">
          <DisclosureButton class="flex w-full items-center justify-between text-sm font-medium text-gray-700 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white">
            <span>
              {{ t('hebrewDisplay.customize') }}
              <span v-if="activePreset === null" class="ml-1 text-xs font-normal text-indigo-600 dark:text-indigo-400">({{ t('hebrewDisplay.custom') }})</span>
            </span>
            <ChevronDownIcon :class="[open ? 'rotate-180' : '', 'h-4 w-4 transition-transform']" aria-hidden="true" />
          </DisclosureButton>
          <DisclosurePanel class="mt-3">
            <HebrewDisplayCustomize />
            <p class="mt-3 rounded-md bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-900/50 dark:text-gray-400" dir="auto">
              {{ currentExample }}
            </p>
          </DisclosurePanel>
        </Disclosure>

        <SwitchGroup as="div" class="mt-3 flex items-start justify-between gap-3 border-t border-gray-200 pt-3 dark:border-gray-700">
          <div>
            <SwitchLabel class="text-sm font-medium text-gray-700 dark:text-gray-300">
              {{ t('hebrewDisplay.quotations.label') }}
            </SwitchLabel>
            <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('hebrewDisplay.quotations.description') }}</p>
          </div>
          <Switch
            :model-value="settings.quotations_in_hebrew"
            :class="[
              settings.quotations_in_hebrew ? 'bg-indigo-600' : 'bg-gray-300 dark:bg-gray-600',
              'relative inline-flex h-5 w-9 flex-shrink-0 rounded-full transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500',
            ]"
            @update:model-value="(value: boolean) => update({ quotations_in_hebrew: value })"
          >
            <span
              :class="[
                settings.quotations_in_hebrew ? 'translate-x-4' : 'translate-x-0.5',
                'mt-0.5 inline-block h-4 w-4 rounded-full bg-white shadow transition-transform',
              ]"
            />
          </Switch>
        </SwitchGroup>

        <p v-if="saveFailed" role="alert" class="mt-3 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-900/30 dark:text-red-300">
          {{ t('hebrewDisplay.saveFailed') }}
        </p>
      </PopoverPanel>
    </transition>
  </Popover>
</template>
