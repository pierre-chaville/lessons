<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Dialog, DialogPanel, DialogTitle, TransitionChild, TransitionRoot } from '@headlessui/vue'
import { CheckIcon } from '@heroicons/vue/24/outline'

import {
  GLOSSARY_CASE_FLAGS,
  GLOSSARY_SOURCES,
  GLOSSARY_STATUSES,
  GLOSSARY_TYPES,
} from '@/api/types'
import type {
  GlossaryCaseFlag,
  GlossaryEntry,
  GlossaryEntryCreate,
  GlossarySource,
  GlossaryStatus,
  GlossaryType,
} from '@/api/types'

const props = defineProps<{
  open: boolean
  /** Entry being edited; null to create a new one. */
  entry: GlossaryEntry | null
  saving: boolean
}>()

const emit = defineEmits<{
  close: []
  submit: [payload: GlossaryEntryCreate]
}>()

const { t } = useI18n()

interface FormState {
  hebrew: string
  translit: string
  aliasesInput: string
  type: GlossaryType
  case_flag: GlossaryCaseFlag
  status: GlossaryStatus
  source: GlossarySource
  translation: string
  sefaria_title: string
  sefaria_ref: string
  context_lesson: string
  context_paragraph: string
}

const form = ref<FormState>(emptyForm())
const hebrewError = ref('')

function emptyForm(): FormState {
  return {
    hebrew: '',
    translit: '',
    aliasesInput: '',
    type: 'term',
    case_flag: 'lower',
    status: 'validated',
    source: 'manual',
    translation: '',
    sefaria_title: '',
    sefaria_ref: '',
    context_lesson: '',
    context_paragraph: '',
  }
}

function formFromEntry(entry: GlossaryEntry): FormState {
  return {
    hebrew: entry.hebrew,
    translit: entry.translit ?? '',
    aliasesInput: entry.aliases.join(', '),
    type: entry.type,
    case_flag: entry.case_flag,
    status: entry.status,
    source: entry.source,
    translation: entry.translation ?? '',
    sefaria_title: entry.sefaria_title ?? '',
    sefaria_ref: entry.sefaria_ref ?? '',
    context_lesson: entry.context_lesson ?? '',
    context_paragraph: entry.context_paragraph ?? '',
  }
}

const parseAliases = (input: string): string[] => [
  ...new Set(input.split(/\r?\n|,/).map((v) => v.trim()).filter(Boolean)),
]

const optionalText = (value: string): string | null => value.trim() || null

const HEBREW_LETTER = /[א-ת]/

function submit() {
  const hebrew = form.value.hebrew.trim()
  if (!HEBREW_LETTER.test(hebrew)) {
    hebrewError.value = t('glossary.hebrewRequired')
    return
  }
  hebrewError.value = ''
  emit('submit', {
    hebrew,
    translit: optionalText(form.value.translit),
    aliases: parseAliases(form.value.aliasesInput),
    type: form.value.type,
    case_flag: form.value.case_flag,
    status: form.value.status,
    source: form.value.source,
    translation: optionalText(form.value.translation),
    sefaria_title: optionalText(form.value.sefaria_title),
    sefaria_ref: optionalText(form.value.sefaria_ref),
    context_lesson: optionalText(form.value.context_lesson),
    context_paragraph: optionalText(form.value.context_paragraph),
  })
}

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return
    form.value = props.entry ? formFromEntry(props.entry) : emptyForm()
    hebrewError.value = ''
  },
  { immediate: true },
)

const inputClass =
  'w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm dark:border-gray-600 dark:bg-gray-900 dark:text-gray-100'
const labelClass = 'mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300'
</script>

