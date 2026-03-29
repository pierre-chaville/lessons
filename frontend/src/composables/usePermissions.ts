import { useAuth } from './useAuth'
import type { Role, Resource } from '@/types'

// Re-export so consumers can import Role/Resource from this module if preferred
export type { Role, Resource }

/**
 * Permission matrix — single source of truth for the frontend.
 * Mirrors the table in .cursor/rules/access.md exactly.
 * Never hardcode role names outside this file.
 */

const PERMISSIONS: Record<Resource, Record<string, Role[]>> = {
  lessons: {
    read:   ['reader', 'editor', 'publisher', 'admin'],
    create: ['publisher', 'admin'],
    update: ['editor', 'publisher', 'admin'],  // editors also need per-lesson assignment check
    delete: ['publisher', 'admin'],
  },
  courses: {
    read:   ['reader', 'editor', 'publisher', 'admin'],
    create: ['publisher', 'admin'],
    update: ['publisher', 'admin'],
    delete: ['publisher', 'admin'],
  },
  themes: {
    read:   ['reader', 'editor', 'publisher', 'admin'],
    create: ['publisher', 'admin'],
    update: ['publisher', 'admin'],
    delete: ['publisher', 'admin'],
  },
  sources: {
    read:   ['reader', 'editor', 'publisher', 'admin'],
    create: ['publisher', 'admin'],
    update: ['publisher', 'admin'],
    delete: ['publisher', 'admin'],
  },
  tasks: {
    read:   ['editor', 'publisher', 'admin'],
    create: ['editor', 'publisher', 'admin'],  // editors also need per-lesson assignment check
    cancel: ['admin'],
  },
  configuration: {
    read:   ['publisher', 'admin'],
    update: ['admin'],
  },
  users: {
    read:   ['publisher', 'admin'],
    manage: ['publisher', 'admin'],
  },
}

export function usePermissions() {
  const { role } = useAuth()

  /**
   * Returns true if the current user's role is allowed to perform `action` on `resource`.
   *
   * @example
   * const { can } = usePermissions()
   * if (can('lessons', 'delete')) { ... }
   */
  const can = (resource: Resource, action: string): boolean => {
    return PERMISSIONS[resource]?.[action]?.includes(role.value) ?? false
  }

  return { can, role }
}
