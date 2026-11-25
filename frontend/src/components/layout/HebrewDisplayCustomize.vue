<script setup lang="ts">
import { RadioGroup, RadioGroupLabel, RadioGroupOption } from '@headlessui/vue'
import { useI18n } from 'vue-i18n'

import {
  HEBREW_PRIMARY_FORMS,
  HEBREW_SUPPLEMENT_FORMS,
  HEBREW_SUPPLEMENT_FREQUENCIES,
  useHebrewDisplay,
} from '@/composables/useHebrewDisplay'
import type {
  HebrewPrimaryForm,
  HebrewSupplementForm,
  HebrewSupplementFrequency,
} from '@/composables/useHebrewDisplay'

const { t } = useI18n()
const { settings, update } = useHebrewDisplay()

const optionClass = (checked: boolean, disabled = false) => [
  checked
    ? 'border-indigo-600 bg-indigo-50 text-indigo-700 dark:border-indigo-400 dark:bg-indigo-900/30 dark:text-indigo-200'
    : 'border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-700',
  disabled ? 'cursor-not-allowed opacity-40' : 'cursor-pointer',
  'rounded-md border px-2.5 py-1 text-xs font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500',
]
</script>

<template>
  <div class="space-y-4">
    <RadioGroup
      :model-value="settings.primary"
      @update:model-value="(value: HebrewPrimaryForm) => update({ primary: value })"
    >
      <RadioGroupLabel class="mb-1.5 block text-xs font-semibold text-gray-700 dark:text-gray-300">
        {{ t('hebrewDisplay.primary.label') }}
      </RadioGroupLabel>
      <div class="flex flex-wrap gap-1.5">
        <RadioGroupOption
          v-for="value in HEBREW_PRIMARY_FORMS"
          :key="value"
          v-slot="{ checked }"
          :value="value"
          as="template"
        >
          <span :class="optionClass(checked)">{{ t(`hebrewDisplay.primary.${value}`) }}</span>
        </RadioGroupOption>
      </div>
    </RadioGroup>

    <RadioGroup
      :model-value="settings.supplement"
      @update:model-value="(value: HebrewSupplementForm) => update({ supplement: value })"
    >
      <RadioGroupLabel class="mb-1.5 block text-xs font-semibold text-gray-700 dark:text-gray-300">
        {{ t('hebrewDisplay.supplement.label') }}
      </RadioGroupLabel>
      <div class="flex flex-wrap gap-1.5">
        <RadioGroupOption
          v-for="value in HEBREW_SUPPLEMENT_FORMS"
          :key="value"
          v-slot="{ checked }"
          :value="value"
          as="template"
        >
          <span :class="optionClass(checked)">
            {{
              value === 'alternate'
                ? t(settings.primary === 'translit' ? 'hebrewDisplay.supplement.hebrew' : 'hebrewDisplay.supplement.translit')
                : t(`hebrewDisplay.supplement.${value}`)
            }}
          </span>
        </RadioGroupOption>
      </div>
    </RadioGroup>

    <RadioGroup
      :model-value="settings.frequency"
      :disabled="settings.supplement === 'none'"
      @update:model-value="(value: HebrewSupplementFrequency) => update({ frequency: value })"
    >
      <RadioGroupLabel class="mb-1.5 block text-xs font-semibold text-gray-700 dark:text-gray-300">
        {{ t('hebrewDisplay.frequency.label') }}
      </RadioGroupLabel>
      <div class="flex flex-wrap gap-1.5">
        <RadioGroupOption
          v-for="value in HEBREW_SUPPLEMENT_FREQUENCIES"
          :key="value"
          v-slot="{ checked, disabled }"
          :value="value"
          as="template"
        >
          <span :class="optionClass(checked && !disabled, disabled)">{{ t(`hebrewDisplay.frequency.${value}`) }}</span>
        </RadioGroupOption>
      </div>
    </RadioGroup>
  </div>
</template>
