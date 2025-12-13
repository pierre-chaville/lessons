<script setup>
import { ref, onMounted, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { 
  MagnifyingGlassIcon,
  DocumentTextIcon, 
  ClockIcon, 
  FunnelIcon,
  XMarkIcon 
} from '@heroicons/vue/24/outline';
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue';
import { ChevronUpDownIcon, CheckIcon } from '@heroicons/vue/20/solid';

const { t } = useI18n();
const lessons = ref([]);
const courses = ref([]);
const themes = ref([]);
const loading = ref(false);
const searchQuery = ref('');
const selectedCourse = ref(null);
const selectedTheme = ref(null);

const API_URL = 'http://localhost:8000';

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

const searchLessons = async () => {
  try {
    loading.value = true;
    const params = {};
    
    // Add search query parameter (to be implemented in backend)
    if (searchQuery.value.trim()) {
      params.q = searchQuery.value.trim();
    }
    
    // Add course filter
    if (selectedCourse.value) {
      params.course_id = selectedCourse.value.id;
    }
    
    // TODO: Backend will implement search logic
    const response = await axios.get(`${API_URL}/lessons`, { params });
    lessons.value = response.data;
  } catch (error) {
    console.error('Failed to search lessons:', error);
  } finally {
    loading.value = false;
  }
};

// Filter lessons by theme on the frontend
const filteredLessons = computed(() => {
  if (!selectedTheme.value) {
    return lessons.value;
  }
  return lessons.value.filter(lesson => 
    lesson.themes && lesson.themes.some(theme => theme.id === selectedTheme.value.id)
  );
});

const clearFilters = () => {
  searchQuery.value = '';
  selectedCourse.value = null;
  selectedTheme.value = null;
  lessons.value = [];
};

const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const formatDuration = (seconds) => {
  if (!seconds) return '';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  } else if (minutes > 0) {
    return `${minutes}m ${secs}s`;
  } else {
    return `${secs}s`;
  }
};

const openLesson = (lesson) => {
  // TODO: Navigate to lesson detail
  console.log('Open lesson:', lesson.id);
};

onMounted(async () => {
  await Promise.all([fetchCourses(), fetchThemes()]);
});
</script>

