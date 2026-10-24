type NamedNode = {
  id: number
  name: string
  parent_id?: number | null
}

/** Build a "Parent / Child" label from a flat list that includes parent ids. */
export function hierarchyLabel(item: NamedNode, items: NamedNode[]): string {
  const byId = new Map(items.map((entry) => [entry.id, entry]))
  const names: string[] = []
  const seen = new Set<number>()
  let current: NamedNode | undefined = item
  while (current && !seen.has(current.id)) {
    seen.add(current.id)
    names.unshift(current.name)
    current = current.parent_id != null ? byId.get(current.parent_id) : undefined
  }
  return names.join(' / ')
}
