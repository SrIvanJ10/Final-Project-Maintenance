const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').trim()

function endpoint(path) {
  if (path.startsWith('http')) return path
  if (!API_BASE_URL) return path
  return `${API_BASE_URL}${path}`
}

function toQuery(params = {}) {
  const query = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    query.set(key, String(value))
  })
  const raw = query.toString()
  return raw ? `?${raw}` : ''
}

function unwrapList(payload) {
  if (Array.isArray(payload)) return payload
  if (payload?.results && Array.isArray(payload.results)) return payload.results
  return []
}

function getCookie(name) {
  const value = `; ${document.cookie}`
  const parts = value.split(`; ${name}=`)
  if (parts.length === 2) return parts.pop().split(';').shift()
  return null
}

export async function ensureCsrfToken() {
  const current = getCookie('csrftoken')
  if (current) return current

  const response = await fetch(endpoint('/api/v1/auth/csrf/'), {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to get CSRF token')
  }

  const payload = await response.json()
  return payload.csrfToken || getCookie('csrftoken')
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = { ...(options.headers || {}) }

  if (method !== 'GET' && method !== 'HEAD') {
    const token = await ensureCsrfToken()
    headers['X-CSRFToken'] = token
  }

  if (options.body && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json'
  }

  const response = await fetch(endpoint(path), {
    ...options,
    headers,
    credentials: 'include',
  })

  const contentType = response.headers.get('content-type') || ''
  const raw = await response.text()
  const isJson = contentType.includes('application/json')
  const data = isJson && raw ? JSON.parse(raw) : null

  if (!response.ok) {
    if (data?.error || data?.detail) {
      throw new Error(data.error || data.detail)
    }
    if (!isJson) {
      const snippet = raw ? raw.replace(/\s+/g, ' ').slice(0, 140) : ''
      throw new Error(
        `API ${method} ${path} returned non-JSON (status ${response.status}). ${snippet}`,
      )
    }
    throw new Error(`API ${method} ${path} failed (status ${response.status})`)
  }

  return data
}

export function getCurrentUser() {
  return request('/api/v1/auth/me/')
}

export function login(username, password) {
  return request('/api/v1/auth/login/', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })
}

export function register(username, email, password) {
  return request('/api/v1/auth/register/', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  })
}

export function logout() {
  return request('/api/v1/auth/logout/', {
    method: 'POST',
  })
}

export function getProjects() {
  return request('/api/v1/projects/').then(unwrapList)
}

export function createProject(projectData) {
  return request('/api/v1/projects/', {
    method: 'POST',
    body: JSON.stringify(projectData),
  })
}

export function updateProject(projectId, projectData) {
  return request(`/api/v1/projects/${projectId}/`, {
    method: 'PATCH',
    body: JSON.stringify(projectData),
  })
}

export function deleteProject(projectId) {
  return request(`/api/v1/projects/${projectId}/`, {
    method: 'DELETE',
  })
}

export function getProjectStatistics(projectId) {
  return request(`/api/v1/projects/${projectId}/statistics/`)
}

export function addProjectCollaborator(projectId, payload) {
  return request(`/api/v1/projects/${projectId}/add_collaborator/`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function startProjectReview(projectId) {
  return request(`/api/v1/projects/${projectId}/start_review/`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function lookupUsers(query) {
  return request(`/api/v1/users/lookup/${toQuery({ q: query })}`).then((payload) => payload?.results || [])
}

export function listSearchCriteria(params = {}) {
  return request(`/api/v1/search-criteria/${toQuery(params)}`).then(unwrapList)
}

export function createSearchCriteria(data) {
  return request('/api/v1/search-criteria/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateSearchCriteria(id, data) {
  return request(`/api/v1/search-criteria/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteSearchCriteria(id) {
  return request(`/api/v1/search-criteria/${id}/`, {
    method: 'DELETE',
  })
}

export function executeSearch(id) {
  return request(`/api/v1/search-criteria/${id}/execute_search/`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export async function importScopusResults(criteriaId, file, scopusQuery = '') {
  const token = await ensureCsrfToken()
  const form = new FormData()
  form.append('file', file)
  if (scopusQuery) form.append('scopus_query', scopusQuery)

  const response = await fetch(endpoint(`/api/v1/search-criteria/${criteriaId}/import_scopus_results/`), {
    method: 'POST',
    headers: { 'X-CSRFToken': token },
    credentials: 'include',
    body: form,
  })

  const raw = await response.text()
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') && raw ? JSON.parse(raw) : null
  if (!response.ok) {
    throw new Error(data?.error || `Scopus import failed (status ${response.status})`)
  }
  return data
}

export function listSearches(params = {}) {
  return request(`/api/v1/searches/${toQuery(params)}`).then(unwrapList)
}

export function listSearchResults(params = {}) {
  return request(`/api/v1/search-results/${toQuery(params)}`).then(unwrapList)
}

export function assessRelevance(id, relevance, notes = '') {
  return request(`/api/v1/search-results/${id}/assess_relevance/`, {
    method: 'POST',
    body: JSON.stringify({ relevance, notes }),
  })
}

export function suggestWithAI(searchResultId) {
  return request(`/api/v1/search-results/${searchResultId}/suggest_with_ai/`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
}

export function listArticles(params = {}) {
  return request(`/api/v1/articles/${toQuery(params)}`).then(unwrapList)
}

export function listArticleDiscussions(params = {}) {
  return request(`/api/v1/article-discussions/${toQuery(params)}`).then(unwrapList)
}

export function createArticleDiscussionMessage(data) {
  return request('/api/v1/article-discussions/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function listWorkflowPhases(params = {}) {
  return request(`/api/v1/workflow-phases/${toQuery(params)}`).then(unwrapList)
}

export function createWorkflowPhase(data) {
  return request('/api/v1/workflow-phases/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateWorkflowPhase(id, data) {
  return request(`/api/v1/workflow-phases/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteWorkflowPhase(id) {
  return request(`/api/v1/workflow-phases/${id}/`, {
    method: 'DELETE',
  })
}

export function listScreeningTasks(params = {}) {
  return request(`/api/v1/screening-tasks/${toQuery(params)}`).then(unwrapList)
}

export function createScreeningTask(data) {
  return request('/api/v1/screening-tasks/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateScreeningTask(id, data) {
  return request(`/api/v1/screening-tasks/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteScreeningTask(id) {
  return request(`/api/v1/screening-tasks/${id}/`, {
    method: 'DELETE',
  })
}

export function listExtractionTemplates(params = {}) {
  return request(`/api/v1/extraction-templates/${toQuery(params)}`).then(unwrapList)
}

export function createExtractionTemplate(data) {
  return request('/api/v1/extraction-templates/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateExtractionTemplate(id, data) {
  return request(`/api/v1/extraction-templates/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteExtractionTemplate(id) {
  return request(`/api/v1/extraction-templates/${id}/`, {
    method: 'DELETE',
  })
}

export function listExtractedData(params = {}) {
  return request(`/api/v1/extracted-data/${toQuery(params)}`).then(unwrapList)
}

export function createExtractedData(data) {
  return request('/api/v1/extracted-data/', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateExtractedData(id, data) {
  return request(`/api/v1/extracted-data/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}

export function deleteExtractedData(id) {
  return request(`/api/v1/extracted-data/${id}/`, {
    method: 'DELETE',
  })
}
