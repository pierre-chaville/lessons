<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue';
import { SignedIn, SignedOut, SignInButton, UserButton } from '@clerk/vue';
import { useI18n } from 'vue-i18n';
import { Menu, MenuButton, MenuItems, MenuItem } from '@headlessui/vue';
import { marked } from 'marked';
import {
  ChevronDownIcon,
  LanguageIcon,
  PlusIcon,
  MicrophoneIcon,
  SunIcon,
  MoonIcon,
  ArrowDownTrayIcon,
  ArrowUpTrayIcon,
  InformationCircleIcon,
  QuestionMarkCircleIcon,
  XMarkIcon,
} from '@heroicons/vue/24/outline';
import { useAuth } from '@/composables/useAuth';
import { usePermissions } from '@/composables/usePermissions';
import NavigationSidebar from './components/NavigationSidebar.vue';
import LessonsList from './views/LessonsList.vue';
import SearchLessons from './views/SearchLessons.vue';
import AIAssistant from './views/AIAssistant.vue';
import CoursesList from './views/CoursesList.vue';
import ThemesList from './views/ThemesList.vue';
import GlossaryList from './views/GlossaryList.vue';
import BookletsList from './views/BookletsList.vue';
import BookletDetail from './views/BookletDetail.vue';
import ProcessingTasks from './views/ProcessingTasks.vue';
import UsersManagement from './views/UsersManagement.vue';
import AuditLogViewer from './views/AuditLogViewer.vue';
import AdminDeletedLessons from './views/AdminDeletedLessons.vue';
import ModelPresets from './views/ModelPresets.vue';
import Preferences from './views/Preferences.vue';

const { locale, t } = useI18n();
const { user, isLoaded, isSignedIn } = useAuth();
const { can } = usePermissions();

const appTitle = import.meta.env.VITE_APP_TITLE || t('app.title');
document.title = appTitle;

const allowedRoles = ['admin', 'reader', 'editor', 'publisher'];
const userRole = computed(() => {
  const role = user.value?.publicMetadata?.role || user.value?.unsafeMetadata?.role;
  return role ? String(role).toLowerCase() : '';
});
const hasAccess = computed(() => allowedRoles.includes(userRole.value));

// Initialize current route from URL
const getInitialRoute = () => {
  // Normalize: strip trailing slash (but keep "/" as-is)
  const raw = window.location.pathname;
  const path = raw.length > 1 && raw.endsWith('/') ? raw.slice(0, -1) : raw;

  // Known routes
  const routes = ['/search', '/assistant', '/courses', '/themes', '/glossary', '/booklets', '/booklets/detail', '/processing', '/users', '/admin', '/admin/audit-log', '/model-presets', '/preferences'];
  const match = routes.find(r => path === r);
  if (match) return match;

  // Lessons (list or detail)
  if (path === '/' || path === '/lessons' || path.startsWith('/lessons')) {
    return '/lessons';
  }
  if (path.startsWith('/booklets/')) {
    return '/booklets/detail';
  }
  if (path === '/booklets') {
    return '/booklets';
  }

  return '/lessons';
};

// Current route/view
const currentRoute = ref(getInitialRoute());

// Reference to components
const lessonsListRef = ref(null);
const coursesListRef = ref(null);
const themesListRef = ref(null);
const glossaryListRef = ref(null);
const usersListRef = ref(null);
const modelPresetsRef = ref(null);
const bookletsListRef = ref(null);
const selectedBookletId = ref(null);
const isHelpDrawerOpen = ref(false);
const helpMarkdownContent = ref('');
const helpHtmlContent = ref('');
const isHelpContentLoading = ref(false);
const lessonsHelpVideoUrl = import.meta.env.VITE_HELP_VIDEO_LESSONS_URL || import.meta.env.VITE_LESSONS_HELP_VIDEO_URL || '';

const HELP_MARKDOWN_FILES = import.meta.glob('./help/*/*.md', {
  query: '?raw',
  import: 'default',
});

// Check if we're viewing a lesson detail
const isViewingDetail = computed(() => {
  return lessonsListRef.value?.isViewingDetail || false;
});

