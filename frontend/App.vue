<script setup>
import { ref, computed, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { Menu, MenuButton, MenuItems, MenuItem } from '@headlessui/vue';
import { 
  ChevronDownIcon, 
  LanguageIcon,
  PlusIcon,
  MicrophoneIcon,
  SunIcon,
  MoonIcon
} from '@heroicons/vue/24/outline';
import NavigationSidebar from './components/NavigationSidebar.vue';
import LessonsList from './views/LessonsList.vue';
import CoursesList from './views/CoursesList.vue';

const { locale, t } = useI18n();

// Current route/view
const currentRoute = ref('/lessons');

// Reference to components
const lessonsListRef = ref(null);
const coursesListRef = ref(null);

// Check if we're viewing a lesson detail
const isViewingDetail = computed(() => {
  return lessonsListRef.value?.isViewingDetail || false;
});

// Handle navigation
const handleNavigation = (route) => {
  currentRoute.value = route;
};

// Get current page title
const pageTitle = computed(() => {
  switch (currentRoute.value) {
    case '/lessons':
      return t('lessons.title');
    case '/courses':
      return t('courses.title');
    case '/themes':
      return t('nav.themes');
    case '/processing':
      return t('nav.processing');
    case '/preferences':
      return t('nav.preferences');
    default:
      return t('lessons.title');
  }
});

// Dark mode state
const isDarkMode = ref(false);

const changeLanguage = (lang) => {
  locale.value = lang;
};

// Function to apply dark mode to document
const applyDarkMode = (dark) => {
  if (dark) {
    document.documentElement.classList.add('dark');
    localStorage.setItem('darkMode', 'true');
  } else {
    document.documentElement.classList.remove('dark');
    localStorage.setItem('darkMode', 'false');
  }
};

const toggleDarkMode = () => {
  isDarkMode.value = !isDarkMode.value;
  applyDarkMode(isDarkMode.value);
  console.log('Dark mode toggled to:', isDarkMode.value);
};

// Initialize dark mode on mount
onMounted(() => {
  // Check localStorage first, then system preference
  const savedDarkMode = localStorage.getItem('darkMode');
  if (savedDarkMode !== null) {
    isDarkMode.value = savedDarkMode === 'true';
  } else {
    // Check system preference if no saved preference
    isDarkMode.value = window.matchMedia('(prefers-color-scheme: dark)').matches;
  }
  
  // Apply the initial state
  applyDarkMode(isDarkMode.value);
  console.log('Initial dark mode:', isDarkMode.value);
});
</script>

<template>
  <div class="flex min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors">
    <!-- Navigation Sidebar -->
    <NavigationSidebar 
      :active-route="currentRoute"
      @navigate="handleNavigation"
    />
    
    <!-- Main Content Wrapper -->
    <div class="flex-1 flex flex-col">
      <!-- Header -->
      <header class="bg-white dark:bg-gray-800 shadow-sm transition-colors">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <MicrophoneIcon class="h-8 w-8 text-indigo-600 dark:text-indigo-400" />
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">
              {{ t('app.title') }}
            </h1>
          </div>
          
          <div class="flex items-center gap-3">
            <!-- Dark Mode Toggle -->
            <button
              @click="toggleDarkMode"
              class="inline-flex items-center justify-center rounded-md p-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              :title="isDarkMode ? t('theme.light') : t('theme.dark')"
            >
              <SunIcon v-if="isDarkMode" class="h-5 w-5" />
              <MoonIcon v-else class="h-5 w-5" />
            </button>
            
            <!-- Language Selector -->
            <Menu as="div" class="relative inline-block text-left">
              <MenuButton class="inline-flex items-center justify-center gap-x-1.5 rounded-md bg-white dark:bg-gray-700 px-3 py-2 text-sm font-semibold text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors">
                <LanguageIcon class="h-5 w-5" />
                {{ locale.toUpperCase() }}
                <ChevronDownIcon class="-mr-1 h-5 w-5 text-gray-400 dark:text-gray-500" aria-hidden="true" />
              </MenuButton>

              <transition
                enter-active-class="transition ease-out duration-100"
                enter-from-class="transform opacity-0 scale-95"
                enter-to-class="transform opacity-100 scale-100"
                leave-active-class="transition ease-in duration-75"
                leave-from-class="transform opacity-100 scale-100"
                leave-to-class="transform opacity-0 scale-95"
              >
                <MenuItems class="absolute right-0 z-10 mt-2 w-32 origin-top-right rounded-md bg-white dark:bg-gray-800 shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none">
                  <div class="py-1">
                    <MenuItem v-slot="{ active }">
                      <button
                        @click="changeLanguage('en')"
                        :class="[
                          active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300',
                          'block w-full px-4 py-2 text-left text-sm'
                        ]"
                      >
                        English
                      </button>
                    </MenuItem>
                    <MenuItem v-slot="{ active }">
                      <button
                        @click="changeLanguage('fr')"
                        :class="[
                          active ? 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-gray-100' : 'text-gray-700 dark:text-gray-300',
                          'block w-full px-4 py-2 text-left text-sm'
                        ]"
                      >
                        Français
                      </button>
                    </MenuItem>
                  </div>
                </MenuItems>
              </transition>
            </Menu>
          </div>
        </div>
        </div>
      </header>

      <!-- Main Content -->
      <main v-if="!isViewingDetail && currentRoute !== '/lessons'" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <!-- Courses View -->
        <template v-if="currentRoute === '/courses'">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('courses.title') }}
            </h2>
            <button
              @click="coursesListRef?.openCreateModal()"
              class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
            >
              <PlusIcon class="h-5 w-5" />
              {{ t('courses.addNew') }}
            </button>
          </div>
          <CoursesList ref="coursesListRef" />
        </template>

        <!-- Placeholder for other views -->
        <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
          <h2 class="text-2xl font-bold text-gray-900 dark:text-white mb-4">
            {{ pageTitle }}
          </h2>
          <p class="text-gray-500 dark:text-gray-400">
            This page is coming soon.
          </p>
        </div>
      </main>
      
      <!-- Lessons View (handles both list and detail) -->
      <div v-if="currentRoute === '/lessons'">
        <!-- Header for list view only -->
        <div v-if="!isViewingDetail" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('lessons.title') }}
            </h2>
            <button
              @click="lessonsListRef?.openCreateModal()"
              class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
            >
              <PlusIcon class="h-5 w-5" />
              {{ t('lessons.addNew') }}
            </button>
          </div>
        </div>
        <!-- Single LessonsList instance with conditional padding -->
        <div :class="!isViewingDetail ? 'max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8' : ''">
          <LessonsList ref="lessonsListRef" />
        </div>
      </div>
    </div>
  </div>
</template>