<template>
  <div class="w-full">
    <!-- Search Bar -->
    <div class="mb-6 bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 transition-colors">
      <div class="flex gap-3">
        <div class="flex-1 relative">
          <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <MagnifyingGlassIcon class="h-5 w-5 text-gray-400 dark:text-gray-500" />
          </div>
          <input
            v-model="searchQuery"
            type="text"
            :placeholder="t('search.placeholder')"
            class="block w-full pl-10 pr-3 py-3 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
            @keyup.enter="searchLessons"
          />
        </div>
        <button
          @click="searchLessons"
          class="inline-flex items-center gap-2 px-6 py-3 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors"
        >
          <MagnifyingGlassIcon class="h-5 w-5" />
          {{ t('search.search') }}
        </button>
      </div>
    </div>

    <!-- Filters Section -->
    <div class="mb-6 bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 transition-colors">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex items-center gap-2">
          <FunnelIcon class="h-5 w-5 text-gray-500 dark:text-gray-400" />
          <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
            {{ t('search.filters') }}:
          </span>
        </div>

        <!-- Course Filter -->
        <Listbox v-model="selectedCourse">
          <div class="relative w-64">
            <ListboxButton class="relative w-full cursor-pointer rounded-md bg-white dark:bg-gray-700 py-2 pl-3 pr-10 text-left shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-600 sm:text-sm">
              <span class="block truncate text-gray-900 dark:text-gray-100">
                {{ selectedCourse ? selectedCourse.name : t('search.allCourses') }}
              </span>
              <span class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                <ChevronUpDownIcon class="h-5 w-5 text-gray-400" aria-hidden="true" />
              </span>
            </ListboxButton>
            <transition
              leave-active-class="transition ease-in duration-100"
              leave-from-class="opacity-100"
              leave-to-class="opacity-0"
            >
              <ListboxOptions class="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white dark:bg-gray-700 py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none sm:text-sm">
                <ListboxOption
                  v-slot="{ active, selected }"
                  :value="null"
                  as="template"
                >
                  <li :class="[
                    active ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100',
                    'relative cursor-pointer select-none py-2 pl-3 pr-9'
                  ]">
                    <span :class="[selected ? 'font-semibold' : 'font-normal', 'block truncate']">
                      {{ t('search.allCourses') }}
                    </span>
                    <span v-if="selected" :class="[
                      active ? 'text-white' : 'text-indigo-600',
                      'absolute inset-y-0 right-0 flex items-center pr-4'
                    ]">
                      <CheckIcon class="h-5 w-5" aria-hidden="true" />
                    </span>
                  </li>
                </ListboxOption>
                <ListboxOption
                  v-for="course in courses"
                  :key="course.id"
                  v-slot="{ active, selected }"
                  :value="course"
                  as="template"
                >
                  <li :class="[
                    active ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100',
                    'relative cursor-pointer select-none py-2 pl-3 pr-9'
                  ]">
                    <span :class="[selected ? 'font-semibold' : 'font-normal', 'block truncate']">
                      {{ course.name }}
                    </span>
                    <span v-if="selected" :class="[
                      active ? 'text-white' : 'text-indigo-600',
                      'absolute inset-y-0 right-0 flex items-center pr-4'
                    ]">
                      <CheckIcon class="h-5 w-5" aria-hidden="true" />
                    </span>
                  </li>
                </ListboxOption>
              </ListboxOptions>
            </transition>
          </div>
        </Listbox>

        <!-- Theme Filter -->
        <Listbox v-model="selectedTheme">
          <div class="relative w-64">
            <ListboxButton class="relative w-full cursor-pointer rounded-md bg-white dark:bg-gray-700 py-2 pl-3 pr-10 text-left shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-600 sm:text-sm">
              <span class="block truncate text-gray-900 dark:text-gray-100">
                {{ selectedTheme ? selectedTheme.name : t('search.allThemes') }}
              </span>
              <span class="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                <ChevronUpDownIcon class="h-5 w-5 text-gray-400" aria-hidden="true" />
              </span>
            </ListboxButton>
            <transition
              leave-active-class="transition ease-in duration-100"
              leave-from-class="opacity-100"
              leave-to-class="opacity-0"
            >
              <ListboxOptions class="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white dark:bg-gray-700 py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none sm:text-sm">
                <ListboxOption
                  v-slot="{ active, selected }"
                  :value="null"
                  as="template"
                >
                  <li :class="[
                    active ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100',
                    'relative cursor-pointer select-none py-2 pl-3 pr-9'
                  ]">
                    <span :class="[selected ? 'font-semibold' : 'font-normal', 'block truncate']">
                      {{ t('search.allThemes') }}
                    </span>
                    <span v-if="selected" :class="[
                      active ? 'text-white' : 'text-indigo-600',
                      'absolute inset-y-0 right-0 flex items-center pr-4'
                    ]">
                      <CheckIcon class="h-5 w-5" aria-hidden="true" />
                    </span>
                  </li>
                </ListboxOption>
                <ListboxOption
                  v-for="theme in themes"
                  :key="theme.id"
                  v-slot="{ active, selected }"
                  :value="theme"
                  as="template"
                >
                  <li :class="[
                    active ? 'bg-indigo-600 text-white' : 'text-gray-900 dark:text-gray-100',
                    'relative cursor-pointer select-none py-2 pl-3 pr-9'
                  ]">
                    <span :class="[selected ? 'font-semibold' : 'font-normal', 'block truncate']">
                      {{ theme.name }}
                    </span>
                    <span v-if="selected" :class="[
                      active ? 'text-white' : 'text-indigo-600',
                      'absolute inset-y-0 right-0 flex items-center pr-4'
                    ]">
                      <CheckIcon class="h-5 w-5" aria-hidden="true" />
                    </span>
                  </li>
                </ListboxOption>
              </ListboxOptions>
            </transition>
          </div>
        </Listbox>

        <!-- Clear Filters Button -->
        <button
          v-if="searchQuery || selectedCourse || selectedTheme"
          @click="clearFilters"
          class="inline-flex items-center gap-1 px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
        >
          <XMarkIcon class="h-4 w-4" />
          {{ t('search.clearAll') }}
        </button>
      </div>
    </div>

    <!-- Results -->
    <div v-if="loading" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('search.searching') }}
    </div>
    
    <div v-else-if="lessons.length === 0 && !searchQuery && !selectedCourse && !selectedTheme" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
      <MagnifyingGlassIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
      <p class="text-gray-500 dark:text-gray-400">
        {{ t('search.enterQuery') }}
      </p>
    </div>

    <div v-else-if="filteredLessons.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('search.noResults') }}
    </div>

    <div v-else class="w-full grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="lesson in filteredLessons"
        :key="lesson.id"
        @click="openLesson(lesson)"
        class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 hover:shadow-md dark:hover:shadow-gray-900/50 transition-all cursor-pointer border border-gray-200 dark:border-gray-700"
      >
        <div class="flex flex-col h-full">
          <div class="flex items-start gap-2 mb-3">
            <DocumentTextIcon class="h-6 w-6 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-1" />
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white line-clamp-2">
              {{ lesson.title }}
            </h3>
          </div>
          
          <div class="flex-1">
            <div class="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-3">
              <ClockIcon class="h-4 w-4" />
              <span>{{ formatDate(lesson.date) }}</span>
              <span v-if="lesson.duration" class="text-gray-400 dark:text-gray-500">•</span>
              <span v-if="lesson.duration">{{ formatDuration(lesson.duration) }}</span>
            </div>
            
            <p v-if="lesson.brief" class="text-xs text-gray-600 dark:text-gray-400 mb-3 line-clamp-2">
              {{ lesson.brief }}
            </p>
            
            <div v-if="lesson.course || (lesson.themes && lesson.themes.length > 0)" class="flex items-start gap-2">
              <!-- Course on the left -->
              <div v-if="lesson.course" class="flex-shrink-0">
                <span class="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                  {{ lesson.course.name }}
                </span>
              </div>
              
              <!-- Themes on the right -->
              <div v-if="lesson.themes && lesson.themes.length > 0" class="flex flex-wrap gap-2 ml-auto">
                <span
                  v-for="theme in lesson.themes"
                  :key="theme.id"
                  class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-300"
                >
                  {{ theme.name }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

