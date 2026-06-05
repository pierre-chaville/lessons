const HAS_TIMEZONE = /(?:Z|[+-]\d{2}:?\d{2})$/i
const HAS_TIME = /(?:T|\s)\d{1,2}:\d{2}/

export const parseApiDateTime = (value: string | null | undefined): Date | null => {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  const normalized =
    HAS_TIME.test(trimmed) && !HAS_TIMEZONE.test(trimmed)
      ? `${trimmed.replace(' ', 'T')}Z`
      : trimmed
  const parsed = new Date(normalized)
  return Number.isNaN(parsed.getTime()) ? null : parsed
}

const localDateTimeFormatter = new Intl.DateTimeFormat('en-GB', {
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZoneName: 'short',
})

export const formatApiDateTime = (
  value: string | null | undefined,
  fallback = '-',
): string => {
  const parsed = parseApiDateTime(value)
  return parsed ? localDateTimeFormatter.format(parsed) : fallback
}
