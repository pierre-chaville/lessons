import { apiClient } from './client'

export interface ClerkUser {
  id: string
  first_name: string | null
  last_name: string | null
  email: string | null
  role: string | null
  image_url: string | null
  created_at: number | null
  last_sign_in_at: number | null
}

export interface UserCreate {
  first_name: string
  last_name: string
  email: string
  password: string
  role: string
}

export interface UserInvite {
  email: string
  role: string
}

export interface InvitationResponse {
  id: string
  email_address: string
  status: string
  role: string | null
  created_at: number | null
}

export interface UserUpdateRole {
  role: string
}

export const usersApi = {
  list: () => apiClient.get<ClerkUser[]>('/users').then((r) => r.data),

  create: (data: UserCreate) =>
    apiClient.post<ClerkUser>('/users', data).then((r) => r.data),

  invite: (data: UserInvite) =>
    apiClient.post<InvitationResponse>('/users/invite', data).then((r) => r.data),

  listInvitations: () =>
    apiClient.get<InvitationResponse[]>('/users/invitations').then((r) => r.data),

  revokeInvitation: (invitationId: string) =>
    apiClient.delete(`/users/invitations/${invitationId}`),

  updateRole: (userId: string, data: UserUpdateRole) =>
    apiClient.patch<ClerkUser>(`/users/${userId}/role`, data).then((r) => r.data),

  delete: (userId: string) => apiClient.delete(`/users/${userId}`),
}
