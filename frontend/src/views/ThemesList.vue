<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  TagIcon,
  TrashIcon,
  CheckIcon,
  ExclamationTriangleIcon,
} from '@heroicons/vue/24/outline'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { themesApi } from '@/api/themes'
import { useToast } from '@/composables/useToast'
import { usePermissions } from '@/composables/usePermissions'
import CourseTreeItem from '@/components/CourseTreeItem.vue'
import { hierarchyLabel } from '@/utils/hierarchyLabel'
import type { Theme, ThemeTreeNode } from '@/api/types'

const { t } = useI18n()
const toast = useToast()
const { can } = usePermissions()

const themes = ref<Theme[]>([])
const tree = ref<ThemeTreeNode[]>([])
const loading = ref(true)
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showDeleteConfirm = ref(false)

const formData = ref({ name: '', description: '', parent_id: null as number | null })

const editingTheme = ref<Theme | null>(null)
const deletingTheme = ref<Theme | null>(null)
const isSaving = ref(false)
const isDeleting = ref(false)

const expanded = ref<Set<number>>(new Set())
const draggedNode = ref<ThemeTreeNode | null>(null)
const dropTargetId = ref<number | null>(null)
const isRootDropTarget = ref(false)
const isDragReordering = ref(false)

const toggleExpand = (id: number) => {
  if (expanded.value.has(id)) {
    expanded.value.delete(id)
  } else {
    expanded.value.add(id)
  }
}

const expandAll = (nodes: ThemeTreeNode[]) => {
  for (const node of nodes) {
    if (node.children.length > 0) {
      expanded.value.add(node.id)
      expandAll(node.children)
    }
  }
}

const fetchData = async () => {
  try {
    loading.value = true
    const [flatList, treeData] = await Promise.all([themesApi.list(), themesApi.tree()])
    themes.value = flatList
    tree.value = treeData
    expandAll(treeData)
  } catch {
    toast.error(t('themes.fetchFailed'))
  } finally {
    loading.value = false
  }
}

const openCreateModal = () => {
  formData.value = { name: '', description: '', parent_id: null }
  showCreateModal.value = true
}

const closeCreateModal = () => {
  showCreateModal.value = false
  formData.value = { name: '', description: '', parent_id: null }
}

const openEditModal = (theme: ThemeTreeNode) => {
  editingTheme.value = theme
  formData.value = {
    name: theme.name,
    description: theme.description ?? '',
    parent_id: theme.parent_id ?? null,
  }
  showEditModal.value = true
}

const closeEditModal = () => {
  showEditModal.value = false
  editingTheme.value = null
  formData.value = { name: '', description: '', parent_id: null }
}

const createTheme = async () => {
  if (!formData.value.name.trim()) {
    toast.error(t('themes.nameRequired'))
    return
  }
  try {
    isSaving.value = true
    await themesApi.create({
      name: formData.value.name.trim(),
      description: formData.value.description.trim() || null,
      parent_id: formData.value.parent_id,
    })
    await fetchData()
    closeCreateModal()
  } catch {
    toast.error(t('themes.createFailed'))
  } finally {
    isSaving.value = false
  }
}

const updateTheme = async () => {
  if (!formData.value.name.trim() || !editingTheme.value) {
    toast.error(t('themes.nameRequired'))
    return
  }
  try {
    isSaving.value = true
    await themesApi.update(editingTheme.value.hashid, {
      name: formData.value.name.trim(),
      description: formData.value.description.trim() || null,
      parent_id: formData.value.parent_id,
    })
    await fetchData()
    closeEditModal()
  } catch {
    toast.error(t('themes.updateFailed'))
  } finally {
    isSaving.value = false
  }
}

const confirmDelete = (theme: ThemeTreeNode) => {
  deletingTheme.value = theme
  showDeleteConfirm.value = true
}

const cancelDelete = () => {
  showDeleteConfirm.value = false
  deletingTheme.value = null
}

const deleteTheme = async () => {
  if (!deletingTheme.value) return
  try {
    isDeleting.value = true
    await themesApi.delete(deletingTheme.value.hashid)
    await fetchData()
    cancelDelete()
  } catch {
    toast.error(t('themes.deleteFailed'))
  } finally {
    isDeleting.value = false
  }
}

const moveTheme = async (node: ThemeTreeNode, direction: 'up' | 'down') => {
  try {
    await themesApi.reorder(node.hashid, direction)
    await fetchData()
  } catch {
    toast.error(t('themes.updateFailed'))
  }
}

const getSiblingList = (
  parentId: number | null,
  nodes: ThemeTreeNode[] = tree.value,
): ThemeTreeNode[] | null => {
  if (parentId === null) return nodes

  for (const node of nodes) {
    if (node.id === parentId) return node.children
    const found = getSiblingList(parentId, node.children)
    if (found) return found
  }

  return null
}

