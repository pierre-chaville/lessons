<script setup lang="ts">
import {
  FolderIcon,
  FolderOpenIcon,
  DocumentTextIcon,
  ChevronRightIcon,
  ChevronDownIcon,
  PencilIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import { usePermissions } from '@/composables/usePermissions'
import type { CourseTreeNode } from '@/api/types'

const props = defineProps<{
  node: CourseTreeNode
  depth: number
  expanded: Set<number>
}>()

const emit = defineEmits<{
  (e: 'toggle', id: number): void
  (e: 'edit', node: CourseTreeNode): void
  (e: 'delete', node: CourseTreeNode): void
}>()

const { can } = usePermissions()

const hasChildren = () => props.node.children.length > 0
const isExpanded = () => props.expanded.has(props.node.id)
</script>

<template>
  <div>
    <div
      class="group flex items-center gap-2 px-4 py-2 hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors cursor-default"
      :style="{ paddingLeft: `${depth * 1.5 + 0.75}rem` }"
    >
      <!-- Expand/Collapse toggle -->
      <button
        v-if="hasChildren()"
        class="flex-shrink-0 p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        @click="emit('toggle', node.id)"
      >
        <ChevronDownIcon v-if="isExpanded()" class="h-4 w-4 text-gray-400 dark:text-gray-500" />
        <ChevronRightIcon v-else class="h-4 w-4 text-gray-400 dark:text-gray-500" />
      </button>
      <span v-else class="w-5" />

      <!-- Icon -->
      <FolderOpenIcon v-if="hasChildren() && isExpanded()" class="h-5 w-5 flex-shrink-0 text-amber-500 dark:text-amber-400" />
      <FolderIcon v-else-if="hasChildren()" class="h-5 w-5 flex-shrink-0 text-amber-500 dark:text-amber-400" />
      <DocumentTextIcon v-else class="h-5 w-5 flex-shrink-0 text-gray-400 dark:text-gray-500" />

      <!-- Name -->
      <span
        :class="[
          'flex-1 text-sm truncate',
          hasChildren()
            ? 'font-semibold text-gray-900 dark:text-white'
            : 'font-medium text-gray-700 dark:text-gray-300',
        ]"
      >
        {{ node.name }}
      </span>

      <!-- Edit button -->
      <button
        v-if="can('courses', 'update')"
        class="flex-shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-all"
        @click.stop="emit('edit', node)"
      >
        <PencilIcon class="h-3.5 w-3.5" />
      </button>

      <!-- Delete button -->
      <button
        v-if="can('courses', 'delete')"
        class="flex-shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-red-100 dark:hover:bg-red-900/30 text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-all"
        @click.stop="emit('delete', node)"
      >
        <TrashIcon class="h-3.5 w-3.5" />
      </button>

      <!-- Lesson count badge -->
      <span class="flex-shrink-0 inline-flex items-center justify-center min-w-[1.75rem] px-1.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400">
        {{ node.lesson_count }}
      </span>
    </div>

    <!-- Recursively render children -->
    <template v-if="hasChildren() && isExpanded()">
      <CourseTreeItem
        v-for="child in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :expanded="expanded"
        @toggle="(id) => emit('toggle', id)"
        @edit="(n) => emit('edit', n)"
        @delete="(n) => emit('delete', n)"
      />
    </template>
  </div>
</template>

<script lang="ts">
export default {
  name: 'CourseTreeItem',
}
</script>
