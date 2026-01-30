<script setup>
import { ref, onMounted, nextTick } from 'vue';
import { useI18n } from 'vue-i18n';
import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/vue';
import {
  CogIcon,
  CheckIcon,
  ArrowPathIcon,
  MicrophoneIcon,
  PencilIcon,
  DocumentTextIcon,
  BookOpenIcon,
  TrashIcon
} from '@heroicons/vue/24/outline';
import axios from 'axios';

const { t } = useI18n();

const API_URL = 'http://localhost:8000';

// Configuration state
const config = ref({
  correction: {
    provider: 'OpenAI',
    model: '',
    prompt: '',
    temperature: 0.3,
    max_tokens: 16000
  },
  edition: {
    provider: 'OpenAI',
    model: '',
    prompt: '',
    temperature: 0.5,
    max_tokens: 16000
  },
  extraction: {
    provider: 'OpenAI',
    model: '',
    prompt: '',
    temperature: 0.3,
    max_tokens: 4000
  },
  sources: {
    provider: 'OpenAI',
    model: '',
    prompt: '',
    temperature: 0.3,
    max_tokens: 4000
  },
  source_types: {},
  summary: {
    max_length: 300,
    provider: 'OpenAI',
    model: '',
    prompts: [
      { name: 'Default', text: '' }
    ],
    temperature: 0.7,
    max_tokens: 4000,
    brief: {
      provider: 'OpenAI',
      model: '',
      prompt: '',
      temperature: 0.5,
      max_tokens: 1000
    }
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
    // Ensure source_types exists
    if (!config.value.source_types) {
      config.value.source_types = {};
    }
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

const addSummaryPrompt = () => {
  config.value.summary.prompts.push({ name: '', text: '' });
};

const removeSummaryPrompt = (index) => {
  if (config.value.summary.prompts.length > 1) {
    config.value.summary.prompts.splice(index, 1);
  }
};

const addSourceType = async () => {
  // Ensure source_types exists
  if (!config.value.source_types) {
    config.value.source_types = {};
  }
  
  // Generate a unique name for the new type
  let newTypeName = 'New Type';
  let counter = 1;
  const currentTypes = { ...(config.value.source_types || {}) };
  while (currentTypes[newTypeName] !== undefined) {
    newTypeName = `New Type ${counter}`;
    counter++;
  }
  
  // Create new object with the added type
  const newTypes = {
    ...currentTypes,
    [newTypeName]: ''
  };
  
  // Update the entire config object to ensure reactivity
  // Use Object.assign to maintain reactivity
  config.value.source_types = newTypes;
  
  // Force Vue to detect the change
  await nextTick();
};

const removeSourceType = (type) => {
  if (config.value.source_types && config.value.source_types[type] !== undefined) {
    delete config.value.source_types[type];
    // Create a new object to trigger reactivity
    config.value.source_types = { ...config.value.source_types };
  }
};

const updateSourceType = (oldType, newType, description) => {
  if (!config.value.source_types) {
    config.value.source_types = {};
  }
  
  // If the type name changed, remove the old one and add the new one
  if (oldType !== newType) {
    delete config.value.source_types[oldType];
  }
  
  config.value.source_types[newType] = description;
  // Create a new object to trigger reactivity
  config.value.source_types = { ...config.value.source_types };
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
                {{ t('preferences.edition') }}
              </div>
            </Tab>
            <Tab v-slot="{ selected }" class="w-full rounded-md py-2.5 text-sm font-medium leading-5 transition-colors focus:outline-none">
              <div :class="[
                'flex items-center justify-center gap-2',
                selected
                  ? 'bg-white dark:bg-gray-800 text-indigo-700 dark:text-indigo-400 shadow'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-white/[0.12] dark:hover:bg-gray-600'
              ]">
                <BookOpenIcon class="h-5 w-5" />
                {{ t('preferences.sources') }}
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
                <!-- Provider -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.provider') }}
                  </label>
                  <select
                    v-model="config.correction.provider"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="OpenAI">OpenAI</option>
                    <option value="Anthropic">Anthropic</option>
                  </select>
                </div>

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

                <!-- Max Tokens -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.maxTokens') }}
                  </label>
                  <input
                    v-model.number="config.correction.max_tokens"
                    type="number"
                    min="256"
                    max="200000"
                    step="256"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.maxTokensDesc') }}
                  </p>
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

            <!-- Edition Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.editionSettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Provider -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.provider') }}
                  </label>
                  <select
                    v-model="config.edition.provider"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="OpenAI">OpenAI</option>
                    <option value="Anthropic">Anthropic</option>
                  </select>
                </div>

                <!-- Model -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.model') }}
                  </label>
                  <input
                    v-model="config.edition.model"
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
                    {{ t('preferences.temperature') }}: {{ config.edition.temperature }}
                  </label>
                  <input
                    v-model.number="config.edition.temperature"
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

                <!-- Max Tokens -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.maxTokens') }}
                  </label>
                  <input
                    v-model.number="config.edition.max_tokens"
                    type="number"
                    min="256"
                    max="200000"
                    step="256"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.maxTokensDesc') }}
                  </p>
                </div>

                <!-- Prompt -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.prompt') }}
                  </label>
                  <textarea
                    v-model="config.edition.prompt"
                    rows="10"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                  ></textarea>
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.editionPromptDesc') }}
                  </p>
                </div>
              </div>
            </TabPanel>

            <!-- Sources Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-6">
                {{ t('preferences.sourcesSettings') }}
              </h2>
              
              <div class="space-y-8">
                <!-- Source Types Reference -->
                <div class="border-b border-gray-200 dark:border-gray-700 pb-6">
                  <h3 class="text-md font-semibold text-gray-900 dark:text-white mb-4">
                    {{ t('preferences.sourceTypes') }}
                  </h3>
                  
                  <div class="bg-gray-50 dark:bg-gray-900/50 rounded-lg p-4">
                    <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
                      {{ t('preferences.sourceTypesDesc') }}
                    </p>
                    <div v-if="config.source_types && Object.keys(config.source_types || {}).length > 0" class="space-y-2">
                      <div
                        v-for="(description, type, index) in config.source_types"
                        :key="type"
                        class="flex items-center gap-2 p-2 bg-white dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700"
                      >
                        <input
                          :value="type"
                          @input="(e) => updateSourceType(type, e.target.value, description)"
                          type="text"
                          class="w-32 px-2 py-1 text-sm font-semibold text-gray-900 dark:text-white bg-transparent border-b border-gray-300 dark:border-gray-600 focus:border-indigo-500 dark:focus:border-indigo-400 focus:outline-none"
                          :placeholder="t('preferences.sourceTypeName')"
                        />
                        <input
                          :value="description"
                          @input="(e) => updateSourceType(type, type, e.target.value)"
                          type="text"
                          class="flex-1 px-2 py-1 text-sm text-gray-700 dark:text-gray-300 bg-transparent border-b border-gray-300 dark:border-gray-600 focus:border-indigo-500 dark:focus:border-indigo-400 focus:outline-none"
                          :placeholder="t('preferences.sourceTypeDescription')"
                        />
                        <button
                          @click="removeSourceType(type)"
                          type="button"
                          class="px-2 py-1.5 text-sm font-medium text-white bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 rounded-md transition-colors shadow-sm flex items-center justify-center flex-shrink-0"
                          :title="t('preferences.remove')"
                        >
                          <TrashIcon class="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    <div v-else class="text-sm text-gray-500 dark:text-gray-400 italic text-center py-4">
                      {{ t('preferences.noSourceTypes') }}
                    </div>
                    
                    <!-- Add Type button at the end -->
                    <div class="mt-4 flex justify-end">
                      <button
                        @click="addSourceType"
                        type="button"
                        class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 rounded-md transition-colors shadow-sm flex items-center gap-2"
                      >
                        <span>+</span>
                        {{ t('preferences.addSourceType') }}
                      </button>
                    </div>
                  </div>
                </div>

                <!-- Source Extraction Section -->
                <div class="border-b border-gray-200 dark:border-gray-700 pb-6">
                  <h3 class="text-md font-semibold text-gray-900 dark:text-white mb-4">
                    {{ t('preferences.sourceExtraction') }}
                  </h3>
                  
                  <div class="space-y-6">
                    <!-- Provider -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.provider') }}
                      </label>
                      <select
                        v-model="config.extraction.provider"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="OpenAI">OpenAI</option>
                        <option value="Anthropic">Anthropic</option>
                      </select>
                    </div>

                    <!-- Model -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.model') }}
                      </label>
                      <input
                        v-model="config.extraction.model"
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
                        {{ t('preferences.temperature') }}: {{ config.extraction.temperature }}
                      </label>
                      <input
                        v-model.number="config.extraction.temperature"
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

                    <!-- Max Tokens -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.maxTokens') }}
                      </label>
                      <input
                        v-model.number="config.extraction.max_tokens"
                        type="number"
                        min="256"
                        max="200000"
                        step="256"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                      />
                      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.maxTokensDesc') }}
                      </p>
                    </div>

                    <!-- Prompt -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.prompt') }}
                      </label>
                      <textarea
                        v-model="config.extraction.prompt"
                        rows="10"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                      ></textarea>
                      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.extractionPromptDesc') }}
                      </p>
                    </div>
                  </div>
                </div>

                <!-- Source Verification Section -->
                <div>
                  <h3 class="text-md font-semibold text-gray-900 dark:text-white mb-4">
                    {{ t('preferences.sourceVerification') }}
                  </h3>
                  
                  <div class="space-y-6">
                    <!-- Provider -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.provider') }}
                      </label>
                      <select
                        v-model="config.sources.provider"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="OpenAI">OpenAI</option>
                        <option value="Anthropic">Anthropic</option>
                      </select>
                    </div>

                    <!-- Model -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.model') }}
                      </label>
                      <input
                        v-model="config.sources.model"
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
                        {{ t('preferences.temperature') }}: {{ config.sources.temperature }}
                      </label>
                      <input
                        v-model.number="config.sources.temperature"
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

                    <!-- Max Tokens -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.maxTokens') }}
                      </label>
                      <input
                        v-model.number="config.sources.max_tokens"
                        type="number"
                        min="256"
                        max="200000"
                        step="256"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                      />
                      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.maxTokensDesc') }}
                      </p>
                    </div>

                    <!-- Prompt -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.prompt') }}
                      </label>
                      <textarea
                        v-model="config.sources.prompt"
                        rows="10"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                      ></textarea>
                      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.sourcesPromptDesc') }}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </TabPanel>

            <!-- Summary Tab -->
            <TabPanel class="rounded-lg bg-white dark:bg-gray-800 p-6 shadow">
              <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
                {{ t('preferences.summarySettings') }}
              </h2>
              
              <div class="space-y-6">
                <!-- Provider -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.provider') }}
                  </label>
                  <select
                    v-model="config.summary.provider"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  >
                    <option value="OpenAI">OpenAI</option>
                    <option value="Anthropic">Anthropic</option>
                  </select>
                </div>

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

                <!-- Max Tokens -->
                <div>
                  <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    {{ t('preferences.maxTokens') }}
                  </label>
                  <input
                    v-model.number="config.summary.max_tokens"
                    type="number"
                    min="256"
                    max="200000"
                    step="256"
                    class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                  />
                  <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.maxTokensDesc') }}
                  </p>
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

                <!-- Prompts -->
                <div>
                  <div class="flex items-center justify-between mb-2">
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300">
                      {{ t('preferences.summaryPrompts') }}
                    </label>
                    <button
                      @click="addSummaryPrompt"
                      type="button"
                      class="px-3 py-1 text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:text-indigo-700 dark:hover:text-indigo-300 border border-indigo-300 dark:border-indigo-600 rounded-md hover:bg-indigo-50 dark:hover:bg-indigo-900/20 transition-colors"
                    >
                      + {{ t('preferences.addPrompt') }}
                    </button>
                  </div>
                  
                  <div class="space-y-4">
                    <div
                      v-for="(prompt, index) in config.summary.prompts"
                      :key="index"
                      class="border border-gray-300 dark:border-gray-600 rounded-md p-4 bg-gray-50 dark:bg-gray-900/30"
                    >
                      <div class="flex items-center gap-3 mb-3">
                        <input
                          v-model="prompt.name"
                          type="text"
                          :placeholder="t('preferences.promptName')"
                          class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 text-sm font-medium"
                        />
                        <button
                          v-if="config.summary.prompts.length > 1"
                          @click="removeSummaryPrompt(index)"
                          type="button"
                          class="px-3 py-2 text-xs font-medium text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md transition-colors"
                        >
                          {{ t('preferences.remove') }}
                        </button>
                      </div>
                      <textarea
                        v-model="prompt.text"
                        rows="8"
                        :placeholder="t('preferences.promptText')"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                      ></textarea>
                    </div>
                  </div>
                  
                  <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
                    {{ t('preferences.summaryPromptDesc') }}
                  </p>
                </div>

                <!-- Brief Summary Settings -->
                <div class="border-t border-gray-200 dark:border-gray-700 pt-6">
                  <h3 class="text-md font-semibold text-gray-900 dark:text-white mb-4">
                    {{ t('preferences.briefSettings') }}
                  </h3>

                  <div class="space-y-6">
                    <!-- Provider -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.provider') }}
                      </label>
                      <select
                        v-model="config.summary.brief.provider"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                      >
                        <option value="OpenAI">OpenAI</option>
                        <option value="Anthropic">Anthropic</option>
                      </select>
                    </div>

                    <!-- Model -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.model') }}
                      </label>
                      <input
                        v-model="config.summary.brief.model"
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
                        {{ t('preferences.temperature') }}: {{ config.summary.brief.temperature }}
                      </label>
                      <input
                        v-model.number="config.summary.brief.temperature"
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

                    <!-- Max Tokens -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.maxTokens') }}
                      </label>
                      <input
                        v-model.number="config.summary.brief.max_tokens"
                        type="number"
                        min="256"
                        max="200000"
                        step="256"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500"
                      />
                      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.maxTokensDesc') }}
                      </p>
                    </div>

                    <!-- Prompt -->
                    <div>
                      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        {{ t('preferences.prompt') }}
                      </label>
                      <textarea
                        v-model="config.summary.brief.prompt"
                        rows="6"
                        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 font-mono text-sm"
                      ></textarea>
                      <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
                        {{ t('preferences.briefPromptDesc') }}
                      </p>
                    </div>
                  </div>
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