const findNodeById = (
  id: number,
  nodes: ThemeTreeNode[] = tree.value,
): ThemeTreeNode | null => {
  for (const node of nodes) {
    if (node.id === id) return node
    const found = findNodeById(id, node.children)
    if (found) return found
  }
  return null
}

const isDescendantNode = (ancestorId: number, nodeId: number): boolean => {
  const ancestor = findNodeById(ancestorId)
  if (!ancestor) return false

  const stack = [...ancestor.children]
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current) continue
    if (current.id === nodeId) return true
    stack.push(...current.children)
  }
  return false
}

const moveWithinSiblings = async (
  sourceNode: ThemeTreeNode,
  targetNode: ThemeTreeNode,
) => {
  const siblings = getSiblingList(sourceNode.parent_id)
  if (!siblings) return

  const sourceIndex = siblings.findIndex((sibling) => sibling.id === sourceNode.id)
  const targetIndex = siblings.findIndex((sibling) => sibling.id === targetNode.id)
  if (sourceIndex === -1 || targetIndex === -1 || sourceIndex === targetIndex) return

  const direction: 'up' | 'down' = sourceIndex < targetIndex ? 'down' : 'up'
  const moveCount = Math.abs(targetIndex - sourceIndex)
  for (let i = 0; i < moveCount; i += 1) {
    await themesApi.reorder(sourceNode.hashid, direction)
  }
}

const handleDragStart = (node: ThemeTreeNode) => {
  if (!can('themes', 'update')) return
  draggedNode.value = node
  dropTargetId.value = null
  isRootDropTarget.value = false
}

const handleDragEnter = (node: ThemeTreeNode) => {
  if (!draggedNode.value || draggedNode.value.id === node.id || isDragReordering.value) {
    dropTargetId.value = null
    isRootDropTarget.value = false
    return
  }

  if (isDescendantNode(draggedNode.value.id, node.id)) {
    dropTargetId.value = null
    isRootDropTarget.value = false
    return
  }

  isRootDropTarget.value = false
  dropTargetId.value = node.id
}

const resetDragState = () => {
  draggedNode.value = null
  dropTargetId.value = null
  isRootDropTarget.value = false
}

const handleRootDragEnter = (event: DragEvent) => {
  if (!draggedNode.value || isDragReordering.value) return
  event.preventDefault()
  dropTargetId.value = null
  isRootDropTarget.value = true
}

const handleRootDragOver = (event: DragEvent) => {
  if (!draggedNode.value || isDragReordering.value) return
  event.preventDefault()
}

const handleRootDrop = async (event: DragEvent) => {
  event.preventDefault()
  const sourceNode = draggedNode.value
  if (!sourceNode || isDragReordering.value) {
    resetDragState()
    return
  }

  if (sourceNode.parent_id === null) {
    resetDragState()
    return
  }

  try {
    isDragReordering.value = true
    await themesApi.update(sourceNode.hashid, { parent_id: 0 })
    await fetchData()
  } catch {
    toast.error(t('themes.updateFailed'))
  } finally {
    isDragReordering.value = false
    resetDragState()
  }
}

const handleDrop = async (targetNode: ThemeTreeNode) => {
  const sourceNode = draggedNode.value
  if (!sourceNode || sourceNode.id === targetNode.id || isDragReordering.value) {
    resetDragState()
    return
  }

  if (isDescendantNode(sourceNode.id, targetNode.id)) {
    resetDragState()
    return
  }

  try {
    isDragReordering.value = true
    if (sourceNode.parent_id === targetNode.parent_id) {
      await moveWithinSiblings(sourceNode, targetNode)
    } else {
      await themesApi.update(sourceNode.hashid, { parent_id: targetNode.id })
    }
    await fetchData()
    expanded.value.add(targetNode.id)
  } catch {
    toast.error(t('themes.updateFailed'))
  } finally {
    isDragReordering.value = false
    resetDragState()
  }
}

const availableParents = computed(() => {
  const excludeId = editingTheme.value?.id
  return themes.value.filter((theme) => theme.id !== excludeId)
})

const parentLabel = (theme: Theme) => hierarchyLabel(theme, themes.value)

onMounted(() => {
  fetchData()
})

defineExpose({ openCreateModal })
</script>