const helpPageConfig = computed(() => {
  if (currentRoute.value === '/lessons') {
    return {
      slug: isViewingDetail.value ? 'lesson-detail' : 'lessons',
      supportsTour: true,
      videoUrl: !isViewingDetail.value ? lessonsHelpVideoUrl : '',
    };
  }
  if (currentRoute.value === '/search') return { slug: 'search', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/assistant') return { slug: 'assistant', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/courses') return { slug: 'courses', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/themes') return { slug: 'themes', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/glossary') return { slug: 'glossary', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/booklets' || currentRoute.value === '/booklets/detail') {
    return { slug: 'booklets', supportsTour: false, videoUrl: '' };
  }
  if (currentRoute.value === '/processing') return { slug: 'processing', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/users') return { slug: 'users', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/admin') return { slug: 'admin', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/admin/audit-log') return { slug: 'audit-log', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/model-presets') return { slug: 'model-presets', supportsTour: false, videoUrl: '' };
  if (currentRoute.value === '/preferences') return { slug: 'preferences', supportsTour: false, videoUrl: '' };
  return { slug: 'lessons', supportsTour: false, videoUrl: '' };
});

const resolveHelpPath = (language, slug) => {
  const exact = `./help/${language}/${slug}.md`;
  if (HELP_MARKDOWN_FILES[exact]) return exact;
  const fallbackEnglish = `./help/en/${slug}.md`;
  if (HELP_MARKDOWN_FILES[fallbackEnglish]) return fallbackEnglish;
  return null;
};

const loadHelpContent = async () => {
  const path = resolveHelpPath(locale.value, helpPageConfig.value.slug);
  if (!path) {
    helpMarkdownContent.value = '';
    helpHtmlContent.value = '';
    return;
  }
  isHelpContentLoading.value = true;
  try {
    const loader = HELP_MARKDOWN_FILES[path];
    const raw = await loader();
    helpMarkdownContent.value = typeof raw === 'string' ? raw : String(raw ?? '');
    helpHtmlContent.value = marked.parse(helpMarkdownContent.value);
  } finally {
    isHelpContentLoading.value = false;
  }
};

const openHelpDrawer = async () => {
  isHelpDrawerOpen.value = true;
  await loadHelpContent();
};

const closeHelpDrawer = () => {
  isHelpDrawerOpen.value = false;
};

const startCurrentPageTour = () => {
  if (!helpPageConfig.value.supportsTour) return;
  if (currentRoute.value === '/lessons') {
    if (isViewingDetail.value) {
      lessonsListRef.value?.startLessonDetailTour?.();
    } else {
      lessonsListRef.value?.startHomeTour?.();
    }
  }
};

// Handle navigation
const handleNavigation = (route) => {
  currentRoute.value = route;
  if (isHelpDrawerOpen.value) {
    void loadHelpContent();
  }
  // Update URL without lesson ID when navigating to main routes
  if (route === '/lessons') {
    if (lessonsListRef.value?.goToLessonsHome) {
      lessonsListRef.value.goToLessonsHome();
    } else {
      window.history.pushState({}, '', route);
    }
  } else {
    window.history.pushState({}, '', route);
  }
};

