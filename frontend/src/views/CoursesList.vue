<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  AcademicCapIcon,
  TrashIcon,
  CheckIcon,
  ExclamationTriangleIcon,
} from '@heroicons/vue/24/outline'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { coursesApi } from '@/api/courses'
import { useToast } from '@/composables/useToast'
import { usePermissions } from '@/composables/usePermissions'
import CourseTreeItem from '@/components/CourseTreeItem.vue'
import type { Course, CourseTreeNode } from '@/api/types'

const { t } = useI18n()
const toast = useToast()
const { can } = usePermissions()

const courses = ref<Course[]>([])
const tree = ref<CourseTreeNode[]>([])
const loading = ref(true)
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showDeleteConfirm = ref(false)

const formData = ref({ name: '', description: '', parent_id: null as number | null })

const editingCourse = ref<Course | null>(null)
const deletingCourse = ref<Course | null>(null)
const isSaving = ref(false)
const isDeleting = ref(false)

const expanded = ref<Set<number>>(new Set())

const toggleExpand = (id: number) => {
  if (expanded.value.has(id)) {
    expanded.value.delete(id)
  } else {
    expanded.value.add(id)
  }
}

const expandAll = (nodes: CourseTreeNode[]) => {
  for (const n of nodes) {
    if (n.children.length > 0) {
      expanded.value.add(n.id)
      expandAll(n.children)
    }
  }
}

