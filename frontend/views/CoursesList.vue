<script setup>
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { 
  AcademicCapIcon,
  PencilIcon,
  TrashIcon,
  XMarkIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  BookOpenIcon
} from '@heroicons/vue/24/outline';
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue';

const { t } = useI18n();
const courses = ref([]);
const loading = ref(true);
const showCreateModal = ref(false);
const showEditModal = ref(false);
const showDeleteConfirm = ref(false);

// Form data
const formData = ref({
  name: '',
  description: ''
});

const editingCourse = ref(null);
const deletingCourse = ref(null);
const isSaving = ref(false);
const isDeleting = ref(false);

const API_URL = 'http://localhost:8000';

const fetchCourses = async () => {
  try {
    loading.value = true;
    const response = await axios.get(`${API_URL}/courses`);
    courses.value = response.data;
  } catch (error) {
    console.error('Failed to fetch courses:', error);
    alert(t('courses.fetchFailed'));
  } finally {
    loading.value = false;
  }
};

const openCreateModal = () => {
  formData.value = {
    name: '',
    description: ''
  };
  showCreateModal.value = true;
};

const closeCreateModal = () => {
  showCreateModal.value = false;
  formData.value = {
    name: '',
    description: ''
  };
};

const openEditModal = (course) => {
  editingCourse.value = course;
  formData.value = {
    name: course.name,
    description: course.description || ''
  };
  showEditModal.value = true;
};

const closeEditModal = () => {
  showEditModal.value = false;
  editingCourse.value = null;
  formData.value = {
    name: '',
    description: ''
  };
};

const createCourse = async () => {
  if (!formData.value.name.trim()) {
    alert(t('courses.nameRequired'));
    return;
  }

  try {
    isSaving.value = true;
    await axios.post(`${API_URL}/courses`, {
      name: formData.value.name.trim(),
      description: formData.value.description.trim() || null
    });
    
    await fetchCourses();
    closeCreateModal();
  } catch (error) {
    console.error('Failed to create course:', error);
    alert(t('courses.createFailed'));
  } finally {
    isSaving.value = false;
  }
};

const updateCourse = async () => {
  if (!formData.value.name.trim()) {
    alert(t('courses.nameRequired'));
    return;
  }

  try {
    isSaving.value = true;
    await axios.patch(`${API_URL}/courses/${editingCourse.value.id}`, {
      name: formData.value.name.trim(),
      description: formData.value.description.trim() || null
    });
    
    await fetchCourses();
    closeEditModal();
  } catch (error) {
    console.error('Failed to update course:', error);
    alert(t('courses.updateFailed'));
  } finally {
    isSaving.value = false;
  }
};

const confirmDelete = (course) => {
  deletingCourse.value = course;
  showDeleteConfirm.value = true;
};

const cancelDelete = () => {
  showDeleteConfirm.value = false;
  deletingCourse.value = null;
};

const deleteCourse = async () => {
  try {
    isDeleting.value = true;
    await axios.delete(`${API_URL}/courses/${deletingCourse.value.id}`);
    
    await fetchCourses();
    cancelDelete();
  } catch (error) {
    console.error('Failed to delete course:', error);
    alert(t('courses.deleteFailed'));
  } finally {
    isDeleting.value = false;
  }
};

onMounted(() => {
  fetchCourses();
});

// Expose methods to parent
defineExpose({
  openCreateModal
});
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

  <div>
    <!-- Filters/Info Section (for visual consistency with lessons page) -->
    <div class="mb-6 bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 transition-colors">
      <div class="flex items-center gap-2">
        <AcademicCapIcon class="h-5 w-5 text-gray-500 dark:text-gray-400" />
        <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
          {{ courses.length }} {{ courses.length === 1 ? t('courses.course') : t('courses.courses') }}
        </span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('courses.loading') }}
    </div>

    <!-- Empty State -->
    <div v-else-if="courses.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
      <AcademicCapIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
      <p class="text-gray-500 dark:text-gray-400">
        {{ t('courses.noCourses') }}
      </p>
    </div>

    <!-- Courses Grid -->
    <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="course in courses"
        :key="course.id"
        class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 hover:shadow-md dark:hover:shadow-gray-900/50 transition-all border border-gray-200 dark:border-gray-700"
      >
      <div class="flex flex-col h-full">
        <div class="flex items-start gap-3 mb-3">
          <AcademicCapIcon class="h-6 w-6 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-1" />
          <h3 class="text-lg font-semibold text-gray-900 dark:text-white line-clamp-2">
            {{ course.name }}
          </h3>
        </div>
        
        <div class="flex-1">
          <p v-if="course.description" class="text-sm text-gray-600 dark:text-gray-400 mb-3 line-clamp-3">
            {{ course.description }}
          </p>
          
          <div class="flex items-center gap-2 mb-3">
            <BookOpenIcon class="h-4 w-4 text-gray-400 dark:text-gray-500" />
            <span class="text-xs text-gray-500 dark:text-gray-400">
              {{ course.lessons?.length || 0 }} {{ t('courses.lessonsCount', course.lessons?.length || 0) }}
            </span>
          </div>
        </div>
        
        <div class="flex gap-2 pt-3 border-t border-gray-200 dark:border-gray-700">
          <button
            @click="openEditModal(course)"
            class="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
          >
            <PencilIcon class="h-4 w-4" />
            {{ t('courses.edit') }}
          </button>
          <button
            @click="confirmDelete(course)"
            class="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
          >
            <TrashIcon class="h-4 w-4" />
            {{ t('courses.delete') }}
          </button>
        </div>
      </div>
    </div>
    </div>
  </div>
</template>

