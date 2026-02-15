import { computed } from 'vue'
import { useUser, useAuth as useClerkAuth } from '@clerk/vue'
import { apiClient } from '@/api/client'
import type { Role } from '@/types'

/**
 * Module-level interceptor ID — ensures the auth interceptor is registered only once
 * regardless of how many components call useAuth().
 */
let interceptorRegistered = false

/**
 * Wraps Clerk's auth state and wires the Authorization header into the shared apiClient.
 * Call this once in App.vue (or a top-level layout) to register the interceptor,
 * then call it freely in any component just to read `role` / `isSignedIn`.
 */
export function useAuth() {
  const { user, isLoaded, isSignedIn } = useUser()
  const { getToken } = useClerkAuth()

  const role = computed<Role>(
    () => (user.value?.publicMetadata?.role as Role) ?? 'reader',
  )

  if (!interceptorRegistered) {
    interceptorRegistered = true
    apiClient.interceptors.request.use(async (config) => {
      const token = await getToken()
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })
  }

  return { user, isLoaded, isSignedIn, role }
}