const fetchData = async () => {
  try {
    loading.value = true
    const [flatList, treeData] = await Promise.all([coursesApi.list(), coursesApi.tree()])
    courses.value = flatList
    tree.value = treeData
    expandAll(treeData)
  } catch {
    toast.error(t('courses.fetchFailed'))
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

const openEditModal = (course: CourseTreeNode) => {
  editingCourse.value = course as unknown as Course
  formData.value = { name: course.name, description: course.description ?? '', parent_id: course.parent_id ?? null }
  showEditModal.value = true
}

const closeEditModal = () => {
  showEditModal.value = false
  editingCourse.value = null
  formData.value = { name: '', description: '', parent_id: null }
}

const createCourse = async () => {
  if (!formData.value.name.trim()) {
    toast.error(t('courses.nameRequired'))
    return
  }
  try {
    isSaving.value = true
    await coursesApi.create({
      name: formData.value.name.trim(),
      description: formData.value.description.trim() || null,
      parent_id: formData.value.parent_id,
    })
    await fetchData()
    closeCreateModal()
  } catch {
    toast.error(t('courses.createFailed'))
  } finally {
    isSaving.value = false
  }
}

const updateCourse = async () => {
  if (!formData.value.name.trim() || !editingCourse.value) {
    toast.error(t('courses.nameRequired'))
    return
  }
  try {
    isSaving.value = true
    await coursesApi.update(editingCourse.value.hashid, {
      name: formData.value.name.trim(),
      description: formData.value.description.trim() || null,
      parent_id: formData.value.parent_id,
    })
    await fetchData()
    closeEditModal()
  } catch {
    toast.error(t('courses.updateFailed'))
  } finally {
    isSaving.value = false
  }
}

const confirmDelete = (course: CourseTreeNode) => {
  deletingCourse.value = course as unknown as Course
  showDeleteConfirm.value = true
}

const cancelDelete = () => {
  showDeleteConfirm.value = false
  deletingCourse.value = null
}

const deleteCourse = async () => {
  if (!deletingCourse.value) return
  try {
    isDeleting.value = true
    await coursesApi.delete(deletingCourse.value.hashid)
    await fetchData()
    cancelDelete()
  } catch {
    toast.error(t('courses.deleteFailed'))
  } finally {
    isDeleting.value = false
  }
}

const availableParents = computed(() => {
  const excludeId = editingCourse.value?.id
  return courses.value.filter((c) => c.id !== excludeId)
})

onMounted(() => {
  fetchData()
})

defineExpose({ openCreateModal })
</script>

<template>
  <!-- Create Course Modal -->
  <Dialog :open="showCreateModal" @close="closeCreateModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ t('courses.createCourse') }}
          </DialogTitle>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('courses.name') }} *
              </label>
              <input
                v-model="formData.name"
                type="text"
                :placeholder="t('courses.namePlaceholder')"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                @keyup.enter="createCourse"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('courses.description') }}
              </label>
              <textarea
                v-model="formData.description"
                :placeholder="t('courses.descriptionPlaceholder')"
                rows="3"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
              ></textarea>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('courses.parentCourse') }}
              </label>
              <select
                v-model="formData.parent_id"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option :value="null">{{ t('courses.noParent') }}</option>
                <option v-for="c in courses" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button
              @click="closeCreateModal"
              :disabled="isSaving"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('courses.cancel') }}
            </button>
            <button
              @click="createCourse"
              :disabled="isSaving"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CheckIcon class="h-4 w-4" />
              {{ isSaving ? t('courses.creating') : t('courses.create') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Edit Course Modal -->
  <Dialog :open="showEditModal" @close="closeEditModal" class="relative z-50">
    <div class="fixed inset-0 bg-black/30 backdrop-blur-sm" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="mx-auto max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-xl">
        <div class="p-6">
          <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {{ t('courses.editCourse') }}
          </DialogTitle>
          <div class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('courses.name') }} *
              </label>
              <input
                v-model="formData.name"
                type="text"
                :placeholder="t('courses.namePlaceholder')"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
                @keyup.enter="updateCourse"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('courses.description') }}
              </label>
              <textarea
                v-model="formData.description"
                :placeholder="t('courses.descriptionPlaceholder')"
                rows="3"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
              ></textarea>
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                {{ t('courses.parentCourse') }}
              </label>
              <select
                v-model="formData.parent_id"
                class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-white focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              >
                <option :value="null">{{ t('courses.noParent') }}</option>
                <option v-for="c in availableParents" :key="c.id" :value="c.id">{{ c.name }}</option>
              </select>
            </div>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button
              @click="closeEditModal"
              :disabled="isSaving"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('courses.cancel') }}
            </button>
            <button
              @click="updateCourse"
              :disabled="isSaving"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 rounded-md transition-colors"
            >
              <CheckIcon class="h-4 w-4" />
              {{ isSaving ? t('courses.saving') : t('courses.save') }}
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
                {{ t('courses.deleteConfirmTitle') }}
              </DialogTitle>
              <p class="text-sm text-gray-600 dark:text-gray-400 mt-1">
                {{ t('courses.deleteConfirmMessage') }}
              </p>
            </div>
          </div>
          <p class="text-sm text-gray-700 dark:text-gray-300 mb-6 pl-16">
            <strong>{{ deletingCourse?.name }}</strong>
          </p>
          <div class="flex justify-end gap-3">
            <button
              @click="cancelDelete"
              :disabled="isDeleting"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 rounded-md transition-colors disabled:opacity-50"
            >
              {{ t('courses.cancel') }}
            </button>
            <button
              @click="deleteCourse"
              :disabled="isDeleting"
              class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 disabled:bg-red-400 rounded-md transition-colors"
            >
              <TrashIcon class="h-4 w-4" />
              {{ isDeleting ? t('courses.deleting') : t('courses.deleteConfirm') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <div class="w-full">
    <!-- Loading State -->
    <div v-if="loading" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('courses.loading') }}
    </div>

    <!-- Empty State -->
    <div v-else-if="tree.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
      <AcademicCapIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
      <p class="text-gray-500 dark:text-gray-400">
        {{ t('courses.noCourses') }}
      </p>
    </div>

    <!-- Tree View -->
    <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
      <div class="py-2">
        <CourseTreeItem
          v-for="node in tree"
          :key="node.id"
          :node="node"
          :depth="0"
          :expanded="expanded"
          @toggle="toggleExpand"
          @edit="openEditModal"
          @delete="confirmDelete"
        />
      </div>
    </div>
  </div>
</template>
