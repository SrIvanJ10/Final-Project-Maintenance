/**
 * Relevance helpers.
 *
 * Groups the duplicated relevance-classification logic (TD-06) into a
 * single source of truth.  Every component that needs to display or
 * reason about relevance values imports from here.
 */

/** Relevance values that count as "included". */
export const INCLUDED_RELEVANCE = ['highly_relevant', 'relevant', 'somewhat_relevant']

/** Relevance values that count as "excluded". */
export const EXCLUDED_RELEVANCE = ['not_relevant', 'duplicate']

/**
 * Human-readable tag for a relevance value.
 * @param {string} relevance
 * @returns {'Included'|'Excluded'|'Pending'}
 */
export function relevanceTag(relevance) {
  if (INCLUDED_RELEVANCE.includes(relevance)) return 'Included'
  if (EXCLUDED_RELEVANCE.includes(relevance)) return 'Excluded'
  return 'Pending'
}

/**
 * CSS class token for a relevance value.
 * @param {string} relevance
 * @returns {'included'|'excluded'|'pending'}
 */
export function relevanceClass(relevance) {
  if (INCLUDED_RELEVANCE.includes(relevance)) return 'included'
  if (EXCLUDED_RELEVANCE.includes(relevance)) return 'excluded'
  return 'pending'
}

/**
 * Short decision text shown next to a reviewer's vote.
 * @param {string} relevance
 * @returns {'Include'|'Exclude'|'Pending'}
 */
export function reviewerDecisionText(relevance) {
  if (INCLUDED_RELEVANCE.includes(relevance)) return 'Include'
  if (EXCLUDED_RELEVANCE.includes(relevance)) return 'Exclude'
  return 'Pending'
}

/**
 * Build a consensus label describing the current review state.
 * @param {object} result  – a search-result object from the API
 * @returns {string}
 */
export function consensusLabel(result) {
  const pendingVotes = result?.pending_reviewers?.length || 0
  if (EXCLUDED_RELEVANCE.includes(result?.relevance)) return 'Unanimously excluded'
  if (INCLUDED_RELEVANCE.includes(result?.relevance)) return 'Unanimously included'
  if (pendingVotes > 0) return `${pendingVotes} vote${pendingVotes === 1 ? '' : 's'} pending`
  return 'Consensus pending'
}
