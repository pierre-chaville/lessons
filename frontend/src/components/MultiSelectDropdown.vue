<script setup lang="ts" generic="T extends string | number">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckIcon, ChevronUpDownIcon, MagnifyingGlassIcon, XMarkIcon } from '@heroicons/vue/24/outline'

export interface MultiSelectOption<T extends string | number = string | number> {
  value: T
  label: string
}

const props = withDefaults(defineProps<{
  modelValue: T[]
  options: MultiSelectOption<T>[]
  placeholder: string
  disabled?: boolean
  accent?: 'indigo' | 'sky'
}>(), {
  disabled: false,
  accent: 'indigo',
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: T[]): void
}>()

const { t } = useI18n()

const open = ref(false)
const query = ref('')
const root = ref<HTMLElement | null>(null)
const searchInput = ref<HTMLInputElement | null>(null)

const filteredOptions = computed(() => {
  const needle = query.value.trim().toLowerCase()
  if (!needle) return props.options
  return props.options.filter((option) => option.label.toLowerCase().includes(needle))
})

const selectedOptions = computed(() => {
  const byValue = new Map(props.options.map((option) => [option.value, option]))
  return props.modelValue
    .map((value) => byValue.get(value))
    .filter((option): option is MultiSelectOption<T> => !!option)
})

const isSelected = (value: T) => props.modelValue.includes(value)

const toggle = (value: T) => {
  if (props.disabled) return
  if (isSelected(value)) {
    emit('update:modelValue', props.modelValue.filter((item) => item !== value))
    return
  }
  emit('update:modelValue', [...props.modelValue, value])
}

const remove = (value: T) => {
  if (props.disabled) return
  emit('update:modelValue', props.modelValue.filter((item) => item !== value))
}

const close = () => {
  open.value = false
}

const toggleOpen = () => {
  if (props.disabled) return
  open.value = !open.value
}

const onDocumentPointerDown = (event: MouseEvent) => {
  if (!root.value?.contains(event.target as Node)) close()
}

watch(open, async (isOpen) => {
  if (!isOpen) {
    query.value = ''
    return
  }
  await nextTick()
  searchInput.value?.focus()
})

onMounted(() => document.addEventListener('mousedown', onDocumentPointerDown))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocumentPointerDown))

const chipClass = computed(() =>
  props.accent === 'sky'
    ? 'bg-sky-600 text-white'
    : 'bg-indigo-600 text-white',
)

const checkClass = computed(() =>
  props.accent === 'sky'
    ? 'border-sky-600 bg-sky-600'
    : 'border-indigo-600 bg-indigo-600',
)
</script>

<template>
  <div ref="root" class="relative">
    <div
      class="flex items-stretch rounded-md border bg-white dark:bg-gray-900 transition-colors"
      :class="[
        disabled ? 'opacity-50' : '',
        open
          ? 'border-indigo-500 ring-2 ring-indigo-500'
          : 'border-gray-300 dark:border-gray-600',
      ]"
    >
      <div
        class="flex min-h-[42px] flex-1 flex-wrap items-center gap-1 px-2 py-1.5"
        :class="disabled ? '' : 'cursor-pointer'"
        @click="toggleOpen"
      >
        <span
          v-if="selectedOptions.length === 0"
          class="px-1 text-sm text-gray-400 dark:text-gray-500"
        >
          {{ placeholder }}
        </span>
        <span
          v-for="option in selectedOptions"
          :key="String(option.value)"
          class="inline-flex max-w-full items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium"
          :class="chipClass"
        >
          <span class="truncate">{{ option.label }}</span>
          <button
            type="button"
            class="rounded-full p-0.5 hover:bg-white/20"
            :title="t('lessons.remove')"
            :disabled="disabled"
            @click.stop="remove(option.value)"
          >
            <XMarkIcon class="h-3 w-3" />
          </button>
        </span>
      </div>
      <button
        type="button"
        class="flex items-center px-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
        :disabled="disabled"
        :aria-expanded="open"
        :aria-label="placeholder"
        @click="toggleOpen"
      >
        <ChevronUpDownIcon class="h-5 w-5" />
      </button>
    </div>

    <div
      v-if="open"
      class="mt-1 overflow-hidden rounded-md border border-gray-200 bg-white shadow-lg dark:border-gray-600 dark:bg-gray-800"
    >
      <div class="border-b border-gray-200 p-2 dark:border-gray-700">
        <div class="relative">
          <MagnifyingGlassIcon class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
          <input
            ref="searchInput"
            v-model="query"
            type="text"
            :placeholder="t('lessons.searchOptions')"
            class="w-full rounded-md border border-gray-300 bg-white py-1.5 pl-8 pr-3 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 dark:border-gray-600 dark:bg-gray-900 dark:text-white"
            @keydown.escape.prevent.stop="close"
            @keydown.enter.prevent
          />
        </div>
      </div>
      <ul class="max-h-60 overflow-y-auto py-1">
        <li v-if="filteredOptions.length === 0" class="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">
          {{ t('lessons.noMatches') }}
        </li>
        <li v-for="option in filteredOptions" :key="String(option.value)">
          <button
            type="button"
            class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-gray-800 hover:bg-gray-50 dark:text-gray-100 dark:hover:bg-gray-700/60"
            @click="toggle(option.value)"
          >
            <span
              class="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border"
              :class="isSelected(option.value) ? checkClass : 'border-gray-300 bg-white dark:border-gray-500 dark:bg-gray-900'"
            >
              <CheckIcon v-if="isSelected(option.value)" class="h-3 w-3 text-white" />
            </span>
            <span class="truncate">{{ option.label }}</span>
          </button>
        </li>
      </ul>
    </div>
  </div>
</template>
