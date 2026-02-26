<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  PencilIcon,
  TrashIcon,
  PlusIcon,
  XMarkIcon,
  EnvelopeIcon,
  UserPlusIcon,
} from '@heroicons/vue/24/outline'
import { Dialog, DialogPanel, DialogTitle } from '@headlessui/vue'
import { usersApi } from '@/api/users'
import type { ClerkUser, InvitationResponse } from '@/api/users'
import { useToast } from '@/composables/useToast'
import { useAuth } from '@/composables/useAuth'

const { t } = useI18n()
const toast = useToast()
const { role: currentUserRole } = useAuth()

const isAdmin = computed(() => currentUserRole.value === 'admin')

const users = ref<ClerkUser[]>([])
const invitations = ref<InvitationResponse[]>([])
const loading = ref(false)
const error = ref('')

// Add user modal (invite / create tabs)
const showAddModal = ref(false)
const addMode = ref<'invite' | 'create'>('invite')
const creating = ref(false)
const inviting = ref(false)
const createForm = ref({
  first_name: '',
  last_name: '',
  email: '',
  password: '',
  role: 'reader',
})
const inviteForm = ref({
  first_name: '',
  last_name: '',
  email: '',
  role: 'reader',
})

// Edit role modal
const showEditModal = ref(false)
const saving = ref(false)
const editingUser = ref<ClerkUser | null>(null)
const editRole = ref('')

// Delete confirmation
const showDeleteModal = ref(false)
const deletingUser = ref<ClerkUser | null>(null)
const deleting = ref(false)

const ALL_ROLES = ['admin', 'publisher', 'editor', 'reader']
/** Publishers can't assign the admin role */
const availableRoles = computed(() =>
  isAdmin.value ? ALL_ROLES : ALL_ROLES.filter((r) => r !== 'admin'),
)

/** Whether the current user can edit/delete a given user */
const canManageUser = (user: ClerkUser) => {
  // Publishers cannot modify/delete admin users
  if (!isAdmin.value && user.role === 'admin') return false
  return true
}

const fetchUsers = async () => {
  loading.value = true
  error.value = ''
  try {
    const [usersList, invitationsList] = await Promise.all([
      usersApi.list(),
      usersApi.listInvitations(),
    ])
    users.value = usersList
    invitations.value = invitationsList
  } catch (e: any) {
    error.value = e?.response?.data?.detail || t('users.loadFailed')
  } finally {
    loading.value = false
  }
}

onMounted(fetchUsers)

// ── Add user (invite / create) ────────────────────────────────────────────────

const openAddModal = () => {
  addMode.value = 'invite'
  createForm.value = { first_name: '', last_name: '', email: '', password: '', role: 'reader' }
  inviteForm.value = { first_name: '', last_name: '', email: '', role: 'reader' }
  showAddModal.value = true
}

const handleInvite = async () => {
  inviting.value = true
  try {
    await usersApi.invite(inviteForm.value)
    toast.success(t('users.inviteSuccess'))
    showAddModal.value = false
    await fetchUsers()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail) || t('users.inviteFailed')
    toast.error(msg)
  } finally {
    inviting.value = false
  }
}

const handleCreate = async () => {
  creating.value = true
  try {
    await usersApi.create(createForm.value)
    toast.success(t('users.createSuccess'))
    showAddModal.value = false
    await fetchUsers()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    const msg = typeof detail === 'string' ? detail : JSON.stringify(detail) || t('users.createFailed')
    toast.error(msg)
  } finally {
    creating.value = false
  }
}

// ── Edit role ─────────────────────────────────────────────────────────────────

const openEditModal = (user: ClerkUser) => {
  editingUser.value = user
  editRole.value = user.role || 'reader'
  showEditModal.value = true
}

const handleUpdateRole = async () => {
  if (!editingUser.value) return
  saving.value = true
  try {
    await usersApi.updateRole(editingUser.value.id, { role: editRole.value })
    toast.success(t('users.updateSuccess'))
    showEditModal.value = false
    await fetchUsers()
  } catch (e: any) {
    toast.error(t('users.updateFailed'))
  } finally {
    saving.value = false
  }
}

// ── Delete ────────────────────────────────────────────────────────────────────

const openDeleteModal = (user: ClerkUser) => {
  deletingUser.value = user
  showDeleteModal.value = true
}

const handleDelete = async () => {
  if (!deletingUser.value) return
  deleting.value = true
  try {
    await usersApi.delete(deletingUser.value.id)
    toast.success(t('users.deleteSuccess'))
    showDeleteModal.value = false
    await fetchUsers()
  } catch (e: any) {
    toast.error(t('users.deleteFailed'))
  } finally {
    deleting.value = false
  }
}