<template>
  <TransitionRoot :show="open" as="template">
    <Dialog class="relative z-50" @close="emit('close')">
      <TransitionChild
        as="template"
        enter="duration-200 ease-out"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="duration-150 ease-in"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
      </TransitionChild>
      <div class="fixed inset-0 flex items-center justify-center p-4">
        <TransitionChild
          as="template"
          enter="duration-200 ease-out"
          enter-from="opacity-0 scale-95"
          enter-to="opacity-100 scale-100"
          leave="duration-150 ease-in"
          leave-from="opacity-100 scale-100"
          leave-to="opacity-0 scale-95"
        >
          <DialogPanel class="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-lg bg-white shadow-xl dark:bg-gray-800">
            <DialogTitle class="px-6 pt-6 text-lg font-semibold text-gray-900 dark:text-white">
              {{ entry ? t('glossary.editTitle') : t('glossary.createTitle') }}
            </DialogTitle>

            <form class="flex min-h-0 flex-1 flex-col" @submit.prevent="submit">
              <div class="grid min-h-0 flex-1 grid-cols-1 gap-4 overflow-y-auto px-6 py-4 sm:grid-cols-2">
                <div class="sm:col-span-2">
                  <label :class="labelClass" for="glossary-hebrew">{{ t('glossary.fields.hebrew') }} *</label>
                  <input
                    id="glossary-hebrew"
                    v-model="form.hebrew"
                    dir="rtl"
                    lang="he"
                    :class="[inputClass, 'text-lg']"
                  />
                  <p v-if="hebrewError" class="mt-1 text-xs text-red-600 dark:text-red-400">{{ hebrewError }}</p>
                  <p v-else-if="entry" class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('glossary.fields.hebrewCons') }} :
                    <span dir="rtl" lang="he">{{ entry.hebrew_cons }}</span>
                  </p>
                </div>

                <div>
                  <label :class="labelClass" for="glossary-translit">{{ t('glossary.fields.translit') }}</label>
                  <input id="glossary-translit" v-model="form.translit" :class="inputClass" />
                </div>
                <div>
                  <label :class="labelClass" for="glossary-translation">{{ t('glossary.fields.translation') }}</label>
                  <input id="glossary-translation" v-model="form.translation" :class="inputClass" />
                </div>

                <div class="sm:col-span-2">
                  <label :class="labelClass" for="glossary-aliases">{{ t('glossary.fields.aliases') }}</label>
                  <textarea id="glossary-aliases" v-model="form.aliasesInput" rows="2" :class="inputClass" />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{{ t('glossary.aliasesHint') }}</p>
                </div>

                <div>
                  <label :class="labelClass" for="glossary-type">{{ t('glossary.fields.type') }}</label>
                  <select id="glossary-type" v-model="form.type" :class="inputClass">
                    <option v-for="value in GLOSSARY_TYPES" :key="value" :value="value">
                      {{ t(`glossary.types.${value}`) }}
                    </option>
                  </select>
                </div>
                <div>
                  <label :class="labelClass" for="glossary-case">{{ t('glossary.fields.caseFlag') }}</label>
                  <select id="glossary-case" v-model="form.case_flag" :class="inputClass">
                    <option v-for="value in GLOSSARY_CASE_FLAGS" :key="value" :value="value">
                      {{ t(`glossary.caseFlags.${value}`) }}
                    </option>
                  </select>
                </div>
                <div>
                  <label :class="labelClass" for="glossary-status">{{ t('glossary.fields.status') }}</label>
                  <select id="glossary-status" v-model="form.status" :class="inputClass">
                    <option v-for="value in GLOSSARY_STATUSES" :key="value" :value="value">
                      {{ t(`glossary.statuses.${value}`) }}
                    </option>
                  </select>
                </div>
                <div>
                  <label :class="labelClass" for="glossary-source">{{ t('glossary.fields.source') }}</label>
                  <select id="glossary-source" v-model="form.source" :class="inputClass">
                    <option v-for="value in GLOSSARY_SOURCES" :key="value" :value="value">
                      {{ t(`glossary.sources.${value}`) }}
                    </option>
                  </select>
                </div>

                <div>
                  <label :class="labelClass" for="glossary-sefaria-title">{{ t('glossary.fields.sefariaTitle') }}</label>
                  <input id="glossary-sefaria-title" v-model="form.sefaria_title" :class="inputClass" />
                </div>
                <div>
                  <label :class="labelClass" for="glossary-sefaria-ref">{{ t('glossary.fields.sefariaRef') }}</label>
                  <input id="glossary-sefaria-ref" v-model="form.sefaria_ref" :class="inputClass" />
                </div>

                <div class="sm:col-span-2">
                  <label :class="labelClass" for="glossary-context-lesson">{{ t('glossary.fields.contextLesson') }}</label>
                  <input id="glossary-context-lesson" v-model="form.context_lesson" :class="inputClass" />
                </div>
                <div class="sm:col-span-2">
                  <label :class="labelClass" for="glossary-context-paragraph">{{ t('glossary.fields.contextParagraph') }}</label>
                  <textarea id="glossary-context-paragraph" v-model="form.context_paragraph" rows="3" dir="auto" :class="inputClass" />
                </div>
              </div>

              <div class="flex justify-end gap-2 border-t border-gray-200 px-6 py-4 dark:border-gray-700">
                <button
                  type="button"
                  class="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 dark:border-gray-600 dark:text-gray-300"
                  @click="emit('close')"
                >
                  {{ t('lessons.cancel') }}
                </button>
                <button
                  type="submit"
                  class="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                  :disabled="saving"
                >
                  <CheckIcon class="h-4 w-4" />
                  {{ saving ? t('glossary.saving') : entry ? t('glossary.save') : t('glossary.create') }}
                </button>
              </div>
            </form>
          </DialogPanel>
        </TransitionChild>
      </div>
    </Dialog>
  </TransitionRoot>
</template>