<template>
  <!-- Create Theme Modal -->
  <Dialog :open="showCreateModal" @close="closeCreateModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ t('themes.createTheme') }}
          </DialogTitle>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('themes.name') }} *
              </label>
              <input
                v-model="formData.name"
                type="text"
                :placeholder="t('themes.namePlaceholder')"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                @keyup.enter="createTheme"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('themes.description') }}
              </label>
              <textarea
                v-model="formData.description"
                :placeholder="t('themes.descriptionPlaceholder')"
                rows="3"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
              ></textarea>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('themes.parentTheme') }}
              </label>
              <select
                v-model="formData.parent_id"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option :value="null">{{ t('themes.noParent') }}</option>
                <option v-for="theme in themes" :key="theme.id" :value="theme.id">
                  {{ parentLabel(theme) }}
                </option>
              </select>
            </div>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button
              @click="closeCreateModal"
              :disabled="isSaving"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('themes.cancel') }}
            </button>
            <button
              @click="createTheme"
              :disabled="isSaving"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CheckIcon class="h-4 w-4" />
              {{ isSaving ? t('themes.creating') : t('themes.create') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Edit Theme Modal -->
  <Dialog :open="showEditModal" @close="closeEditModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ t('themes.editTheme') }}
          </DialogTitle>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('themes.name') }} *
              </label>
              <input
                v-model="formData.name"
                type="text"
                :placeholder="t('themes.namePlaceholder')"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                @keyup.enter="updateTheme"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('themes.description') }}
              </label>
              <textarea
                v-model="formData.description"
                :placeholder="t('themes.descriptionPlaceholder')"
                rows="3"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
              ></textarea>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('themes.parentTheme') }}
              </label>
              <select
                v-model="formData.parent_id"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option :value="null">{{ t('themes.noParent') }}</option>
                <option v-for="theme in availableParents" :key="theme.id" :value="theme.id">
                  {{ parentLabel(theme) }}
                </option>
              </select>
            </div>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button
              @click="closeEditModal"
              :disabled="isSaving"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('themes.cancel') }}
            </button>
            <button
              @click="updateTheme"
              :disabled="isSaving"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CheckIcon class="h-4 w-4" />
              {{ isSaving ? t('themes.saving') : t('themes.save') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Delete Confirmation Dialog -->
  <Dialog :open="showDeleteConfirm" @close="cancelDelete" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <div class="flex items-center gap-4 mb-4">
            <div class="flex-shrink-0 w-12 h-12 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
              <ExclamationTriangleIcon class="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <div>
              <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
                {{ t('themes.deleteConfirmTitle') }}
              </DialogTitle>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {{ t('themes.deleteConfirmMessage') }}
              </p>
            </div>
          </div>
          <p class="text-sm text-gray-700 dark:text-gray-300 mb-6 pl-16">
            <strong>{{ deletingTheme?.name }}</strong>
          </p>
          <div class="flex justify-end gap-3">
            <button
              @click="cancelDelete"
              :disabled="isDeleting"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('themes.cancel') }}
            </button>
            <button
              @click="deleteTheme"
              :disabled="isDeleting"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 rounded-md transition-colors"
            >
              <TrashIcon class="h-4 w-4" />
              {{ isDeleting ? t('themes.deleting') : t('themes.deleteConfirm') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <div class="w-full">
    <div v-if="loading" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('themes.loading') }}
    </div>

    <div v-else-if="tree.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
      <TagIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
      <p class="text-gray-500 dark:text-gray-400">
        {{ t('themes.noThemes') }}
      </p>
    </div>

    <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
      <div class="px-4 pt-3">
        <p class="text-xs text-gray-500 dark:text-gray-400">
          {{ t('themes.dragHint') }}
        </p>
      </div>
      <div class="py-2">
        <div
          class="mx-4 mb-2 rounded-md border border-dashed px-3 py-2 text-xs transition-colors"
          :class="isRootDropTarget
            ? 'border-indigo-400 bg-indigo-50 text-indigo-700 dark:border-indigo-500 dark:bg-indigo-900/30 dark:text-indigo-300'
            : 'border-gray-300 text-gray-500 dark:border-gray-600 dark:text-gray-400'"
          @dragenter="handleRootDragEnter"
          @dragover="handleRootDragOver"
          @drop="handleRootDrop"
        >
          {{ t('themes.dropToRoot') }}
        </div>
        <CourseTreeItem
          v-for="(node, idx) in tree"
          :key="node.id"
          :node="node"
          :depth="0"
          :expanded="expanded"
          show-course-id
          permission-resource="themes"
          :node-id-label="t('themes.idLabel')"
          :is-first="idx === 0"
          :is-last="idx === tree.length - 1"
          :dragged-id="draggedNode?.id ?? null"
          :drop-target-id="dropTargetId"
          @toggle="toggleExpand"
          @edit="openEditModal"
          @delete="confirmDelete"
          @move-up="(n) => moveTheme(n, 'up')"
          @move-down="(n) => moveTheme(n, 'down')"
          @drag-start="handleDragStart"
          @drag-enter="handleDragEnter"
          @drop="handleDrop"
          @drag-end="resetDragState"
        />
      </div>
    </div>
  </div>
</template>
