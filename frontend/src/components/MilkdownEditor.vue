<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Crepe } from '@milkdown/crepe'
import '@milkdown/crepe/theme/common/style.css'
import '@milkdown/crepe/theme/frame.css'

const props = withDefaults(defineProps<{
  modelValue: string
  placeholder?: string
  disabled?: boolean
}>(), {
  placeholder: '',
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void
}>()

const rootEl = ref<HTMLDivElement | null>(null)
const isDarkMode = ref(false)
let editor: Crepe | null = null
let darkModeObserver: MutationObserver | null = null

const syncDarkMode = () => {
  isDarkMode.value = document.documentElement.classList.contains('dark')
}

onMounted(async () => {
  if (!rootEl.value) return

  syncDarkMode()
  darkModeObserver = new MutationObserver(syncDarkMode)
  darkModeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['class'],
  })

  editor = new Crepe({
    root: rootEl.value,
    defaultValue: props.modelValue || '',
    features: {
      [Crepe.Feature.BlockEdit]: true,
      [Crepe.Feature.Toolbar]: true,
      [Crepe.Feature.TopBar]: true,
    },
    featureConfigs: {
      [Crepe.Feature.Placeholder]: {
        text: props.placeholder,
      },
    },
  })

  editor.on((listener) => {
    listener.markdownUpdated((_ctx, markdown) => {
      emit('update:modelValue', markdown)
    })
  })

  await editor.create()
  editor.setReadonly(!!props.disabled)
})

watch(() => props.disabled, (disabled) => {
  editor?.setReadonly(!!disabled)
})

onBeforeUnmount(() => {
  darkModeObserver?.disconnect()
  darkModeObserver = null
  editor?.destroy()
  editor = null
})
</script>

<template>
  <div
    class="milkdown-editor rounded-lg border border-gray-300 dark:border-gray-600"
    :class="{ 'milkdown-editor--dark': isDarkMode }"
  >
    <div ref="rootEl" class="milkdown-editor-root min-h-[24rem]" />
  </div>
</template>

<style scoped>
.milkdown-editor :deep(.milkdown) {
  border: none;
  --crepe-color-background: #ffffff;
  --crepe-color-on-background: #111827;
  --crepe-color-surface: #f9fafb;
  --crepe-color-surface-low: #f3f4f6;
  --crepe-color-on-surface: #111827;
  --crepe-color-on-surface-variant: #4b5563;
  --crepe-color-outline: #d1d5db;
  --crepe-color-primary: #111827;
  --crepe-color-secondary: #e5e7eb;
  --crepe-color-on-secondary: #111827;
  --crepe-color-inverse: #111827;
  --crepe-color-on-inverse: #f9fafb;
  --crepe-color-inline-code: #be123c;
  --crepe-color-error: #dc2626;
  --crepe-color-hover: #e5e7eb;
  --crepe-color-selected: #dbeafe;
  --crepe-color-inline-area: #f3f4f6;
}

.milkdown-editor :deep(.milkdown .ProseMirror) {
  min-height: 24rem;
  /* Keep extra left gutter so block add/drag controls stay visible */
  padding: 0.9rem 1rem 0.9rem 2.5rem;
}

.milkdown-editor :deep(.milkdown .editor) {
  background: transparent;
}

@media (min-width: 768px) {
  .milkdown-editor :deep(.milkdown .ProseMirror) {
    padding-left: 3.5rem;
  }
}

.milkdown-editor--dark :deep(.milkdown) {
  --crepe-color-background: #111827;
  --crepe-color-on-background: #f3f4f6;
  --crepe-color-surface: #0f172a;
  --crepe-color-surface-low: #1f2937;
  --crepe-color-on-surface: #e5e7eb;
  --crepe-color-on-surface-variant: #9ca3af;
  --crepe-color-outline: #374151;
  --crepe-color-primary: #e5e7eb;
  --crepe-color-secondary: #374151;
  --crepe-color-on-secondary: #e5e7eb;
  --crepe-color-inverse: #f3f4f6;
  --crepe-color-on-inverse: #111827;
  --crepe-color-inline-code: #fda4af;
  --crepe-color-error: #f87171;
  --crepe-color-hover: #1f2937;
  --crepe-color-selected: #1e3a8a;
  --crepe-color-inline-area: #374151;
}
</style>
