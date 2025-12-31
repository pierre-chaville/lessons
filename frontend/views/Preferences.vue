<script setup>
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/vue';
import {
  CogIcon,
  CheckIcon,
  ArrowPathIcon,
  KeyIcon,
  MicrophoneIcon,
  PencilIcon,
  DocumentTextIcon
} from '@heroicons/vue/24/outline';
import axios from 'axios';

const { t } = useI18n();

const API_URL = 'http://localhost:8000';

// Configuration state
const config = ref({
  api_key: '',
  provider: 'OpenAI',
  correction: {
    model: '',
    prompt: '',
    temperature: 0.3
  },
  summary: {
    max_length: 300,
    model: '',
    prompt: '',
    temperature: 0.7
  },
  transcribe: {
    beam_size: 5,
    initial_prompt: '',
    language: 'fr',
    vad_filter: true
  },
  whisper: {
    compute_type: 'int8',
    device: 'cuda',
    model_size: 'large-v3'
  }
});

const isLoading = ref(true);
const isSaving = ref(false);
const isResetting = ref(false);
const saveMessage = ref('');
const saveError = ref('');

// Load configuration on mount
onMounted(async () => {
  await loadConfig();
});

const loadConfig = async () => {
  try {
    isLoading.value = true;
    const response = await axios.get(`${API_URL}/config`);
    config.value = response.data;
  } catch (error) {
    console.error('Failed to load configuration:', error);
    saveError.value = t('preferences.loadFailed');
  } finally {
    isLoading.value = false;
  }
};

const saveConfig = async () => {
  try {
    isSaving.value = true;
    saveMessage.value = '';
    saveError.value = '';
    
    await axios.put(`${API_URL}/config`, {
      config: config.value
    });
    
    saveMessage.value = t('preferences.saveSuccess');
    setTimeout(() => {
      saveMessage.value = '';
    }, 3000);
  } catch (error) {
    console.error('Failed to save configuration:', error);
    saveError.value = t('preferences.saveFailed');
  } finally {
    isSaving.value = false;
  }
};