// ── Revoke invitation ────────────────────────────────────────────────────
const showRevokeModal = ref(false)
const revokingInvitation = ref<InvitationResponse | null>(null)
const revoking = ref(false)

const openRevokeModal = (invitation: InvitationResponse) => {
  revokingInvitation.value = invitation
  showRevokeModal.value = true
}

const handleRevoke = async () => {
  if (!revokingInvitation.value) return
  revoking.value = true
  try {
    await usersApi.revokeInvitation(revokingInvitation.value.id)
    toast.success(t('users.revokeSuccess'))
    showRevokeModal.value = false
    await fetchUsers()
  } catch (e: any) {
    toast.error(t('users.revokeFailed'))
  } finally {
    revoking.value = false
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const formatDate = (timestamp: number | null) => {
  if (!timestamp) return t('users.never')
  return new Date(timestamp).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

const getRoleBadgeClass = (role: string | null) => {
  switch (role) {
    case 'admin':
      return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
    case 'publisher':
      return 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400'
    case 'editor':
      return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400'
    case 'reader':
    default:
      return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
  }
}

const userCount = computed(() => users.value.length)

defineExpose({ openAddModal, userCount })
</script>

<template>
  <!-- Loading -->
  <div v-if="loading" class="text-center py-12">
    <p class="text-gray-500 dark:text-gray-400">{{ t('users.loading') }}</p>
  </div>

  <!-- Error -->
  <div v-else-if="error" class="text-center py-12">
    <p class="text-red-500 dark:text-red-400">{{ error }}</p>
  </div>

  <!-- Users Table -->
  <div v-else>
    <div v-if="users.length === 0" class="text-center py-12">
      <p class="text-gray-500 dark:text-gray-400">{{ t('users.noUsers') }}</p>
    </div>

    <div v-else class="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
      <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
        <thead class="bg-gray-50 dark:bg-gray-900">
          <tr>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {{ t('users.firstName') }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {{ t('users.lastName') }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {{ t('users.email') }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {{ t('users.role') }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {{ t('users.createdAt') }}
            </th>
            <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {{ t('users.lastSignIn') }}
            </th>
            <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
              {{ t('users.actions') }}
            </th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
          <tr
            v-for="user in users"
            :key="user.id"
            class="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
          >
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">
              <div class="flex items-center gap-3">
                <img
                  v-if="user.image_url"
                  :src="user.image_url"
                  class="h-8 w-8 rounded-full"
                  alt=""
                />
                <div v-else class="h-8 w-8 rounded-full bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
                  <span class="text-xs font-medium text-indigo-600 dark:text-indigo-400">
                    {{ (user.first_name || '?')[0].toUpperCase() }}
                  </span>
                </div>
                {{ user.first_name || '—' }}
              </div>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">
              {{ user.last_name || '—' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
              {{ user.email || '—' }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap">
              <span
                :class="[
                  'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
                  getRoleBadgeClass(user.role)
                ]"
              >
                {{ user.role ? t(`users.roles.${user.role}`) : '—' }}
              </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
              {{ formatDate(user.created_at) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
              {{ formatDate(user.last_sign_in_at) }}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right">
              <div v-if="canManageUser(user)" class="flex items-center justify-end gap-2">
                <button
                  @click="openEditModal(user)"
                  class="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400 hover:text-indigo-600 dark:hover:text-indigo-400 transition-colors"
                  :title="t('users.editRole')"
                >
                  <PencilIcon class="h-4 w-4" />
                </button>
                <button
                  @click="openDeleteModal(user)"
                  class="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                  :title="t('users.deleteUser')"
                >
                  <TrashIcon class="h-4 w-4" />
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <!-- Pending Invitations -->
    <div v-if="invitations.length > 0" class="mt-8">
      <h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-3">
        {{ t('users.pendingInvitations') }}
        <span class="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
          {{ invitations.length }}
        </span>
      </h3>
      <div class="bg-white dark:bg-gray-800 shadow-sm rounded-lg overflow-hidden transition-colors">
        <table class="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
          <thead class="bg-gray-50 dark:bg-gray-900">
            <tr>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                {{ t('users.email') }}
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                {{ t('users.firstName') }}
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                {{ t('users.lastName') }}
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                {{ t('users.role') }}
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                {{ t('users.status') }}
              </th>
              <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                {{ t('users.createdAt') }}
              </th>
              <th class="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                {{ t('users.actions') }}
              </th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
            <tr
              v-for="inv in invitations"
              :key="inv.id"
              class="hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
            >
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">
                <div class="flex items-center gap-3">
                  <div class="h-8 w-8 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                    <EnvelopeIcon class="h-4 w-4 text-amber-600 dark:text-amber-400" />
                  </div>
                  {{ inv.email_address }}
                </div>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">
                {{ inv.first_name || '—' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-gray-100">
                {{ inv.last_name || '—' }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span
                  :class="[
                    'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
                    getRoleBadgeClass(inv.role)
                  ]"
                >
                  {{ inv.role ? t(`users.roles.${inv.role}`) : '—' }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap">
                <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400">
                  {{ t('users.pending') }}
                </span>
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                {{ formatDate(inv.created_at) }}
              </td>
              <td class="px-6 py-4 whitespace-nowrap text-right">
                <button
                  @click="openRevokeModal(inv)"
                  class="p-1.5 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                  :title="t('users.revokeInvite')"
                >
                  <XMarkIcon class="h-4 w-4" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- Revoke Invitation Confirmation Modal -->
  <Dialog :open="showRevokeModal" @close="showRevokeModal = false" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="w-full max-w-sm bg-white dark:bg-gray-800 rounded-xl shadow-2xl">
        <div class="p-6">
          <div class="flex items-center justify-between mb-4">
            <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ t('users.revokeInvite') }}
            </DialogTitle>
            <button @click="showRevokeModal = false" class="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300">
              <XMarkIcon class="h-5 w-5" />
            </button>
          </div>

          <div v-if="revokingInvitation" class="mb-2">
            <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
              {{ revokingInvitation.email_address }}
            </p>
          </div>

          <p class="text-sm text-gray-600 dark:text-gray-400 mb-6">
            {{ t('users.confirmRevoke') }}
          </p>

          <div class="flex justify-end gap-3">
            <button
              @click="showRevokeModal = false"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
            >
              {{ t('users.cancel') }}
            </button>
            <button
              @click="handleRevoke"
              :disabled="revoking"
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md disabled:opacity-50 transition-colors"
            >
              {{ revoking ? '...' : t('users.revokeInvite') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Add User Modal (Invite / Create tabs) -->
  <Dialog :open="showAddModal" @close="showAddModal = false" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="w-full max-w-md bg-white dark:bg-gray-800 rounded-xl shadow-2xl">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ t('users.addUser') }}
            </DialogTitle>
            <button @click="showAddModal = false" class="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300">
              <XMarkIcon class="h-5 w-5" />
            </button>
          </div>

          <!-- Tabs -->
          <div class="flex border-b border-gray-200 dark:border-gray-700 mb-5">
            <button
              @click="addMode = 'invite'"
              :class="[
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
                addMode === 'invite'
                  ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              ]"
            >
              <EnvelopeIcon class="h-4 w-4" />
              {{ t('users.inviteUser') }}
            </button>
            <button
              @click="addMode = 'create'"
              :class="[
                'flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px',
                addMode === 'create'
                  ? 'border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400'
                  : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
              ]"
            >
              <UserPlusIcon class="h-4 w-4" />
              {{ t('users.createUser') }}
            </button>
          </div>

          <!-- Invite Form -->
          <form v-if="addMode === 'invite'" @submit.prevent="handleInvite" class="space-y-4">
            <p class="text-sm text-gray-500 dark:text-gray-400">
              {{ t('users.inviteDesc') }}
            </p>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.firstName') }}</label>
              <input
                v-model="inviteForm.first_name"
                type="text"
                required
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.lastName') }}</label>
              <input
                v-model="inviteForm.last_name"
                type="text"
                required
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.email') }}</label>
              <input
                v-model="inviteForm.email"
                type="email"
                required
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.role') }}</label>
              <select
                v-model="inviteForm.role"
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option v-for="role in availableRoles" :key="role" :value="role">
                  {{ t(`users.roles.${role}`) }}
                </option>
              </select>
            </div>

            <div class="flex justify-end gap-3 pt-4">
              <button
                type="button"
                @click="showAddModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                {{ t('users.cancel') }}
              </button>
              <button
                type="submit"
                :disabled="inviting"
                class="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md disabled:opacity-50 transition-colors"
              >
                <EnvelopeIcon class="h-4 w-4" />
                {{ inviting ? t('users.inviting') : t('users.sendInvite') }}
              </button>
            </div>
          </form>

          <!-- Create Form -->
          <form v-else @submit.prevent="handleCreate" class="space-y-4">
            <p class="text-sm text-gray-500 dark:text-gray-400">
              {{ t('users.createDesc') }}
            </p>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.firstName') }}</label>
              <input
                v-model="createForm.first_name"
                type="text"
                required
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.lastName') }}</label>
              <input
                v-model="createForm.last_name"
                type="text"
                required
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.email') }}</label>
              <input
                v-model="createForm.email"
                type="email"
                required
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.password') }}</label>
              <input
                v-model="createForm.password"
                type="password"
                required
                minlength="8"
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              />
            </div>
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.role') }}</label>
              <select
                v-model="createForm.role"
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option v-for="role in availableRoles" :key="role" :value="role">
                  {{ t(`users.roles.${role}`) }}
                </option>
              </select>
            </div>

            <div class="flex justify-end gap-3 pt-4">
              <button
                type="button"
                @click="showAddModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                {{ t('users.cancel') }}
              </button>
              <button
                type="submit"
                :disabled="creating"
                class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md disabled:opacity-50 transition-colors"
              >
                {{ creating ? t('users.creating') : t('users.create') }}
              </button>
            </div>
          </form>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Edit Role Modal -->
  <Dialog :open="showEditModal" @close="showEditModal = false" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="w-full max-w-sm bg-white dark:bg-gray-800 rounded-xl shadow-2xl">
        <div class="p-6">
          <div class="flex items-center justify-between mb-6">
            <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ t('users.editRole') }}
            </DialogTitle>
            <button @click="showEditModal = false" class="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300">
              <XMarkIcon class="h-5 w-5" />
            </button>
          </div>

          <div v-if="editingUser" class="mb-4">
            <p class="text-sm text-gray-600 dark:text-gray-400">
              {{ editingUser.first_name }} {{ editingUser.last_name }}
              <span class="text-gray-400 dark:text-gray-500">({{ editingUser.email }})</span>
            </p>
          </div>

          <form @submit.prevent="handleUpdateRole" class="space-y-4">
            <div>
              <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{{ t('users.role') }}</label>
              <select
                v-model="editRole"
                class="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                <option v-for="role in availableRoles" :key="role" :value="role">
                  {{ t(`users.roles.${role}`) }}
                </option>
              </select>
            </div>

            <div class="flex justify-end gap-3 pt-4">
              <button
                type="button"
                @click="showEditModal = false"
                class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
              >
                {{ t('users.cancel') }}
              </button>
              <button
                type="submit"
                :disabled="saving"
                class="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-md disabled:opacity-50 transition-colors"
              >
                {{ saving ? t('users.saving') : t('users.save') }}
              </button>
            </div>
          </form>
        </div>
      </DialogPanel>
    </div>
  </Dialog>

  <!-- Delete Confirmation Modal -->
  <Dialog :open="showDeleteModal" @close="showDeleteModal = false" class="relative z-50">
    <div class="fixed inset-0 bg-black/30" aria-hidden="true" />
    <div class="fixed inset-0 flex items-center justify-center p-4">
      <DialogPanel class="w-full max-w-sm bg-white dark:bg-gray-800 rounded-xl shadow-2xl">
        <div class="p-6">
          <div class="flex items-center justify-between mb-4">
            <DialogTitle class="text-lg font-semibold text-gray-900 dark:text-white">
              {{ t('users.deleteUser') }}
            </DialogTitle>
            <button @click="showDeleteModal = false" class="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300">
              <XMarkIcon class="h-5 w-5" />
            </button>
          </div>

          <div v-if="deletingUser" class="mb-2">
            <p class="text-sm font-medium text-gray-900 dark:text-gray-100">
              {{ deletingUser.first_name }} {{ deletingUser.last_name }}
            </p>
            <p class="text-sm text-gray-500 dark:text-gray-400">{{ deletingUser.email }}</p>
          </div>

          <p class="text-sm text-gray-600 dark:text-gray-400 mb-6">
            {{ t('users.confirmDelete') }}
          </p>

          <div class="flex justify-end gap-3">
            <button
              @click="showDeleteModal = false"
              class="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
            >
              {{ t('users.cancel') }}
            </button>
            <button
              @click="handleDelete"
              :disabled="deleting"
              class="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md disabled:opacity-50 transition-colors"
            >
              {{ deleting ? '...' : t('users.deleteUser') }}
            </button>
          </div>
        </div>
      </DialogPanel>
    </div>
  </Dialog>
</template>
