import axios from 'axios'

/**
 * Shared axios instance for all backend API calls.
 * Auth token injection is handled in composables/useAuth.ts via a request interceptor.
 * Do not create additional axios instances in components or views.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  headers: { 'Content-Type': 'application/json' },
})

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
