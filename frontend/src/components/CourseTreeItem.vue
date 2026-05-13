<script setup lang="ts">
import {
  FolderIcon,
  FolderOpenIcon,
  DocumentTextIcon,
  ChevronRightIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  PencilIcon,
  TrashIcon,
} from '@heroicons/vue/24/outline'
import { usePermissions } from '@/composables/usePermissions'
import type { CourseTreeNode } from '@/api/types'

const props = withDefaults(defineProps<{
  node: CourseTreeNode
  depth: number
  expanded: Set<number>
  selectedId?: number | null
  showActions?: boolean
  isFirst?: boolean
  isLast?: boolean
  draggedId?: number | null
  dropTargetId?: number | null
}>(), {
  selectedId: null,
  showActions: true,
  isFirst: false,
  isLast: false,
  draggedId: null,
  dropTargetId: null,
})

const emit = defineEmits<{
  (e: 'toggle', id: number): void
  (e: 'edit', node: CourseTreeNode): void
  (e: 'delete', node: CourseTreeNode): void
  (e: 'select', node: CourseTreeNode): void
  (e: 'moveUp', node: CourseTreeNode): void
  (e: 'moveDown', node: CourseTreeNode): void
  (e: 'dragStart', node: CourseTreeNode): void
  (e: 'dragEnter', node: CourseTreeNode): void
  (e: 'drop', node: CourseTreeNode): void
  (e: 'dragEnd'): void
}>()

const { can } = usePermissions()

const hasChildren = () => props.node.children.length > 0
const isExpanded = () => props.expanded.has(props.node.id)
const isSelected = () => props.selectedId === props.node.id
const canDrag = () => props.showActions && can('courses', 'update')
const isDropTarget = () => props.dropTargetId === props.node.id && props.draggedId !== props.node.id

const handleRowClick = () => {
  emit('select', props.node)
}

const handleDragStart = (event: DragEvent) => {
  if (!canDrag()) return
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', String(props.node.id))
  }
  emit('dragStart', props.node)
}

const handleDragEnter = (event: DragEvent) => {
  if (!canDrag()) return
  event.preventDefault()
  emit('dragEnter', props.node)
}

const handleDragOver = (event: DragEvent) => {
  if (!canDrag()) return
  event.preventDefault()
}

const handleDrop = (event: DragEvent) => {
  if (!canDrag()) return
  event.preventDefault()
  emit('drop', props.node)
}
</script>

<template>
  <div>
    <div
      :class="[
        'group flex items-center gap-2 px-4 py-2 transition-colors',
        isSelected()
          ? 'bg-indigo-50 dark:bg-indigo-900/30'
          : 'hover:bg-gray-50 dark:hover:bg-gray-700/50',
        isDropTarget()
          ? 'ring-1 ring-inset ring-indigo-400 dark:ring-indigo-500 bg-indigo-50/60 dark:bg-indigo-900/30'
          : '',
        selectedId !== undefined ? 'cursor-pointer' : 'cursor-default',
      ]"
      :style="{ paddingLeft: `${depth * 1.5 + 0.75}rem` }"
      :draggable="canDrag()"
      @click="handleRowClick"
      @dragstart="handleDragStart"
      @dragenter="handleDragEnter"
      @dragover="handleDragOver"
      @drop="handleDrop"
      @dragend="emit('dragEnd')"
    >
      <!-- Expand/Collapse toggle -->
      <button
        v-if="hasChildren()"
        class="flex-shrink-0 p-0.5 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
        @click.stop="emit('toggle', node.id)"
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
          isSelected()
            ? 'font-semibold text-indigo-600 dark:text-indigo-400'
            : hasChildren()
              ? 'font-semibold text-gray-900 dark:text-white'
              : 'font-medium text-gray-700 dark:text-gray-300',
        ]"
      >
        {{ node.name }}
      </span>

      <!-- Move up/down buttons (Courses page only) -->
      <template v-if="showActions && can('courses', 'update')">
        <button
          :disabled="isFirst"
          class="flex-shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-all disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
          @click.stop="emit('moveUp', node)"
        >
          <ChevronUpIcon class="h-3.5 w-3.5" />
        </button>
        <button
          :disabled="isLast"
          class="flex-shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-all disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-transparent"
          @click.stop="emit('moveDown', node)"
        >
          <ChevronDownIcon class="h-3.5 w-3.5" />
        </button>
      </template>

      <!-- Edit button (Courses page only) -->
      <button
        v-if="showActions && can('courses', 'update')"
        class="flex-shrink-0 p-1 rounded opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-all"
        @click.stop="emit('edit', node)"
      >
        <PencilIcon class="h-3.5 w-3.5" />
      </button>

      <!-- Delete button (Courses page only) -->
      <button
        v-if="showActions && can('courses', 'delete')"
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
        v-for="(child, idx) in node.children"
        :key="child.id"
        :node="child"
        :depth="depth + 1"
        :expanded="expanded"
        :selected-id="selectedId"
        :show-actions="showActions"
        :is-first="idx === 0"
        :is-last="idx === node.children.length - 1"
        :dragged-id="draggedId"
        :drop-target-id="dropTargetId"
        @toggle="(id) => emit('toggle', id)"
        @edit="(n) => emit('edit', n)"
        @delete="(n) => emit('delete', n)"
        @select="(n) => emit('select', n)"
        @move-up="(n) => emit('moveUp', n)"
        @move-down="(n) => emit('moveDown', n)"
        @drag-start="(n) => emit('dragStart', n)"
        @drag-enter="(n) => emit('dragEnter', n)"
        @drop="(n) => emit('drop', n)"
        @drag-end="emit('dragEnd')"
      />
    </template>
  </div>
</template>

<script lang="ts">
export default {
  name: 'CourseTreeItem',
}
</script>
