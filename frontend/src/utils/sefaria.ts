/** Sefaria page of a reference or book title (e.g. "Berakhot 2a", "Tanya"). */
export function sefariaUrl(ref: string): string {
  return `https://www.sefaria.org/${encodeURIComponent(ref.trim().replace(/ /g, '_'))}`
}
