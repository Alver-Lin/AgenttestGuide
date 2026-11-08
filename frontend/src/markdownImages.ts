/** Keep Markdown portable on disk; only the rendered URL points to the local API. */
export function markdownImageUrl(noteId: string, source: string) {
  const value = source.trim()
  if (!value || /^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(value) || value.startsWith('/api/'))
    return source
  return `/api/notes/${encodeURIComponent(noteId)}/image?path=${encodeURIComponent(value)}`
}
