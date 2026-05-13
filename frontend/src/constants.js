/**
 * Application-wide constants.
 *
 * Centralises every "magic string" that was previously hard-coded across
 * components so that a typo is caught at import-time instead of silently
 * producing a bug at runtime.
 */

// ── Screens ──────────────────────────────────────────────────────────
export const SCREENS = {
  PROJECTS: 'projects',
  WORKSPACE: 'workspace',
  REVIEW: 'review',
}

// ── Tabs inside the Workspace screen ─────────────────────────────────
export const TABS = {
  QUERY: 'query',
  ARTICLES: 'articles',
}

// ── Data-source types ────────────────────────────────────────────────
export const SOURCES = {
  SCOPUS: 'scopus',
  SEMANTIC: 'semantic_scholar',
}

// ── Article-source filter values ─────────────────────────────────────
export const SOURCE_FILTERS = {
  ALL: 'all',
  SCOPUS: 'scopus',
  SEMANTIC: 'semantic_scholar',
}

// ── Article-decision filter values ───────────────────────────────────
export const DECISION_FILTERS = {
  ALL: 'all',
  PENDING: 'pending',
  INCLUDED: 'included',
  EXCLUDED: 'excluded',
}

// ── User roles ───────────────────────────────────────────────────────
export const ROLES = {
  OWNER: 'owner',
  REVIEWER: 'reviewer',
  VIEWER: 'viewer',
  ADVISOR: 'advisor',
}

// ── Auth UI modes ────────────────────────────────────────────────────
export const AUTH_MODES = {
  LOGIN: 'login',
  REGISTER: 'register',
}
