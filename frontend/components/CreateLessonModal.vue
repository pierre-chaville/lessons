<script setup>
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { 
  XMarkIcon,
  CloudArrowUpIcon,
  CheckIcon,
  DocumentIcon
} from '@heroicons/vue/24/outline';
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue';

const props = defineProps({
  isOpen: {
    type: Boolean,
    required: true
  }
});

const emit = defineEmits(['close', 'created']);

const { t } = useI18n();

const API_URL = 'http://localhost:8000';

// Form state
const selectedFile = ref(null);
const title = ref('');
const date = ref('');
const courseId = ref(null);
const themeIds = ref([]);
const isUploading = ref(false);

const courses = ref([]);
const themes = ref([]);

// File selection
const fileInput = ref(null);

const onFileSelected = (event) => {
  const file = event.target.files[0];
  if (!file) return;
  
  selectedFile.value = file;
  
  // Parse filename to extract title and date
  parseFilename(file.name);
};

const parseFilename = (filename) => {
  // Remove extension
  const nameWithoutExt = filename.replace(/\.[^/.]+$/, '');
  
  // Try to extract date pattern (assuming format: name_YYYYMMDD or name_DDMMYYYY)
  // Example patterns:
  // - lesson_20250824.mp3 -> title: "lesson", date: "2025-08-24"
  // - eloul_d_20250824.mp3 -> title: "eloul d", date: "2025-08-24"
  
  const datePattern = /[_\-](\d{8})$/;
  const match = nameWithoutExt.match(datePattern);
  
  if (match) {
    const dateStr = match[1];
    // Assume YYYYMMDD format
    if (dateStr.length === 8) {
      const year = dateStr.substring(0, 4);
      const month = dateStr.substring(4, 6);
      const day = dateStr.substring(6, 8);
      date.value = `${year}-${month}-${day}`;
      
      // Title is everything before the date
      title.value = nameWithoutExt.substring(0, match.index).replace(/[_-]/g, ' ').trim();
    }
  } else {
    // No date found, use entire filename as title
    title.value = nameWithoutExt.replace(/[_-]/g, ' ').trim();
    // Set to today
    date.value = new Date().toISOString().slice(0, 10);
  }
};

const selectFile = () => {
  fileInput.value?.click();
};

const removeFile = () => {
  selectedFile.value = null;
  title.value = '';
  date.value = '';
  if (fileInput.value) {
    fileInput.value.value = '';
  }
};

const toggleTheme = (themeId) => {
  const index = themeIds.value.indexOf(themeId);
  if (index === -1) {
    themeIds.value.push(themeId);
  } else {
    themeIds.value.splice(index, 1);
  }
};

const fetchCourses = async () => {
  try {
    const response = await axios.get(`${API_URL}/courses`);
    courses.value = response.data;
  } catch (error) {
    console.error('Failed to fetch courses:', error);
  }
};

const fetchThemes = async () => {
  try {
    const response = await axios.get(`${API_URL}/themes`);
    themes.value = response.data;
  } catch (error) {
    console.error('Failed to fetch themes:', error);
  }
};

const createLesson = async () => {
  if (!selectedFile.value || !title.value) {
    alert(t('lessons.fillRequired'));
    return;
  }
  
  try {
    isUploading.value = true;
    
    // Upload file first
    const formData = new FormData();
    formData.append('file', selectedFile.value);
    
    const uploadResponse = await axios.post(`${API_URL}/upload/audio`, formData);
    const uploadedFilename = uploadResponse.data.filename;
    
    // Create lesson
    const lessonData = {
      title: title.value,
      filename: uploadedFilename,
      date: date.value ? new Date(date.value).toISOString() : new Date().toISOString(),
      course_id: courseId.value,
      theme_ids: themeIds.value.length > 0 ? themeIds.value : null
    };
    
    await axios.post(`${API_URL}/lessons`, lessonData);
    
    // Reset form and close
    resetForm();
    emit('created');
    emit('close');
  } catch (error) {
    console.error('Failed to create lesson:', error);
    alert(t('lessons.createFailed'));
  } finally {
    isUploading.value = false;
  }
};

