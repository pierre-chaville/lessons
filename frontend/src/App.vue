<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue';
import { SignedIn, SignedOut, SignInButton, SignOutButton, UserButton } from '@clerk/vue';
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
import { useAuth } from '@/composables/useAuth';
import { usePermissions } from '@/composables/usePermissions';
import NavigationSidebar from './components/NavigationSidebar.vue';
import LessonsList from './views/LessonsList.vue';
import SearchLessons from './views/SearchLessons.vue';
import CoursesList from './views/CoursesList.vue';
import ThemesList from './views/ThemesList.vue';
import BookletsList from './views/BookletsList.vue';
import BookletDetail from './views/BookletDetail.vue';
import ProcessingTasks from './views/ProcessingTasks.vue';
import UsersManagement from './views/UsersManagement.vue';
import AuditLogViewer from './views/AuditLogViewer.vue';
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
  const routes = ['/search', '/courses', '/themes', '/booklets', '/booklets/detail', '/processing', '/users', '/admin/audit-log', '/preferences'];
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
const usersListRef = ref(null);
const bookletsListRef = ref(null);
const selectedBookletId = ref(null);

// Check if we're viewing a lesson detail
const isViewingDetail = computed(() => {
  return lessonsListRef.value?.isViewingDetail || false;
});

// Handle navigation
const handleNavigation = (route) => {
  currentRoute.value = route;
  // Update URL without lesson ID when navigating to main routes
  if (route === '/lessons') {
    // Only update if we're not on a lesson detail page
    if (!window.location.pathname.match(/^\/lessons\/[a-zA-Z0-9]+$/)) {
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
    case '/courses':
      return t('courses.title');
    case '/themes':
      return t('themes.title');
    case '/booklets':
      return t('booklets.title');
    case '/booklets/detail':
      return t('booklets.title');
    case '/processing':
      return t('nav.processing');
    case '/users':
      return t('users.title');
    case '/admin/audit-log':
      return t('nav.audit');
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
            <!-- Dark Mode Toggle -->
            <button
              @click="toggleDarkMode"
              class="inline-flex items-center justify-center rounded-md p-2 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              :title="isDarkMode ? t('theme.light') : t('theme.dark')"
            >
              <SunIcon v-if="isDarkMode" class="h-5 w-5" />
              <MoonIcon v-else class="h-5 w-5" />
            </button>
            <!-- User Menu -->
            <SignedIn>
              <div class="flex items-center gap-2">
                <UserButton />
                <SignOutButton>
                  <button class="inline-flex items-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors">
                    {{ t('auth.signOut') }}
                  </button>
                </SignOutButton>
              </div>
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

      <!-- Courses View -->
      <div v-else-if="currentRoute === '/courses'">
        <!-- Header -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('courses.title') }}
            </h2>
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
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 pb-0">
          <div class="mb-6 flex justify-between items-center">
            <h2 class="text-xl font-semibold text-gray-900 dark:text-white">
              {{ t('processing.title') }}
            </h2>
          </div>
        </div>
        <!-- Content -->
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
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

      <!-- Preferences View -->
      <div v-else-if="currentRoute === '/preferences'" class="h-full flex flex-col">
        <Preferences />
      </div>

      <!-- Global Audit View -->
      <div v-else-if="currentRoute === '/admin/audit-log'">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <AuditLogViewer />
        </div>
      </div>

      <!-- Placeholder for other views -->
      <main v-else-if="!isViewingDetail && currentRoute !== '/lessons' && currentRoute !== '/search' && currentRoute !== '/courses' && currentRoute !== '/themes' && currentRoute !== '/booklets' && currentRoute !== '/booklets/detail' && currentRoute !== '/processing' && currentRoute !== '/users' && currentRoute !== '/admin/audit-log' && currentRoute !== '/preferences'" class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
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
    </div>
  </SignedIn>
</template>

