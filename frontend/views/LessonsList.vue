<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { 
  DocumentTextIcon, 
  ClockIcon, 
  FunnelIcon,
  XMarkIcon 
} from '@heroicons/vue/24/outline';
import { Listbox, ListboxButton, ListboxOptions, ListboxOption } from '@headlessui/vue';
import { ChevronUpDownIcon, CheckIcon } from '@heroicons/vue/20/solid';
import LessonDetail from './LessonDetail.vue';
import CreateLessonModal from '../components/CreateLessonModal.vue';

const { t } = useI18n();
const lessons = ref([]);
const courses = ref([]);
const themes = ref([]);
const loading = ref(true);
const selectedLesson = ref(null);
const selectedLessonDetail = ref(null);

const selectedCourse = ref(null);
const selectedTheme = ref(null);
const showCreateModal = ref(false);

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

const fetchLessons = async () => {
  try {
    loading.value = true;
    const params = {};
    if (selectedCourse.value) {
      params.course_id = selectedCourse.value.id;
    }
    const response = await axios.get(`${API_URL}/lessons`, { params });
    lessons.value = response.data;
  } catch (error) {
    console.error('Failed to fetch lessons:', error);
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
    lesson.themes.some(theme => theme.id === selectedTheme.value.id)
  );
});

// Watch for filter changes
watch([selectedCourse], () => {
  fetchLessons();
});

const clearFilters = () => {
  selectedCourse.value = null;
  selectedTheme.value = null;
};

onMounted(async () => {
  await Promise.all([fetchCourses(), fetchThemes(), fetchLessons()]);
});

const formatDate = (dateString) => {
  if (!dateString) return '';
  const date = new Date(dateString);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const openLesson = async (lesson) => {
  try {
    // Fetch full lesson details
    const response = await axios.get(`${API_URL}/lessons/${lesson.id}`);
    selectedLessonDetail.value = response.data;
    selectedLesson.value = lesson;
  } catch (error) {
    console.error('Failed to fetch lesson details:', error);
  }
};

const closeLesson = () => {
  selectedLesson.value = null;
  selectedLessonDetail.value = null;
};

const openCreateModal = () => {
  showCreateModal.value = true;
};

const closeCreateModal = () => {
  showCreateModal.value = false;
};

const onLessonCreated = () => {
  fetchLessons(); // Refresh the list
};

// Expose whether we're viewing a lesson detail
defineExpose({
  isViewingDetail: computed(() => selectedLessonDetail.value !== null),
  openCreateModal
});
</script>

<template>
  <!-- Create Lesson Modal -->
  <CreateLessonModal
    :is-open="showCreateModal"
    @close="closeCreateModal"
    @created="onLessonCreated"
  />
  
  <!-- Show lesson detail if a lesson is selected -->
  <LessonDetail
    v-if="selectedLessonDetail"
    :lesson="selectedLessonDetail"
    @close="closeLesson"
  />
  
  <!-- Show lessons list if no lesson is selected -->
  <div v-else>
    <!-- Filters Section -->
    <div class="mb-6 bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 transition-colors">
      <div class="flex items-center gap-4 flex-wrap">
        <div class="flex items-center gap-2">
          <FunnelIcon class="h-5 w-5 text-gray-500 dark:text-gray-400" />
          <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
            {{ t('lessons.filters') }}:
          </span>
        </div>

        <!-- Course Filter -->
        <Listbox v-model="selectedCourse">
          <div class="relative w-64">
            <ListboxButton class="relative w-full cursor-pointer rounded-md bg-white dark:bg-gray-700 py-2 pl-3 pr-10 text-left shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 focus:outline-none focus:ring-2 focus:ring-indigo-600 sm:text-sm">
              <span class="block truncate text-gray-900 dark:text-gray-100">
                {{ selectedCourse ? selectedCourse.name : t('lessons.allCourses') }}
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
                      {{ t('lessons.allCourses') }}
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
                {{ selectedTheme ? selectedTheme.name : t('lessons.allThemes') }}
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
                      {{ t('lessons.allThemes') }}
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
          v-if="selectedCourse || selectedTheme"
          @click="clearFilters"
          class="inline-flex items-center gap-1 px-3 py-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 transition-colors"
        >
          <XMarkIcon class="h-4 w-4" />
          {{ t('lessons.clearFilters') }}
        </button>
      </div>
    </div>

    <!-- Lessons Grid -->
    <div v-if="loading" class="p-8 text-center text-gray-500 dark:text-gray-400">
      {{ t('lessons.loading') }}
    </div>
    
    <div v-else-if="filteredLessons.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('lessons.noLessons') }}
    </div>

    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
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
            </div>
            
            <div v-if="lesson.themes && lesson.themes.length > 0" class="flex flex-wrap gap-2 mb-3">
              <span
                v-for="theme in lesson.themes"
                :key="theme.id"
                class="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-indigo-100 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-300"
              >
                {{ theme.name }}
              </span>
            </div>
          </div>
          
          <div class="text-xs text-gray-500 dark:text-gray-400 pt-3 border-t border-gray-200 dark:border-gray-700">
            <span class="font-mono">{{ lesson.filename }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

