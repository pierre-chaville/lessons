import { apiClient } from './client'
import type { AuditLogRow } from './types'

export const auditApi = {
  query: (params?: {
    actor_id?: string
    action?: string
    entity_type?: string
    entity_id?: string
    occurred_after?: string
    occurred_before?: string
    limit?: number
  }) => apiClient.get<AuditLogRow[]>('/audit-log', { params }).then((r) => r.data),
}