const resetForm = () => {
  selectedFile.value = null;
  title.value = '';
  date.value = '';
  courseId.value = null;
  themeIds.value = [];
  if (fileInput.value) {
    fileInput.value.value = '';
  }
};

const close = () => {
  if (!isUploading.value) {
    resetForm();
    emit('close');
  }
};

// Fetch data when modal opens
const handleOpen = async () => {
  if (props.isOpen) {
    await Promise.all([fetchCourses(), fetchThemes()]);
  }
};

// Watch for modal open
import { watch } from 'vue';
watch(() => props.isOpen, handleOpen);
</script>

<template>
  <Dialog :open="isOpen" @close="close" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-2xl w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <!-- Header -->
        <div class="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <DialogTitle class="text-xl font-semibold text-gray-900 dark:text-white">
            {{ t('lessons.createLesson') }}
          </DialogTitle>
          <button
            @click="close"
            :disabled="isUploading"
            class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          >
            <XMarkIcon class="h-6 w-6" />
          </button>
        </div>
        
        <!-- Content -->
        <div class="p-6 space-y-6">
          <!-- File Upload -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.audioFile') }} *
            </label>
            
            <input
              ref="fileInput"
              type="file"
              accept="audio/*"
              @change="onFileSelected"
              class="hidden"
            />
            
            <div v-if="!selectedFile">
              <button
                @click="selectFile"
                class="w-full flex flex-col items-center justify-center px-6 py-8 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg hover:border-indigo-500 dark:hover:border-indigo-400 transition-colors"
              >
                <CloudArrowUpIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mb-2" />
                <span class="text-sm text-gray-600 dark:text-gray-400">
                  {{ t('lessons.clickToUpload') }}
                </span>
                <span class="text-xs text-gray-500 dark:text-gray-500 mt-1">
                  MP3, WAV, M4A, etc.
                </span>
              </button>
            </div>
            
            <div v-else class="flex items-center gap-3 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700">
              <DocumentIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400" />
              <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-gray-900 dark:text-white truncate">
                  {{ selectedFile.name }}
                </p>
                <p class="text-xs text-gray-500 dark:text-gray-400">
                  {{ (selectedFile.size / 1024 / 1024).toFixed(2) }} MB
                </p>
              </div>
              <button
                @click="removeFile"
                :disabled="isUploading"
                class="text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
              >
                <XMarkIcon class="h-5 w-5" />
              </button>
            </div>
          </div>
          
          <!-- Title -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.title') }} *
            </label>
            <input
              v-model="title"
              type="text"
              :disabled="isUploading"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
              :placeholder="t('lessons.titlePlaceholder')"
            />
          </div>
          
          <!-- Date -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.date') }}
            </label>
            <input
              v-model="date"
              type="date"
              :disabled="isUploading"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
            />
          </div>
          
          <!-- Course -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.course') }}
            </label>
            <select
              v-model="courseId"
              :disabled="isUploading"
              class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent disabled:opacity-50"
            >
              <option :value="null">{{ t('lessons.noCourse') }}</option>
              <option v-for="course in courses" :key="course.id" :value="course.id">
                {{ course.name }}
              </option>
            </select>
          </div>
          
          <!-- Themes -->
          <div>
            <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              {{ t('lessons.themes') }}
            </label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="theme in themes"
                :key="theme.id"
                @click="toggleTheme(theme.id)"
                :disabled="isUploading"
                :class="[
                  'px-3 py-1.5 rounded-full text-sm font-medium transition-colors disabled:opacity-50',
                  themeIds.includes(theme.id)
                    ? 'bg-indigo-600 text-white'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
                ]"
              >
                {{ theme.name }}
              </button>
            </div>
          </div>
        </div>
        
        <!-- Footer -->
        <div class="flex justify-end gap-3 px-6 py-4 bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700">
          <button
            @click="close"
            :disabled="isUploading"
            class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-md transition-colors disabled:opacity-50"
          >
            {{ t('lessons.cancel') }}
          </button>
          <button
            @click="createLesson"
            :disabled="isUploading || !selectedFile || !title"
            class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
          >
            <CheckIcon class="h-4 w-4" />
            {{ isUploading ? t('lessons.uploading') : t('lessons.create') }}
          </button>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>

