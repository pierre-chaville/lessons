import type { ComposerTranslation } from 'vue-i18n'
import type { LessonVersion } from '@/api/types'
import { formatApiDateTime, parseApiDateTime } from '@/utils/dateTime'

type AuthorResolver = (createdById: string | null) => string

const formatDateTime = (iso: string | null): string => {
  return formatApiDateTime(iso, 'n/a')
}

const sessionDurationMinutes = (version: LessonVersion): number => {
  if (!version.last_edited_at) return 0
  const startedAt = parseApiDateTime(version.created_at)?.getTime()
  const endedAt = parseApiDateTime(version.last_edited_at)?.getTime()
  if (startedAt === undefined || endedAt === undefined) return 0
  const diffMinutes = (endedAt - startedAt) / 60000
  return Math.max(0, Math.ceil(diffMinutes))
}

export const useVersionLabel = (
  version: LessonVersion,
  t: ComposerTranslation,
  resolveAuthor: AuthorResolver,
): string => {
  if (version.version_source === 'pipeline') {
    return t('history.versionLabelPipeline', {
      createdAt: formatDateTime(version.created_at),
    })
  }

  if (version.version_source === 'restore') {
    return t('history.versionLabelRestore', {
      version: version.restored_from_version_number ?? '?',
      createdAt: formatDateTime(version.created_at),
      author: resolveAuthor(version.created_by_id),
    })
  }

  if (version.edit_count > 1) {
    return t('history.versionLabelHumanSession', {
      startedAt: formatDateTime(version.created_at),
      lastEditedAt: formatDateTime(version.last_edited_at),
      edits: version.edit_count,
      minutes: sessionDurationMinutes(version),
    })
  }

  return t('history.versionLabelHumanSingle', {
    createdAt: formatDateTime(version.created_at),
    author: resolveAuthor(version.created_by_id),
  })
}
