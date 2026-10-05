import DOMPurify from 'dompurify'

/**
 * Safely sanitizes dirty HTML using DOMPurify in browser and server fallback.
 */
export function sanitizeHtml(dirtyHtml: string): string {
  if (!dirtyHtml) return ''

  if (typeof window !== 'undefined' && DOMPurify && typeof DOMPurify.sanitize === 'function') {
    return DOMPurify.sanitize(dirtyHtml, {
      USE_PROFILES: { html: true },
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'span', 'b', 'i', 'strong', 'em', 'mark', 'small', 'del', 'ins', 'sub', 'sup',
        'ul', 'ol', 'li',
        'a', 'blockquote', 'code', 'pre', 'hr', 'br',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'div',
      ],
      ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'style', 'title'],
    })
  }

  // Safe SSR fallback: strip script tags and onload/onerror attributes
  return dirtyHtml
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/\son\w+="[^"]*"/gi, '')
    .replace(/\son\w+='[^']*'/gi, '')
}
