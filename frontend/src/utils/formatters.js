/**
 * Pure formatting / display helpers.
 *
 * None of these depend on Vue reactivity so they can be unit-tested
 * in isolation.
 */

/**
 * Format an array of author objects / strings into a semicolon-separated list.
 * @param {Array} authors
 * @returns {string}
 */
export function formatAuthors(authors) {
  if (!Array.isArray(authors) || !authors.length) return 'Not available'
  const names = authors
    .map((a) => {
      if (typeof a === 'string') return a
      if (a?.name) return a.name
      return ''
    })
    .filter(Boolean)
  return names.length ? names.join('; ') : 'Not available'
}

/**
 * Format an ISO date-time string for the es-ES locale.
 * @param {string|null} value
 * @returns {string}
 */
export function formatDateTime(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('es-ES', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

/**
 * Human-readable label for an article source.
 * @param {string} source
 * @returns {string}
 */
export function sourceLabel(source) {
  if (source === 'scopus') return 'SCOPUS'
  if (source === 'semantic_scholar') return 'Semantic Scholar'
  return 'Unknown'
}

/**
 * Human-readable label for an LLM provider.
 * @param {string} provider
 * @returns {string}
 */
export function providerLabel(provider) {
  if (provider === 'openai') return 'OpenAI'
  return 'OpenAI'
}

/**
 * Human-readable label for a collaborator role.
 * @param {string} role
 * @returns {string}
 */
export function roleLabel(role) {
  if (role === 'owner') return 'Owner'
  if (role === 'reviewer') return 'Reviewer'
  if (role === 'viewer') return 'Viewer'
  if (role === 'advisor') return 'Advisor'
  return role || 'Member'
}