const resetConfig = async () => {
  if (!confirm(t('preferences.resetConfirmMessage'))) {
    return;
  }
  
  try {
    isResetting.value = true;
    saveMessage.value = '';
    saveError.value = '';
    
    const response = await axios.post(`${API_URL}/config/reset`);
    config.value = response.data.config;
    
    saveMessage.value = t('preferences.resetSuccess');
    setTimeout(() => {
      saveMessage.value = '';
    }, 3000);
  } catch (error) {
    console.error('Failed to reset configuration:', error);
    saveError.value = t('preferences.resetFailed');
  } finally {
    isResetting.value = false;
  }
};
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50 dark:bg-gray-900">
    <!-- Header -->
    <div class="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <CogIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400" />
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
            {{ t('preferences.title') }}
          </h1>
        </div>
        
        <div class="flex items-center gap-3">
          <!-- Success/Error Messages -->
          <div v-if="saveMessage" class="text-sm text-green-600 dark:text-green-400 font-medium">
            {{ saveMessage }}
          </div>
          <div v-if="saveError" class="text-sm text-red-600 dark:text-red-400 font-medium">
            {{ saveError }}
          </div>
          
          <!-- Reset Button -->
          <button
            @click="resetConfig"
            :disabled="isSaving || isResetting || isLoading"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
          >
            <ArrowPathIcon class="h-4 w-4" />
            {{ isResetting ? t('preferences.resetting') : t('preferences.reset') }}
          </button>
          
          <!-- Save Button -->
          <button
            @click="saveConfig"
            :disabled="isSaving || isResetting || isLoading"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
          >
            <CheckIcon class="h-4 w-4" />
            {{ isSaving ? t('preferences.saving') : t('preferences.save') }}
          </button>
        </div>
      </div>
    </div>

    <!-- Content -->
    <div v-if="isLoading" class="flex-1 flex items-center justify-center">
      <div class="text-center">
        <CogIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 animate-spin mx-auto mb-4" />
        <p class="text-gray-600 dark:text-gray-400">{{ t('preferences.loading') }}</p>
      </div>
    </div>

    <div v-else class="flex-1 overflow-y-auto p-6">
      <div class="max-w-5xl mx-auto">
        <TabGroup>
          <TabList class="flex space-x-2 rounded-lg bg-gray-200 dark:bg-gray-700 p-1">
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <KeyIcon class="h-5 w-5" />
                {{ t('preferences.llmSettings') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <MicrophoneIcon class="h-5 w-5" />
                {{ t('preferences.transcription') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <PencilIcon class="h-5 w-5" />
                {{ t('preferences.correction') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <DocumentTextIcon class="h-5 w-5" />
                {{ t('preferences.summary') }}
              </div>
            </Tab>
          </TabList>

          <TabPanels class="mt-6">
            <!-- LLM Settings Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.llmSettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Provider -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.provider') }}
                  </label>
                  <select
                    v-model="config.provider"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="OpenAI">OpenAI</option>
                    <option value="Anthropic">Anthropic</option>
                  </select>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.providerDesc') }}
                  </p>
                </div>

                <!-- API Key -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.apiKey') }}
                  </label>
                  <input
                    v-model="config.api_key"
                    type="password"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                    :placeholder="t('preferences.apiKeyPlaceholder')"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.apiKeyDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Transcription Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.transcriptionSettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Whisper Model Size -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.whisperModelSize') }}
                  </label>
                  <select
                    v-model="config.whisper.model_size"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="tiny">Tiny</option>
                    <option value="base">Base</option>
                    <option value="small">Small</option>
                    <option value="medium">Medium</option>
                    <option value="large-v2">Large v2</option>
                    <option value="large-v3">Large v3</option>
                  </select>
                </div>

                <!-- Device -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.device') }}
                  </label>
                  <select
                    v-model="config.whisper.device"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="cpu">CPU</option>
                    <option value="cuda">CUDA (GPU)</option>
                  </select>
                </div>

                <!-- Compute Type -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.computeType') }}
                  </label>
                  <select
                    v-model="config.whisper.compute_type"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="int8">int8</option>
                    <option value="float16">float16</option>
                    <option value="float32">float32</option>
                  </select>
                </div>

                <!-- Language -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.language') }}
                  </label>
                  <input
                    v-model="config.transcribe.language"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.languageDesc') }}
                  </p>
                </div>

                <!-- Beam Size -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.beamSize') }}
                  </label>
                  <input
                    v-model.number="config.transcribe.beam_size"
                    type="number"
                    min="1"
                    max="10"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <!-- VAD Filter -->
                <div class="flex items-center gap-3">
                  <input
                    v-model="config.transcribe.vad_filter"
                    type="checkbox"
                    class="w-4 h-4 text-indigo-600 border-gray-300 rounded focus:ring-indigo-500"
                  />
                  <label class="text-sm font-medium text-gray-700 dark:text-gray-300">
                    {{ t('preferences.vadFilter') }}
                  </label>
                </div>

                <!-- Initial Prompt -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.initialPrompt') }}
                  </label>
                  <textarea
                    v-model="config.transcribe.initial_prompt"
                    rows="4"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    :placeholder="t('preferences.initialPromptPlaceholder')"
                  ></textarea>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.initialPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Correction Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.correctionSettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Model -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.model') }}
                  </label>
                  <input
                    v-model="config.correction.model"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    placeholder="gpt-4o"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.modelDesc') }}
                  </p>
                </div>

                <!-- Temperature -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.temperature') }}: {{ config.correction.temperature }}
                  </label>
                  <input
                    v-model.number="config.correction.temperature"
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    class="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
                  />
                  <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1">
                    <span>{{ t('preferences.precise') }}</span>
                    <span>{{ t('preferences.creative') }}</span>
                  </div>
                </div>

                <!-- Prompt -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.prompt') }}
                  </label>
                  <textarea
                    v-model="config.correction.prompt"
                    rows="10"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                  ></textarea>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.correctionPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Summary Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.summarySettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Model -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.model') }}
                  </label>
                  <input
                    v-model="config.summary.model"
                    type="text"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                    placeholder="gpt-4o"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.modelDesc') }}
                  </p>
                </div>

                <!-- Temperature -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.temperature') }}: {{ config.summary.temperature }}
                  </label>
                  <input
                    v-model.number="config.summary.temperature"
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    class="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-lg appearance-none cursor-pointer"
                  />
                  <div class="flex justify-between text-xs text-gray-500 dark:text-gray-400 mt-1">
                    <span>{{ t('preferences.precise') }}</span>
                    <span>{{ t('preferences.creative') }}</span>
                  </div>
                </div>

                <!-- Max Length -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.maxLength') }}
                  </label>
                  <input
                    v-model.number="config.summary.max_length"
                    type="number"
                    min="50"
                    max="2000"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.maxLengthDesc') }}
                  </p>
                </div>

                <!-- Prompt -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.prompt') }}
                  </label>
                  <textarea
                    v-model="config.summary.prompt"
                    rows="10"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                  ></textarea>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.summaryPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>
          </TabPanels>
        </TabGroup>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Custom styles for range slider */
input[type="range"]::-webkit-slider-thumb {
  appearance: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #4f46e5;
  cursor: pointer;
}

input[type="range"]::-moz-range-thumb {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #4f46e5;
  cursor: pointer;
  border: none;
}
</style>


