<script setup>
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import axios from 'axios';
import { 
  TagIcon,
  PencilIcon,
  TrashIcon,
  XMarkIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  BookOpenIcon
} from '@heroicons/vue/24/outline';
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue';

const { t } = useI18n();
const themes = ref([]);
const loading = ref(true);
const showCreateModal = ref(false);
const showEditModal = ref(false);
const showDeleteConfirm = ref(false);

// Form data
const formData = ref({
  name: ''
});

const editingTheme = ref(null);
const deletingTheme = ref(null);
const isSaving = ref(false);
const isDeleting = ref(false);

const API_URL = 'http://localhost:8000';

const fetchThemes = async () => {
  try {
    loading.value = true;
    const response = await axios.get(`${API_URL}/themes`);
    themes.value = response.data;
  } catch (error) {
    console.error('Failed to fetch themes:', error);
    alert(t('themes.fetchFailed'));
  } finally {
    loading.value = false;
  }
};

const openCreateModal = () => {
  formData.value = {
    name: ''
  };
  showCreateModal.value = true;
};

const closeCreateModal = () => {
  showCreateModal.value = false;
  formData.value = {
    name: ''
  };
};

const openEditModal = (theme) => {
  editingTheme.value = theme;
  formData.value = {
    name: theme.name
  };
  showEditModal.value = true;
};

const closeEditModal = () => {
  showEditModal.value = false;
  editingTheme.value = null;
  formData.value = {
    name: ''
  };
};

const createTheme = async () => {
  if (!formData.value.name.trim()) {
    alert(t('themes.nameRequired'));
    return;
  }

  try {
    isSaving.value = true;
    await axios.post(`${API_URL}/themes`, {
      name: formData.value.name.trim()
    });
    
    await fetchThemes();
    closeCreateModal();
  } catch (error) {
    console.error('Failed to create theme:', error);
    alert(t('themes.createFailed'));
  } finally {
    isSaving.value = false;
  }
};

const updateTheme = async () => {
  if (!formData.value.name.trim()) {
    alert(t('themes.nameRequired'));
    return;
  }

  try {
    isSaving.value = true;
    await axios.patch(`${API_URL}/themes/${editingTheme.value.id}`, {
      name: formData.value.name.trim()
    });
    
    await fetchThemes();
    closeEditModal();
  } catch (error) {
    console.error('Failed to update theme:', error);
    alert(t('themes.updateFailed'));
  } finally {
    isSaving.value = false;
  }
};

const confirmDelete = (theme) => {
  deletingTheme.value = theme;
  showDeleteConfirm.value = true;
};

const cancelDelete = () => {
  showDeleteConfirm.value = false;
  deletingTheme.value = null;
};

const deleteTheme = async () => {
  try {
    isDeleting.value = true;
    await axios.delete(`${API_URL}/themes/${deletingTheme.value.id}`);
    
    await fetchThemes();
    cancelDelete();
  } catch (error) {
    console.error('Failed to delete theme:', error);
    alert(t('themes.deleteFailed'));
  } finally {
    isDeleting.value = false;
  }
};

onMounted(() => {
  fetchThemes();
});

// Expose methods to parent
defineExpose({
  openCreateModal
});
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
    <!-- Info Section -->
    <div class="mb-6 bg-white dark:bg-gray-800 shadow-sm rounded-lg p-4 transition-colors w-full">
      <div class="flex items-center gap-2">
        <TagIcon class="h-5 w-5 text-gray-500 dark:text-gray-400" />
        <span class="text-sm font-medium text-gray-700 dark:text-gray-300">
          {{ themes.length }} {{ themes.length === 1 ? t('themes.theme') : t('themes.themes') }}
        </span>
      </div>
    </div>

    <!-- Loading State -->
    <div v-if="loading" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center text-gray-500 dark:text-gray-400 transition-colors">
      {{ t('themes.loading') }}
    </div>

    <!-- Empty State -->
    <div v-else-if="themes.length === 0" class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-8 text-center transition-colors">
      <TagIcon class="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
      <p class="text-gray-500 dark:text-gray-400">
        {{ t('themes.noThemes') }}
      </p>
    </div>

    <!-- Themes Grid -->
    <div v-else class="w-full grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <div
        v-for="theme in themes"
        :key="theme.id"
        class="bg-white dark:bg-gray-800 shadow-sm rounded-lg p-6 hover:shadow-md dark:hover:shadow-gray-900/50 transition-all border border-gray-200 dark:border-gray-700"
      >
        <div class="flex flex-col h-full">
          <div class="flex items-start gap-3 mb-3">
            <TagIcon class="h-6 w-6 text-indigo-600 dark:text-indigo-400 flex-shrink-0 mt-1" />
            <h3 class="text-lg font-semibold text-gray-900 dark:text-white line-clamp-2">
              {{ theme.name }}
            </h3>
          </div>
          
          <div class="flex-1">
            <div class="flex items-center gap-2 mb-3">
              <BookOpenIcon class="h-4 w-4 text-gray-400 dark:text-gray-500" />
              <span class="text-xs text-gray-500 dark:text-gray-400">
                {{ theme.lessons_count || 0 }} {{ t('themes.lessonsCount', theme.lessons_count || 0) }}
              </span>
            </div>
          </div>
          
          <div class="flex gap-2 pt-3 border-t border-gray-200 dark:border-gray-700">
            <button
              @click="openEditModal(theme)"
              class="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-md transition-colors"
            >
              <PencilIcon class="h-4 w-4" />
              {{ t('themes.edit') }}
            </button>
            <button
              @click="confirmDelete(theme)"
              class="flex-1 inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/30 rounded-md transition-colors"
            >
              <TrashIcon class="h-4 w-4" />
              {{ t('themes.delete') }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