// Get current page title
const pageTitle = computed(() => {
  switch (currentRoute.value) {
    case '/lessons':
      return t('lessons.title');
    case '/search':
      return t('search.title');
    case '/assistant':
      return t('assistant.title');
    case '/courses':
      return t('courses.title');
    case '/themes':
      return t('themes.title');
    case '/glossary':
      return t('glossary.title');
    case '/booklets':
      return t('booklets.title');
    case '/booklets/detail':
      return t('booklets.title');
    case '/processing':
      return t('nav.processing');
    case '/users':
      return t('users.title');
    case '/admin':
      return t('admin.title');
    case '/admin/audit-log':
      return t('nav.audit');
    case '/model-presets':
      return t('nav.modelPresets');
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
};

const parseBookletIdFromPath = () => {
  const match = window.location.pathname.match(/^\/booklets\/(\d+)$/);
  if (!match) return null;
  const id = Number(match[1]);
  return Number.isFinite(id) ? id : null;
};

const openBookletDetail = (bookletId) => {
  selectedBookletId.value = bookletId;
  currentRoute.value = '/booklets/detail';
  window.history.pushState({ bookletId }, '', `/booklets/${bookletId}`);
};

const closeBookletDetail = () => {
  selectedBookletId.value = null;
  currentRoute.value = '/booklets';
  window.history.pushState({}, '', '/booklets');
};

const handleAppPopState = () => {
  currentRoute.value = getInitialRoute();
  selectedBookletId.value = parseBookletIdFromPath();
};

// Initialize dark mode on mount
onMounted(() => {
  // Check localStorage first, then system preference
  const savedDarkMode = localStorage.getItem('darkMode');
  if (savedDarkMode !== null) {
    isDarkMode.value = savedDarkMode === 'true';
  } else {
    // Check system preference if no saved preference
    isDarkMode.value = window.matchMedia('(prefers-color-scheme: light)').matches;
  }
  
  // Apply the initial state
  applyDarkMode(isDarkMode.value);

  selectedBookletId.value = parseBookletIdFromPath();
  window.addEventListener('popstate', handleAppPopState);
});

onBeforeUnmount(() => {
  window.removeEventListener('popstate', handleAppPopState);
});

watch(
  () => [currentRoute.value, locale.value, isViewingDetail.value],
  () => {
    if (isHelpDrawerOpen.value) {
      void loadHelpContent();
    }
  }
);


</script>

<template>
  <SignedOut>
    <div class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-6">
      <div class="text-center">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">{{ t('auth.signInTitle') }}</h2>
        <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{{ t('auth.signInDesc') }}</p>
        <SignInButton mode="redirect">
          <button class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md transition-colors">
            {{ t('auth.signIn') }}
          </button>
        </SignInButton>
      </div>
    </div>
  </SignedOut>
  <SignedIn>
    <div v-if="!isLoaded" class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900">
      <p class="text-gray-600 dark:text-gray-300">{{ t('auth.loading') }}</p>
    </div>
    <div v-else-if="!hasAccess" class="min-h-screen flex items-center justify-center bg-gray-50 dark:bg-gray-900 p-6">
      <div class="max-w-md text-center">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-2">{{ t('auth.noAccessTitle') }}</h2>
        <p class="text-sm text-gray-600 dark:text-gray-300">{{ t('auth.noAccessDesc') }}</p>
      </div>
    </div>
    <div v-else class="flex min-h-screen bg-gray-50 dark:bg-gray-900 transition-colors">
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
              {{ appTitle }}
            </h1>
          </div>
          
          <div class="flex items-center gap-3">
            <button
              data-tour="help-button"
              @click="openHelpDrawer"
              :title="t('help.open')"
              class="inline-flex items-center justify-center rounded-md p-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              <QuestionMarkCircleIcon class="h-5 w-5" />
            </button>
            <!-- Dark Mode Toggle -->
            <button
              data-tour="theme-toggle"
              @click="toggleDarkMode"
              class="inline-flex items-center justify-center rounded-md p-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              :title="isDarkMode ? t('theme.light') : t('theme.dark')"
            >
              <SunIcon v-if="isDarkMode" class="h-5 w-5" />
              <MoonIcon v-else class="h-5 w-5" />
            </button>
            <!-- User Menu -->
            <SignedIn>
              <UserButton />
            </SignedIn>
            
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

      <!-- Search View -->
      <div v-if="currentRoute === '/search'">
        <!-- Header -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('search.title') }}
            </h2>
          </div>
        </div>
        <!-- Content -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
          <SearchLessons />
        </div>
      </div>

      <!-- AI Assistant View -->
      <div v-else-if="currentRoute === '/assistant'">
        <AIAssistant />
      </div>

      <!-- Courses View -->
      <div v-else-if="currentRoute === '/courses'">
        <!-- Header -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('courses.title') }}
            </h2>
            <div class="flex items-center gap-2">
              <button
                v-if="can('configuration', 'update')"
                @click="coursesListRef?.openCsvHelpModal?.()"
                class="inline-flex items-center gap-x-2 rounded-md px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                <InformationCircleIcon class="h-4 w-4" />
                {{ t('courses.csvHelpButton') }}
              </button>
              <button
                v-if="can('configuration', 'update')"
                @click="coursesListRef?.downloadBulkCsv?.()"
                class="inline-flex items-center gap-x-2 rounded-md px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                <ArrowDownTrayIcon class="h-4 w-4" />
                {{ t('courses.exportLessonsCsv') }}
              </button>
              <button
                v-if="can('configuration', 'update')"
                @click="coursesListRef?.openBulkCsvPicker?.()"
                class="inline-flex items-center gap-x-2 rounded-md px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                <ArrowUpTrayIcon class="h-4 w-4" />
                {{ t('courses.importLessonsCsv') }}
              </button>
              <button
                v-if="can('courses', 'create')"
                @click="coursesListRef?.openCreateModal()"
                class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
              >
                <PlusIcon class="h-5 w-5" />
                {{ t('courses.addNew') }}
              </button>
            </div>
          </div>
        </div>
        <!-- Content -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
          <CoursesList ref="coursesListRef" />
        </div>
      </div>

      <!-- Themes View -->
      <div v-else-if="currentRoute === '/themes'">
        <!-- Header -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('themes.title') }}
            </h2>
            <button
              v-if="can('themes', 'create')"
              @click="themesListRef?.openCreateModal()"
              class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
            >
              <PlusIcon class="h-5 w-5" />
              {{ t('themes.addNew') }}
            </button>
          </div>
        </div>
        <!-- Content -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
          <ThemesList ref="themesListRef" />
        </div>
      </div>

      <!-- Glossary View -->
      <div v-else-if="currentRoute === '/glossary'">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('glossary.title') }}
            </h2>
            <div class="flex items-center gap-2">
              <button
                v-if="can('glossary', 'create')"
                @click="glossaryListRef?.exportYaml?.()"
                class="inline-flex items-center gap-x-2 rounded-md px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                <ArrowDownTrayIcon class="h-4 w-4" />
                {{ t('glossary.exportYaml') }}
              </button>
              <button
                v-if="can('glossary', 'create')"
                @click="glossaryListRef?.openImportDialog?.()"
                class="inline-flex items-center gap-x-2 rounded-md px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                <ArrowUpTrayIcon class="h-4 w-4" />
                {{ t('glossary.importYaml') }}
              </button>
              <button
                v-if="can('glossary', 'create')"
                @click="glossaryListRef?.openCreateModal()"
                class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
              >
                <PlusIcon class="h-5 w-5" />
                {{ t('glossary.addNew') }}
              </button>
            </div>
          </div>
        </div>
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
          <GlossaryList ref="glossaryListRef" />
        </div>
      </div>

      <!-- Booklets View -->
      <div v-else-if="currentRoute === '/booklets'">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('booklets.title') }}
            </h2>
            <button
              v-if="can('lessons', 'update')"
              @click="bookletsListRef?.openCreateModal()"
              class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
            >
              <PlusIcon class="h-5 w-5" />
              {{ t('booklets.addNew') }}
            </button>
          </div>
        </div>
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
          <BookletsList ref="bookletsListRef" @open-detail="openBookletDetail" />
        </div>
      </div>

      <!-- Booklet Detail View -->
      <div v-else-if="currentRoute === '/booklets/detail'">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <BookletDetail :booklet-id="selectedBookletId" @back="closeBookletDetail" />
        </div>
      </div>

      <!-- Processing View -->
      <div v-else-if="currentRoute === '/processing'">
        <!-- Header -->
        <div class="w-full px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('processing.title') }}
            </h2>
          </div>
        </div>
        <!-- Content -->
        <div class="w-full px-4 sm:px-6 lg:px-8 pb-8">
          <ProcessingTasks />
        </div>
      </div>

      <!-- Users View -->
      <div v-else-if="currentRoute === '/users'">
        <!-- Header -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white flex items-center gap-2">
              {{ t('users.title') }}
              <span
                v-if="usersListRef?.userCount"
                class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-400"
              >
                {{ usersListRef.userCount }}
              </span>
            </h2>
            <button
              @click="usersListRef?.openAddModal()"
              class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
            >
              <PlusIcon class="h-5 w-5" />
              {{ t('users.addUser') }}
            </button>
          </div>
        </div>
        <!-- Content -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
          <UsersManagement ref="usersListRef" />
        </div>
      </div>

      <!-- Model Presets View -->
      <div v-else-if="currentRoute === '/model-presets'">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('modelPresets.title') }}
            </h2>
            <button
              v-if="can('model_presets', 'create')"
              @click="modelPresetsRef?.openCreateModal()"
              class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
            >
              <PlusIcon class="h-5 w-5" />
              {{ t('modelPresets.addNew') }}
            </button>
          </div>
        </div>
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
          <ModelPresets ref="modelPresetsRef" />
        </div>
      </div>

      <!-- Preferences View -->
      <div v-else-if="currentRoute === '/preferences'" class="h-full flex flex-col">
        <Preferences />
      </div>

      <!-- Admin View -->
      <div v-else-if="currentRoute === '/admin'">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <AdminDeletedLessons />
        </div>
      </div>

      <!-- Global Audit View -->
      <div v-else-if="currentRoute === '/admin/audit-log'">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <AuditLogViewer />
        </div>
      </div>

      <!-- Placeholder for other views -->
      <main v-else-if="!isViewingDetail && currentRoute !== '/lessons' && currentRoute !== '/search' && currentRoute !== '/assistant' && currentRoute !== '/courses' && currentRoute !== '/themes' && currentRoute !== '/glossary' && currentRoute !== '/booklets' && currentRoute !== '/booklets/detail' && currentRoute !== '/processing' && currentRoute !== '/users' && currentRoute !== '/admin' && currentRoute !== '/admin/audit-log' && currentRoute !== '/model-presets' && currentRoute !== '/preferences'" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
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
        <div v-if="!isViewingDetail" class="mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('lessons.title') }}
            </h2>
            <button
              v-if="can('lessons', 'create')"
              @click="lessonsListRef?.openCreateModal()"
              class="inline-flex items-center gap-x-2 rounded-md bg-indigo-600 dark:bg-indigo-500 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 dark:hover:bg-indigo-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600 dark:focus-visible:outline-indigo-500 transition-colors"
            >
              <PlusIcon class="h-5 w-5" />
              {{ t('lessons.addNew') }}
            </button>
          </div>
        </div>
        <!-- LessonsList with two-panel layout -->
        <div :class="!isViewingDetail ? 'mx-auto px-4 sm:px-6 lg:px-8 pb-8' : ''">
          <LessonsList ref="lessonsListRef" />
        </div>
      </div>
    </div>

    <div v-if="isHelpDrawerOpen" class="fixed inset-0 z-50">
      <div class="absolute inset-0 bg-black/40" @click="closeHelpDrawer"></div>
      <aside class="absolute right-0 top-0 h-full w-full max-w-xl bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 shadow-xl overflow-y-auto">
        <div class="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white">
            {{ t('help.drawerTitle') }}
          </h3>
          <button
            @click="closeHelpDrawer"
            :title="t('help.close')"
            class="rounded-md p-2 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <XMarkIcon class="h-5 w-5" />
          </button>
        </div>

        <div class="px-5 py-4 space-y-6">
          <section v-if="helpPageConfig.supportsTour" class="space-y-2">
            <h4 class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ t('help.guidedTourTitle') }}
            </h4>
            <p class="text-sm text-gray-600 dark:text-gray-300">
              {{ t('help.guidedTourDescription') }}
            </p>
            <button
              @click="closeHelpDrawer(); startCurrentPageTour()"
              class="inline-flex items-center gap-2 rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-500"
            >
              {{ t('lessons.startTour') }}
            </button>
          </section>

          <section v-if="helpPageConfig.videoUrl" class="space-y-2">
            <h4 class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ t('help.videoTitle') }}
            </h4>
            <div class="aspect-video rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700">
              <iframe
                :src="helpPageConfig.videoUrl"
                class="h-full w-full"
                :title="t('help.videoTitle')"
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowfullscreen
              ></iframe>
            </div>
          </section>

          <section class="space-y-2">
            <h4 class="text-sm font-semibold text-gray-900 dark:text-white">
              {{ t('help.explanationTitle') }}
            </h4>
            <p v-if="isHelpContentLoading" class="text-sm text-gray-600 dark:text-gray-300">
              {{ t('help.loading') }}
            </p>
            <div
              v-else-if="helpHtmlContent"
              class="prose prose-sm max-w-none text-gray-700 dark:prose-invert dark:text-gray-200"
              v-html="helpHtmlContent"
            ></div>
            <p v-else class="text-sm text-gray-600 dark:text-gray-300">
              {{ t('help.noContent') }}
            </p>
          </section>
        </div>
      </aside>
    </div>
    </div>
  </SignedIn>
</template>

