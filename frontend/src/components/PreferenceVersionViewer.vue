<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { configApi } from '@/api/config'

const props = defineProps<{
  versionId: string | null
}>()

const { t } = useI18n()
const loading = ref(false)
const error = ref<string | null>(null)
const yaml = ref('')

const loadVersion = async () => {
  if (!props.versionId) {
    yaml.value = ''
    return
  }
  loading.value = true
  error.value = null
  try {
    yaml.value = await configApi.getVersionYaml(props.versionId)
  } catch (e: any) {
    yaml.value = ''
    error.value = e?.response?.data?.detail || t('history.versionLoadFailed')
  } finally {
    loading.value = false
  }
}

watch(
  () => props.versionId,
  loadVersion,
  { immediate: true },
)
</script>

<template>
  <div class="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800">
    <div v-if="loading" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.loadingVersionContent') }}
    </div>
    <div v-else-if="error" class="text-sm text-red-600 dark:text-red-400">
      {{ error }}
    </div>
    <div v-else-if="!versionId" class="text-sm text-gray-500 dark:text-gray-400">
      {{ t('history.noVersionSelected') }}
    </div>
    <pre
      v-else
      class="max-h-[65vh] overflow-auto whitespace-pre-wrap rounded-md border border-gray-200 bg-gray-50 p-3 text-xs leading-5 text-gray-900 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
    >{{ yaml }}</pre>
  </div>
</template>
