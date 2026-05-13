/**
 * CSV generation and download helpers.
 *
 * Decoupled from any Vue component so the logic can be tested and
 * reused independently (TD-08).
 */

import { formatAuthors, sourceLabel } from './formatters.js'

/**
 * Convert an array of search-result objects to a CSV string.
 * @param {Array} results – search-result objects with nested `article`
 * @returns {string} CSV text
 */
export function generateResultsCsv(results) {
  if (!results.length) return ''

  const rows = results.map((result, idx) => {
    const article = result.article || {}
    return {
      rank: result.rank || idx + 1,
      relevance: result.relevance,
      source: sourceLabel(article.article_source),
      title: article.title || '',
      authors: formatAuthors(article.authors),
      year: article.publication_year || '',
      venue: article.publication_venue || '',
      doi_or_url: article.source_url || '',
      notes: result.reviewer_notes || '',
    }
  })

  const headers = Object.keys(rows[0])
  return [
    headers.join(','),
    ...rows.map((row) =>
      headers
        .map((key) => {
          const value = String(row[key] ?? '')
          const escaped = value.replaceAll('"', '""')
          return `"${escaped}"`
        })
        .join(','),
    ),
  ].join('\n')
}

/**
 * Trigger a browser download of a CSV string.
 * @param {string} csvString
 * @param {string} filename
 */
export function downloadCsv(csvString, filename) {
  const blob = new Blob([csvString], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
