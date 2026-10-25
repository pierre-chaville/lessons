import axios from 'axios'

/**
 * Shared axios instance for all backend API calls.
 * Auth token injection is handled in composables/useAuth.ts via a request interceptor.
 * Do not create additional axios instances in components or views.
 */
export const apiBaseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const apiClient = axios.create({
  baseURL: apiBaseUrl,
  headers: { 'Content-Type': 'application/json' },
})

type AuthTokenGetter = () => Promise<string | null>
let authTokenGetter: AuthTokenGetter | null = null

/** Registered by useAuth() so non-axios callers (e.g. streaming fetch) can auth. */
export function setAuthTokenGetter(getter: AuthTokenGetter) {
  authTokenGetter = getter
}

export async function getAuthHeaders(
  extra: Record<string, string> = {},
): Promise<Record<string, string>> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...extra,
  }
  const token = authTokenGetter ? await authTokenGetter() : null
  if (token) {
    headers.Authorization = `Bearer ${token}`
  }
  return headers
}

// Global response interceptor — handles 401 and 5xx centrally.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Clerk handles redirect to sign-in automatically via its middleware.
    }
    return Promise.reject(error)
  },
)
