/**
 * Shared TypeScript types used across composables, views, and components.
 */

/** The four user roles defined in .cursor/rules/access.md */
export type Role = 'reader' | 'editor' | 'publisher' | 'admin'

/** Resources covered by the RBAC permission matrix */
export type Resource =
  | 'lessons'
  | 'courses'
  | 'themes'
  | 'sources'
  | 'tasks'
  | 'configuration'
  | 'users'
