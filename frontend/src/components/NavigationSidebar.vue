<script setup lang="ts">
import { ref, computed } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  BookOpenIcon,
  AcademicCapIcon,
  TagIcon,
  DocumentTextIcon,
  UsersIcon,
  ClipboardDocumentListIcon,
  Cog6ToothIcon,
  CpuChipIcon,
  SparklesIcon,
  TrashIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon
} from '@heroicons/vue/24/outline';
import { usePermissions } from '@/composables/usePermissions';

const { t } = useI18n();
const { can, role } = usePermissions();

const emit = defineEmits<{ (e: 'navigate', route: string): void }>();

const props = defineProps<{ activeRoute?: string }>();

const isCollapsed = ref(false);
const openSections = ref<Set<string>>(new Set(['organization', 'administration']));

type NavigationItem = {
  key: string;
  label: string;
  icon: any;
  route: string;
  always: boolean;
};

type NavigationSection = {
  key: string;
  label: string;
  items: NavigationItem[];
};

const topNavigationItems: NavigationItem[] = [
  { key: 'lessons',     label: 'nav.lessons',     icon: BookOpenIcon,         route: '/lessons',     always: true },
  { key: 'assistant',   label: 'nav.assistant',   icon: SparklesIcon,         route: '/assistant',   always: true },
  { key: 'booklets',    label: 'nav.booklets',    icon: BookOpenIcon,         route: '/booklets',    always: false },
];

const organizationNavigationItems: NavigationItem[] = [
  { key: 'courses',     label: 'nav.courses',      icon: AcademicCapIcon,      route: '/courses',     always: true },
  { key: 'themes',      label: 'nav.themes',       icon: TagIcon,              route: '/themes',      always: true },
  { key: 'glossary',    label: 'nav.glossary',     icon: BookOpenIcon,         route: '/glossary',    always: false },
];

const administrationNavigationItems: NavigationItem[] = [
  { key: 'processing',  label: 'nav.processing',   icon: DocumentTextIcon,     route: '/processing',  always: false },
  { key: 'users',       label: 'nav.users',        icon: UsersIcon,            route: '/users',       always: false },
  { key: 'admin',       label: 'nav.admin',        icon: TrashIcon,            route: '/admin',       always: false },
  { key: 'audit',       label: 'nav.audit',        icon: ClipboardDocumentListIcon, route: '/admin/audit-log', always: false },
  { key: 'modelPresets',label: 'nav.modelPresets', icon: CpuChipIcon,          route: '/model-presets', always: false },
  { key: 'preferences', label: 'nav.preferences',  icon: Cog6ToothIcon,        route: '/preferences', always: false },
];

const isNavigationItemVisible = (item: NavigationItem) => {
  if (item.key === 'processing')  return can('tasks', 'read');
  if (item.key === 'booklets')    return can('lessons', 'update');
  if (item.key === 'glossary')    return can('glossary', 'read');
  if (item.key === 'users')       return can('users', 'manage');
  if (item.key === 'admin')       return role.value === 'admin';
  if (item.key === 'audit')       return role.value === 'admin';
  if (item.key === 'modelPresets') return can('model_presets', 'read');
  if (item.key === 'preferences') return can('configuration', 'read');
  return true;
};

const topItems = computed(() => topNavigationItems.filter(isNavigationItemVisible));

const navigationSections = computed<NavigationSection[]>(() =>
  [
    {
      key: 'organization',
      label: 'nav.organization',
      items: organizationNavigationItems.filter(isNavigationItemVisible),
    },
    {
      key: 'administration',
      label: 'nav.administration',
      items: administrationNavigationItems.filter(isNavigationItemVisible),
    },
  ].filter((section) => section.items.length > 0)
);

const collapsedNavigationItems = computed(() => [
  ...topItems.value,
  ...navigationSections.value.flatMap((section) => section.items),
]);

const toggleCollapse = () => { isCollapsed.value = !isCollapsed.value; };

const handleNavClick = (item: NavigationItem) => { emit('navigate', item.route); };

const isSectionActive = (section: NavigationSection) =>
  section.items.some((item) => props.activeRoute === item.route);

const isSectionOpen = (section: NavigationSection) =>
  openSections.value.has(section.key) || isSectionActive(section);

const toggleSection = (section: NavigationSection) => {
  const next = new Set(openSections.value);
  if (next.has(section.key)) next.delete(section.key);
  else next.add(section.key);
  openSections.value = next;
};
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
      <template v-if="isCollapsed">
        <button
          v-for="item in collapsedNavigationItems"
          :key="item.key"
          @click="handleNavClick(item)"
          :class="[
            'w-full flex items-center justify-center gap-3 px-3 py-2.5 rounded-md transition-all',
            props.activeRoute === item.route
              ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
              : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
          ]"
          :title="t(item.label)"
        >
          <component :is="item.icon" class="h-6 w-6 flex-shrink-0" />
        </button>
      </template>

      <template v-else>
        <button
          v-for="item in topItems"
          :key="item.key"
          @click="handleNavClick(item)"
          :class="[
            'w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-all',
            props.activeRoute === item.route
              ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
              : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
          ]"
        >
          <component :is="item.icon" class="h-6 w-6 flex-shrink-0" />
          <span class="font-medium text-sm">
            {{ t(item.label) }}
          </span>
        </button>

        <div
          v-for="section in navigationSections"
          :key="section.key"
          class="pt-3"
        >
          <button
            @click="toggleSection(section)"
            :class="[
              'w-full flex items-center justify-between rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors',
              isSectionActive(section)
                ? 'text-indigo-600 dark:text-indigo-400'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
            ]"
          >
            <span>{{ t(section.label) }}</span>
            <ChevronDownIcon
              :class="[
                'h-4 w-4 transition-transform',
                isSectionOpen(section) ? '' : '-rotate-90'
              ]"
            />
          </button>

          <div
            v-show="isSectionOpen(section)"
            class="ml-3 mt-1 space-y-1 border-l border-gray-200 pl-3 dark:border-gray-700"
          >
            <button
              v-for="item in section.items"
              :key="item.key"
              @click="handleNavClick(item)"
              :class="[
                'w-full flex items-center gap-3 px-3 py-2 rounded-md transition-all',
                props.activeRoute === item.route
                  ? 'bg-indigo-50 dark:bg-indigo-900/30 text-indigo-600 dark:text-indigo-400'
                  : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
              ]"
            >
              <component :is="item.icon" class="h-5 w-5 flex-shrink-0" />
              <span class="font-medium text-sm">
                {{ t(item.label) }}
              </span>
            </button>
          </div>
        </div>
      </template>
    </nav>
  </aside>
</template>

