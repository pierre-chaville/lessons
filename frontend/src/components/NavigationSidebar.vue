<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  BookOpenIcon,
  MagnifyingGlassIcon,
  AcademicCapIcon,
  TagIcon,
  DocumentTextIcon,
  Cog6ToothIcon,
  ChevronLeftIcon,
  ChevronRightIcon
} from '@heroicons/vue/24/outline';
import { usePermissions } from '@/composables/usePermissions';

const { t } = useI18n();
const { can } = usePermissions();

const emit = defineEmits<{ (e: 'navigate', route: string): void }>();

const props = defineProps<{ activeRoute?: string }>();

const isCollapsed = ref(false);

const allNavigationItems = [
  { key: 'lessons',     label: 'nav.lessons',     icon: BookOpenIcon,         route: '/lessons',     always: true },
  { key: 'search',      label: 'nav.search',       icon: MagnifyingGlassIcon,  route: '/search',      always: true },
  { key: 'courses',     label: 'nav.courses',      icon: AcademicCapIcon,      route: '/courses',     always: true },
  { key: 'themes',      label: 'nav.themes',       icon: TagIcon,              route: '/themes',      always: true },
  { key: 'processing',  label: 'nav.processing',   icon: DocumentTextIcon,     route: '/processing',  always: false },
  { key: 'preferences', label: 'nav.preferences',  icon: Cog6ToothIcon,        route: '/preferences', always: false },
];

const navigationItems = computed(() =>
  allNavigationItems.filter((item) => {
    if (item.key === 'processing')  return can('tasks', 'read');
    if (item.key === 'preferences') return can('configuration', 'read');
    return true;
  })
);

const toggleCollapse = () => { isCollapsed.value = !isCollapsed.value; };

const handleNavClick = (item: { route: string }) => { emit('navigate', item.route); };
</script>

<template>
  <aside
    :class="[
      'flex-shrink-0 h-screen sticky top-0 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 transition-all duration-300 ease-in-out z-40',
      isCollapsed ? 'w-16' : 'w-64'
    ]"
  >
    <!-- Header -->
    <div class="h-16 flex items-center justify-between px-4 border-b border-gray-200 dark:border-gray-700">
      <transition
        enter-active-class="transition-opacity duration-200"
        leave-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        leave-to-class="opacity-0"
      >
        <h2 v-if="!isCollapsed" class="text-lg font-semibold text-gray-900 dark:text-white">
          {{ t('nav.menu') }}
        </h2>
      </transition>
      <button
        @click="toggleCollapse"
        class="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400 transition-colors"
        :title="isCollapsed ? t('nav.expand') : t('nav.collapse')"
      >
        <ChevronLeftIcon v-if="!isCollapsed" class="h-5 w-5" />
        <ChevronRightIcon v-else class="h-5 w-5" />
      </button>
    </div>

    <!-- Navigation Items -->
    <nav class="p-2 space-y-1">
      <button
        v-for="item in navigationItems"
        :key="item.key"
        @click="handleNavClick(item)"
        :class="[
          'w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-all',
          props.activeRoute === item.route
            ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
            : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700',
          isCollapsed ? 'justify-center' : ''
        ]"
        :title="isCollapsed ? t(item.label) : ''"
      >
        <component :is="item.icon" class="h-6 w-6 flex-shrink-0" />
        <transition
          enter-active-class="transition-opacity duration-200"
          leave-active-class="transition-opacity duration-200"
          enter-from-class="opacity-0"
          leave-to-class="opacity-0"
        >
          <span v-if="!isCollapsed" class="font-medium text-sm">
            {{ t(item.label) }}
          </span>
        </transition>
      </button>
    </nav>
  </aside>
</template>

