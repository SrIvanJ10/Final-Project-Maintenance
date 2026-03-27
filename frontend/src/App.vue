<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import * as api from './lib/api'

const user = ref(null)
const status = ref('Checking session...')
const msg = ref('')
const err = ref('')
const aiSuggestion = ref(null)
const discussionMessages = ref([])
let flashTimeoutId = null

const auth = reactive({
  mode: 'login',
  username: '',
  email: '',
  password: '',
})

const ui = reactive({
  screen: 'projects', // projects | workspace | review
  activeTab: 'query', // query | articles
  projectModalOpen: false,
  selectedProjectId: null,
  sourceType: 'scopus', // scopus | semantic_scholar
  articleSourceFilter: 'all', // all | scopus | semantic_scholar
  articleDecisionFilter: 'all', // all | pending | included | excluded
  reviewIndex: 0,
  loading: false,
  aiLoading: false,
  discussionLoading: false,
  discussionSending: false,
})

const drafts = reactive({
  projectName: '',
  projectDescription: '',
  projectInclusionCriteriaEdit: '',
  collaboratorQuery: '',
  collaboratorRole: 'reviewer',
  discussionMessage: '',
  scopusQuery: '',
  semanticKeywords: '',
})

const lists = reactive({
  projects: [],
  criteria: [],
  searches: [],
  results: [],
  tasks: [],
})

const INCLUDED_RELEVANCE = ['highly_relevant', 'relevant', 'somewhat_relevant']
const EXCLUDED_RELEVANCE = ['not_relevant', 'duplicate']

const selectedProject = computed(() => lists.projects.find((p) => p.id === ui.selectedProjectId) || null)

const projectCriteria = computed(() => {
  if (!selectedProject.value) return []
  return lists.criteria.filter((c) => c.project === selectedProject.value.id)
})

const sourceCriteria = computed(() => {
  return projectCriteria.value.find((c) => c.source_type === ui.sourceType) || null
})

const projectSearches = computed(() => {
  const criteriaIds = new Set(projectCriteria.value.map((c) => c.id))
  return lists.searches.filter((s) => criteriaIds.has(s.criteria))
})

const projectResults = computed(() => {
  const searchIds = new Set(projectSearches.value.map((s) => s.id))
  if (!searchIds.size) return []
  return lists.results.filter((r) => searchIds.has(r.search))
})

const currentResults = computed(() => {
  const sourceFilter = ui.articleSourceFilter
  const decisionFilter = ui.articleDecisionFilter
  const searchOrder = new Map(projectSearches.value.map((s, idx) => [s.id, idx]))

  return projectResults.value
    .filter((r) => {
      if (sourceFilter === 'all') return true
      return r.article?.article_source === sourceFilter
    })
    .filter((r) => {
      if (decisionFilter === 'all') return true
      if (decisionFilter === 'pending') return r.relevance === 'not_reviewed'
      if (decisionFilter === 'included') return INCLUDED_RELEVANCE.includes(r.relevance)
      if (decisionFilter === 'excluded') return EXCLUDED_RELEVANCE.includes(r.relevance)
      return true
    })
    .slice()
    .sort((a, b) => {
      const searchCmp = (searchOrder.get(a.search) ?? 999999) - (searchOrder.get(b.search) ?? 999999)
      if (searchCmp !== 0) return searchCmp
      return (a.rank || 0) - (b.rank || 0)
    })
})

function parseTaskAssignments(task) {
  if (!task?.notes) return []
  try {
    const payload = JSON.parse(task.notes)
    return Array.isArray(payload?.assigned_result_ids) ? payload.assigned_result_ids : []
  } catch {
    return []
  }
}

const projectTasks = computed(() => {
  const searchIds = new Set(projectSearches.value.map((s) => s.id))
  return lists.tasks.filter((task) => searchIds.has(task.search))
})

const currentUserProjectTasks = computed(() => {
  return projectTasks.value.filter((task) => task.reviewer?.id === user.value?.id)
})

const reviewResults = computed(() => {
  const assignedIds = new Set(currentUserProjectTasks.value.flatMap(parseTaskAssignments))
  const hasDistributedTasks = projectTasks.value.some((task) => parseTaskAssignments(task).length > 0)

  if (!hasDistributedTasks) return currentResults.value
  return currentResults.value.filter((result) => assignedIds.has(result.id))
})

const totalCount = computed(() => projectResults.value.length)
const includedCount = computed(() => projectResults.value.filter((r) => INCLUDED_RELEVANCE.includes(r.relevance)).length)
const excludedCount = computed(() => projectResults.value.filter((r) => EXCLUDED_RELEVANCE.includes(r.relevance)).length)
const pendingCount = computed(() => totalCount.value - includedCount.value - excludedCount.value)

const reviewedCount = computed(() => includedCount.value + excludedCount.value)
const progressPercent = computed(() => {
  if (!totalCount.value) return 0
  return Math.round((reviewedCount.value / totalCount.value) * 100)
})
const currentPendingCount = computed(() => reviewResults.value.filter((r) => r.relevance === 'not_reviewed').length)

const currentReviewResult = computed(() => {
  if (!reviewResults.value.length) return null
  return reviewResults.value[ui.reviewIndex] || reviewResults.value[0]
})

function setFlash(nextMsg = '', nextErr = '') {
  if (flashTimeoutId) {
    clearTimeout(flashTimeoutId)
    flashTimeoutId = null
  }
  msg.value = nextMsg
  err.value = nextErr

  if (nextMsg || nextErr) {
    flashTimeoutId = window.setTimeout(() => {
      msg.value = ''
      err.value = ''
      flashTimeoutId = null
    }, 5000)
  }
}

function dismissFlash() {
  if (flashTimeoutId) {
    clearTimeout(flashTimeoutId)
    flashTimeoutId = null
  }
  msg.value = ''
  err.value = ''
}

function clearProjectDraft() {
  drafts.projectName = ''
  drafts.projectDescription = ''
}

function syncProjectDetailDraft() {
  drafts.projectInclusionCriteriaEdit = selectedProject.value?.inclusion_criteria || ''
}

function relevanceTag(relevance) {
  if (INCLUDED_RELEVANCE.includes(relevance)) return 'Included'
  if (EXCLUDED_RELEVANCE.includes(relevance)) return 'Excluded'
  return 'Pending'
}

function consensusLabel(result) {
  const pendingVotes = result?.pending_reviewers?.length || 0
  if (EXCLUDED_RELEVANCE.includes(result?.relevance)) return 'Excluded by at least one reviewer'
  if (INCLUDED_RELEVANCE.includes(result?.relevance)) return 'Unanimously included'
  if (pendingVotes > 0) return `${pendingVotes} vote${pendingVotes === 1 ? '' : 's'} pending`
  return 'Consensus pending'
}

function relevanceClass(relevance) {
  if (INCLUDED_RELEVANCE.includes(relevance)) return 'included'
  if (EXCLUDED_RELEVANCE.includes(relevance)) return 'excluded'
  return 'pending'
}

function reviewerDecisionText(relevance) {
  if (INCLUDED_RELEVANCE.includes(relevance)) return 'Include'
  if (EXCLUDED_RELEVANCE.includes(relevance)) return 'Exclude'
  return 'Pending'
}

function formatAuthors(authors) {
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

function sourceLabel(source) {
  if (source === 'scopus') return 'SCOPUS'
  if (source === 'semantic_scholar') return 'Semantic Scholar'
  return 'Unknown'
}

function providerLabel(provider) {
  if (provider === 'openai') return 'OpenAI'
  return 'OpenAI'
}

function roleLabel(role) {
  if (role === 'owner') return 'Owner'
  if (role === 'reviewer') return 'Reviewer'
  if (role === 'viewer') return 'Viewer'
  if (role === 'advisor') return 'Advisor'
  return role || 'Member'
}

function formatDateTime(value) {
  if (!value) return ''
  return new Intl.DateTimeFormat('es-ES', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value))
}

function pickFirstPendingIndex() {
  const index = reviewResults.value.findIndex((r) => r.relevance === 'not_reviewed')
  return index === -1 ? 0 : index
}

function clampReviewIndex() {
  if (!reviewResults.value.length) {
    ui.reviewIndex = 0
    return
  }
  if (ui.reviewIndex < 0) ui.reviewIndex = 0
  if (ui.reviewIndex > reviewResults.value.length - 1) {
    ui.reviewIndex = reviewResults.value.length - 1
  }
}

function syncDraftsFromCriteria() {
  const criteria = sourceCriteria.value
  if (!criteria) {
    drafts.scopusQuery = ''
    drafts.semanticKeywords = ''
    return
  }
  drafts.scopusQuery = criteria.scopus_query || ''
  drafts.semanticKeywords = criteria.keywords || ''
}

async function refreshData() {
  if (!user.value) return
  ui.loading = true
  try {
    const [projects, criteria, searches, results, tasks] = await Promise.all([
      api.getProjects(),
      api.listSearchCriteria(),
      api.listSearches(),
      api.listSearchResults(),
      api.listScreeningTasks(),
    ])

    lists.projects = projects
    lists.criteria = criteria
    lists.searches = searches
    lists.results = results
    lists.tasks = tasks

    if (!ui.selectedProjectId && lists.projects[0]) {
      ui.selectedProjectId = lists.projects[0].id
    }
    if (ui.selectedProjectId && !lists.projects.some((p) => p.id === ui.selectedProjectId)) {
      ui.selectedProjectId = lists.projects[0]?.id || null
    }

    syncProjectDetailDraft()
    syncDraftsFromCriteria()
    clampReviewIndex()
    status.value = `Signed in as ${user.value.username}`
  } catch (e) {
    setFlash('', e.message)
  } finally {
    ui.loading = false
  }
}

async function loadDiscussionThread() {
  if (!selectedProject.value || !currentReviewResult.value?.article?.id || ui.screen !== 'review') {
    discussionMessages.value = []
    return
  }

  ui.discussionLoading = true
  try {
    discussionMessages.value = await api.listArticleDiscussions({
      project: selectedProject.value.id,
      article: currentReviewResult.value.article.id,
    })
  } catch (e) {
    setFlash('', e.message)
  } finally {
    ui.discussionLoading = false
  }
}

async function boot() {
  try {
    const payload = await api.getCurrentUser()
    user.value = payload.user
    await refreshData()
  } catch {
    status.value = 'Not authenticated'
  }
}

async function login() {
  setFlash()
  try {
    const payload = await api.login(auth.username, auth.password)
    user.value = payload.user
    auth.password = ''
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  }
}

async function register() {
  setFlash()
  try {
    const payload = await api.register(auth.username, auth.email, auth.password)
    user.value = payload.user
    auth.password = ''
    auth.email = ''
    auth.mode = 'login'
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  }
}

async function logout() {
  await api.logout()
  user.value = null
  status.value = 'Signed out'
}

function openProject(project) {
  ui.selectedProjectId = project.id
  ui.screen = 'workspace'
  ui.activeTab = 'query'
  syncProjectDetailDraft()
  syncDraftsFromCriteria()
}

function backToProjects() {
  ui.screen = 'projects'
}

async function createProject() {
  if (!drafts.projectName.trim()) {
    setFlash('', 'Project name is required')
    return
  }

  const title = drafts.projectName.trim()
  const description = drafts.projectDescription.trim()

  try {
    await api.createProject({
      title,
      description: description || `Systematic review project: ${title}`,
      status: 'draft',
      research_question: `Research question for ${title}`,
      objectives: description || `Initial objectives for ${title}`,
      scope: description || `Initial scope for ${title}`,
    })

    ui.projectModalOpen = false
    clearProjectDraft()
    setFlash('Project created successfully with an automatic Inclusion Criteria proposal')
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  }
}

async function saveProjectInclusionCriteria() {
  if (!selectedProject.value) return
  if (!drafts.projectInclusionCriteriaEdit.trim()) {
    setFlash('', 'Inclusion criteria cannot be empty')
    return
  }

  try {
    await api.updateProject(selectedProject.value.id, {
      inclusion_criteria: drafts.projectInclusionCriteriaEdit.trim(),
    })
    setFlash('Inclusion criteria updated')
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  }
}

async function addCollaborator() {
  if (!selectedProject.value) return
  const collaboratorQuery = drafts.collaboratorQuery.trim()

  if (!collaboratorQuery) {
    setFlash('', 'Enter the collaborator username')
    return
  }

  try {
    let collaboratorPayload = { username: collaboratorQuery }
    const matches = await api.lookupUsers(collaboratorQuery)
    const normalizedQuery = collaboratorQuery.toLowerCase()
    const exactMatch = matches.find((candidate) => candidate.username?.toLowerCase() === normalizedQuery)

    if (exactMatch) {
      collaboratorPayload = { user_id: exactMatch.id }
    } else if (matches.length === 1) {
      collaboratorPayload = { user_id: matches[0].id }
    } else if (matches.length > 1) {
      setFlash('', 'Multiple users match. Use the collaborator exact username.')
      return
    }

    await api.addProjectCollaborator(selectedProject.value.id, {
      ...collaboratorPayload,
      role: drafts.collaboratorRole,
    })
    drafts.collaboratorQuery = ''
    setFlash(`${collaboratorQuery} added as ${roleLabel(drafts.collaboratorRole)}.`)
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  }
}

async function upsertCriteriaForSource(sourceType) {
  if (!selectedProject.value) {
    throw new Error('Select a project first')
  }

  const existing = projectCriteria.value.find((c) => c.source_type === sourceType)
  const basePayload = {
    project: selectedProject.value.id,
    name: sourceType === 'scopus' ? `SCOPUS - ${selectedProject.value.title}` : `Semantic Scholar - ${selectedProject.value.title}`,
    description: 'Project search configuration',
    source_type: sourceType,
    publication_year_from: null,
    publication_year_to: null,
    inclusion_criteria: '',
    exclusion_criteria: '',
    is_active: true,
  }

  if (sourceType === 'scopus') {
    if (!drafts.scopusQuery.trim()) {
      throw new Error('The SCOPUS query cannot be empty')
    }
    Object.assign(basePayload, { scopus_query: drafts.scopusQuery.trim(), keywords: '' })
  } else {
    if (!drafts.semanticKeywords.trim()) {
      throw new Error('You must enter keywords for Semantic Scholar')
    }
    Object.assign(basePayload, { keywords: drafts.semanticKeywords.trim(), scopus_query: '' })
  }

  if (existing) {
    return api.updateSearchCriteria(existing.id, basePayload)
  }
  return api.createSearchCriteria(basePayload)
}

async function saveQuery() {
  setFlash()
  try {
    await upsertCriteriaForSource(ui.sourceType)
    setFlash('Configuration saved')
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  }
}

async function runSemanticSearch() {
  setFlash()
  try {
    const criteria = await upsertCriteriaForSource('semantic_scholar')
    await api.executeSearch(criteria.id)
    setFlash('Search executed in Semantic Scholar')
    ui.activeTab = 'articles'
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  }
}

async function importScopus(event) {
  const file = event?.target?.files?.[0]
  if (!file) return

  setFlash()
  try {
    const criteria = await upsertCriteriaForSource('scopus')
    await api.importScopusResults(criteria.id, file, drafts.scopusQuery.trim())
    setFlash('SCOPUS results imported successfully')
    ui.activeTab = 'articles'
    await refreshData()
  } catch (e) {
    setFlash('', e.message)
  } finally {
    event.target.value = ''
  }
}

async function startReview() {
  if (!selectedProject.value) return
  if (!currentResults.value.length) {
    setFlash('', 'There are no articles available for review')
    return
  }

  setFlash()
  try {
    if (selectedProject.value.owner?.id === user.value?.id) {
      const payload = await api.startProjectReview(selectedProject.value.id)
      setFlash(
        `Review started. ${payload.assigned_results} articles distributed across ${payload.distributed_to.length} people.`,
      )
    } else if (!projectTasks.value.length) {
      setFlash('', 'Only the owner can start the project review')
      return
    }

    await refreshData()
    if (!reviewResults.value.length) {
      setFlash('', 'You do not have assigned articles in this review round')
      return
    }

    ui.reviewIndex = pickFirstPendingIndex()
    aiSuggestion.value = null
    drafts.discussionMessage = ''
    ui.screen = 'review'
  } catch (e) {
    setFlash('', e.message)
  }
}

function exportResultsCsv() {
  if (!currentResults.value.length) {
    setFlash('', 'There are no results to export')
    return
  }

  const rows = currentResults.value.map((result, idx) => {
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
  const csv = [
    headers.join(','),
    ...rows.map((row) => headers.map((key) => {
      const value = String(row[key] ?? '')
      const escaped = value.replaceAll('"', '""')
      return `"${escaped}"`
    }).join(',')),
  ].join('\n')

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${selectedProject.value?.title || 'results'}-articles.csv`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

async function reviewCurrent(nextRelevance) {
  if (!currentReviewResult.value) return

  try {
    const currentNotes = currentReviewResult.value.current_user_assessment?.notes || ''
    await api.assessRelevance(currentReviewResult.value.id, nextRelevance, currentNotes)
    await refreshData()

    const nextPending = reviewResults.value.findIndex((r) => r.relevance === 'not_reviewed')
    if (nextPending !== -1) {
      ui.reviewIndex = nextPending
    } else {
      clampReviewIndex()
    }
  } catch (e) {
    setFlash('', e.message)
  }
}

async function suggestCurrentWithAI() {
  if (!currentReviewResult.value) return

  setFlash()
  ui.aiLoading = true
  aiSuggestion.value = null
  try {
    const interaction = await api.suggestWithAI(currentReviewResult.value.id)
    aiSuggestion.value = interaction
    setFlash(`AI suggestion generated with ${providerLabel(interaction.llm_provider)}`)
  } catch (e) {
    setFlash('', e.message)
  } finally {
    ui.aiLoading = false
  }
}

async function sendDiscussionMessage() {
  if (!selectedProject.value || !currentReviewResult.value?.article?.id) return
  const message = drafts.discussionMessage.trim()
  if (!message) {
    setFlash('', 'Write a message before sending it')
    return
  }

  ui.discussionSending = true
  try {
    await api.createArticleDiscussionMessage({
      project: selectedProject.value.id,
      article: currentReviewResult.value.article.id,
      message,
    })
    drafts.discussionMessage = ''
    await loadDiscussionThread()
  } catch (e) {
    setFlash('', e.message)
  } finally {
    ui.discussionSending = false
  }
}

function nextArticle() {
  if (ui.reviewIndex < reviewResults.value.length - 1) {
    ui.reviewIndex += 1
    aiSuggestion.value = null
    drafts.discussionMessage = ''
  }
}

function previousArticle() {
  if (ui.reviewIndex > 0) {
    ui.reviewIndex -= 1
    aiSuggestion.value = null
    drafts.discussionMessage = ''
  }
}

function onChangeSource(value) {
  ui.sourceType = value
  syncDraftsFromCriteria()
}

watch(
  () => [ui.screen, selectedProject.value?.id, currentReviewResult.value?.article?.id],
  () => {
    loadDiscussionThread()
  },
)

onMounted(boot)
</script>

<template>
  <div class="page-shell">
    <main class="app-container">
      <section v-if="!user" class="auth-card">
        <h1>Mnemosyne</h1>
        <p class="subtitle">
          {{ auth.mode === 'login'
            ? 'Sign in to manage your systematic reviews.'
            : 'Create your account to start working on your systematic reviews.' }}
        </p>
        <p class="status-label">{{ status }}</p>
        <form class="auth-form" @submit.prevent="auth.mode === 'login' ? login() : register()">
          <label>
            Username
            <input v-model="auth.username" required />
          </label>
          <label v-if="auth.mode === 'register'">
            Email
            <input v-model="auth.email" type="email" required />
          </label>
          <label>
            Password
            <input v-model="auth.password" type="password" required />
          </label>
          <button type="submit">
            {{ auth.mode === 'login' ? 'Sign in' : 'Create account' }}
          </button>
          <button
            type="button"
            class="ghost"
            @click="auth.mode = auth.mode === 'login' ? 'register' : 'login'"
          >
            {{ auth.mode === 'login' ? 'Create an account' : 'I already have an account' }}
          </button>
        </form>
      </section>

      <template v-else>
        <header class="top-bar">
          <p class="status-label">{{ status }}</p>
          <div class="top-actions">
            <button class="ghost" @click="refreshData" :disabled="ui.loading">Refresh</button>
            <button class="ghost" @click="logout">Sign out</button>
          </div>
        </header>

        <div v-if="msg || err" class="toast-stack">
          <div v-if="msg" class="toast toast-ok">
            <span>{{ msg }}</span>
            <button type="button" class="toast-close" @click="dismissFlash">×</button>
          </div>
          <div v-if="err" class="toast toast-error">
            <span>{{ err }}</span>
            <button type="button" class="toast-close" @click="dismissFlash">×</button>
          </div>
        </div>

        <section v-if="ui.screen === 'projects'" class="projects-screen">
          <header class="hero">
            <h1>Systematic Literature Reviews</h1>
            <p>Manage your systematic review projects and the inclusion/exclusion process</p>
            <button class="primary large" @click="ui.projectModalOpen = true">+ New Project</button>
          </header>

          <div v-if="!lists.projects.length" class="empty-projects">
            <div class="folder-icon">[ ]</div>
            <h2>No projects yet</h2>
            <p>Create your first systematic review project</p>
            <button class="primary" @click="ui.projectModalOpen = true">+ Create Project</button>
          </div>

          <div v-else class="project-grid">
            <article v-for="project in lists.projects" :key="project.id" class="project-card" @click="openProject(project)">
              <div>
                <h3>{{ project.title }}</h3>
                <p>{{ project.description || 'No description' }}</p>
              </div>
              <span class="open-link">Open project ></span>
            </article>
          </div>
        </section>

        <section v-if="ui.screen === 'workspace' && selectedProject" class="workspace-screen">
          <button class="back-link" @click="backToProjects">< Back to Projects</button>

          <h1>{{ selectedProject.title }}</h1>
          <p class="workspace-description">{{ selectedProject.description || 'No description' }}</p>

          <section class="workspace-panel">
            <div class="query-tab">
              <h2>Inclusion Criteria (PRISMA 2020)</h2>
              <textarea
                v-model="drafts.projectInclusionCriteriaEdit"
                rows="8"
                placeholder="Define the project inclusion criteria"
              />
              <div class="inline-actions">
                <button class="primary" @click="saveProjectInclusionCriteria">Save Criteria</button>
              </div>
            </div>
          </section>

          <section class="workspace-panel">
            <div class="query-tab">
              <h2>Review Team</h2>
              <p class="hint">An article is only finally included when all required team members vote to include it.</p>
              <div class="collaborator-list">
                <span class="status-pill source">Owner: {{ selectedProject.owner?.username }}</span>
                <span
                  v-for="collaborator in selectedProject.collaborators"
                  :key="collaborator.id"
                  class="status-pill"
                >
                  {{ collaborator.username }} · {{ roleLabel(collaborator.role) }}
                </span>
              </div>
              <div class="inline-actions">
                <input
                  v-model="drafts.collaboratorQuery"
                  placeholder="collaborator username"
                  @keydown.enter.prevent="addCollaborator"
                />
                <select v-model="drafts.collaboratorRole">
                  <option value="reviewer">Reviewer</option>
                  <option value="viewer">Viewer</option>
                  <option value="advisor">Advisor</option>
                </select>
                <button class="primary" @click="addCollaborator">Add collaborator</button>
              </div>
            </div>
          </section>

          <section class="stats-grid">
            <article class="stat-card">
              <h3>Total</h3>
              <strong>{{ totalCount }}</strong>
            </article>
            <article class="stat-card green">
              <h3>Included</h3>
              <strong>{{ includedCount }}</strong>
            </article>
            <article class="stat-card red">
              <h3>Excluded</h3>
              <strong>{{ excludedCount }}</strong>
            </article>
            <article class="stat-card yellow">
              <h3>Pending</h3>
              <strong>{{ pendingCount }}</strong>
            </article>
          </section>

          <section class="workspace-panel">
            <nav class="tabs">
              <button
                class="tab"
                :class="{ active: ui.activeTab === 'query' }"
                @click="ui.activeTab = 'query'"
              >
                SCOPUS / Semantic Scholar Query
              </button>
              <button
                class="tab"
                :class="{ active: ui.activeTab === 'articles' }"
                @click="ui.activeTab = 'articles'"
              >
                Articles ({{ totalCount }})
              </button>
            </nav>

            <div v-if="ui.activeTab === 'query'" class="query-tab">
              <h2>Search Configuration</h2>

              <label>
                Source
                <select :value="ui.sourceType" @change="onChangeSource($event.target.value)">
                  <option value="scopus">SCOPUS</option>
                  <option value="semantic_scholar">Semantic Scholar</option>
                </select>
              </label>

              <template v-if="ui.sourceType === 'scopus'">
                <label>
                  SCOPUS Search Query
                  <textarea
                    v-model="drafts.scopusQuery"
                    rows="5"
                    placeholder='E.g.: TITLE-ABS-KEY("machine learning" AND "healthcare") AND PUBYEAR > 2019'
                  />
                </label>
                <p class="hint">Define your search query using SCOPUS syntax</p>
                <button class="primary" @click="saveQuery">Save Query</button>

                <hr />

                <h3>Upload SCOPUS Results</h3>
                <p class="info-box">
                  <strong>Instructions:</strong> Export the results from SCOPUS in CSV format and upload them here. The file should include columns such as Title, Authors, Year, Abstract, DOI, etc.
                </p>
                <label class="upload-btn">
                  Upload CSV File
                  <input type="file" accept=".csv,.json,application/json,text/csv" @change="importScopus" />
                </label>
              </template>

              <template v-else>
                <label>
                  Keywords for Semantic Scholar
                  <textarea
                    v-model="drafts.semanticKeywords"
                    rows="4"
                    placeholder="E.g.: machine learning healthcare, neural networks diagnosis"
                  />
                </label>
                <p class="hint">Separate multiple terms with commas to broaden the search.</p>
                <div class="inline-actions">
                  <button class="primary" @click="saveQuery">Save Configuration</button>
                  <button class="success" @click="runSemanticSearch">Search in Semantic Scholar</button>
                </div>
              </template>
            </div>

            <div v-else class="articles-tab">
              <div class="articles-header">
                <h2>Article List</h2>
                <div class="inline-actions">
                  <label class="source-filter">
                    Source
                    <select v-model="ui.articleSourceFilter">
                      <option value="all">All</option>
                      <option value="scopus">SCOPUS</option>
                      <option value="semantic_scholar">Semantic Scholar</option>
                    </select>
                  </label>
                  <label class="source-filter">
                    Status
                    <select v-model="ui.articleDecisionFilter">
                      <option value="all">All</option>
                      <option value="pending">Pending</option>
                      <option value="included">Included</option>
                      <option value="excluded">Excluded</option>
                    </select>
                  </label>
                  <button class="ghost" @click="exportResultsCsv">Export Results</button>
                  <button class="success" :disabled="!currentResults.length" @click="startReview">
                    Start Review ({{ currentPendingCount }} pending)
                  </button>
                </div>
              </div>

              <div v-if="!currentResults.length" class="empty-articles">
                There are no results for the selected filter. Change the source or import/run a search.
              </div>

              <article v-for="(result, idx) in currentResults" :key="result.id" class="article-row">
                <div class="article-row-top">
                  <span class="article-rank">#{{ idx + 1 }}</span>
                  <span class="status-pill source">{{ sourceLabel(result.article?.article_source) }}</span>
                  <span class="status-pill" :class="relevanceClass(result.relevance)">{{ relevanceTag(result.relevance) }}</span>
                </div>
                <h3>{{ result.article?.title || 'Untitled' }}</h3>
                <p class="meta-line">
                  {{ formatAuthors(result.article?.authors) }} · {{ result.article?.publication_year || 'N/A' }} · {{ result.article?.publication_venue || 'No journal' }}
                </p>
                <p class="meta-line">{{ consensusLabel(result) }}</p>
              </article>
            </div>
          </section>
        </section>

        <section v-if="ui.screen === 'review' && selectedProject" class="review-screen">
          <button class="back-link" @click="ui.screen = 'workspace'">< Back to Project</button>
          <h1>{{ selectedProject.title }}</h1>

          <section class="progress-card">
            <div class="progress-head">
              <h2>Review Progress</h2>
              <strong>{{ reviewedCount }} / {{ totalCount }} ({{ progressPercent }}%)</strong>
            </div>
            <div class="progress-track">
              <div class="progress-value" :style="{ width: `${progressPercent}%` }" />
            </div>
            <p class="progress-legend">
              <span class="dot green"></span> Included: {{ includedCount }}
              <span class="dot red"></span> Excluded: {{ excludedCount }}
            </p>
          </section>

          <article v-if="currentReviewResult" class="review-card">
            <header class="review-header">
              <div>
                <p>Article {{ ui.reviewIndex + 1 }} of {{ reviewResults.length }}</p>
                <h2>{{ currentReviewResult.article?.title || 'Untitled' }}</h2>
              </div>
              <span class="status-pill" :class="relevanceClass(currentReviewResult.relevance)">
                {{ relevanceTag(currentReviewResult.relevance) }}
              </span>
            </header>

            <div class="review-meta">
              <div>
                <h3>Authors</h3>
                <p>{{ formatAuthors(currentReviewResult.article?.authors) }}</p>
              </div>
              <div>
                <h3>Year</h3>
                <p>{{ currentReviewResult.article?.publication_year || 'N/A' }}</p>
              </div>
              <div>
                <h3>Journal</h3>
                <p>{{ currentReviewResult.article?.publication_venue || 'Not available' }}</p>
              </div>
              <div>
                <h3>Source</h3>
                <p>{{ sourceLabel(currentReviewResult.article?.article_source) }}</p>
              </div>
              <div>
                <h3>DOI / URL</h3>
                <a v-if="currentReviewResult.article?.source_url" :href="currentReviewResult.article.source_url" target="_blank" rel="noreferrer">
                  {{ currentReviewResult.article.source_url }}
                </a>
                <p v-else>Not available</p>
              </div>
            </div>

            <div class="abstract-box">
              <h3>Abstract</h3>
              <div class="abstract-scroll">
                {{ currentReviewResult.article?.abstract || 'This article has no abstract available.' }}
              </div>
            </div>

            <div class="review-actions">
              <button class="danger" @click="reviewCurrent('not_relevant')">Exclude</button>
              <button class="success" @click="reviewCurrent('highly_relevant')">Include</button>
            </div>

            <section class="review-section">
              <h3>Team Consensus</h3>
              <p class="hint">{{ consensusLabel(currentReviewResult) }}</p>
              <div class="collaborator-list">
                <span class="status-pill source" v-for="reviewer in currentReviewResult.required_reviewers" :key="reviewer.id">
                  {{ reviewer.username }}
                </span>
              </div>
              <div class="assessment-list">
                <p v-for="assessment in currentReviewResult.assessments" :key="assessment.id">
                  <strong>{{ assessment.reviewer.username }}:</strong> {{ reviewerDecisionText(assessment.relevance) }}
                </p>
                <p v-if="!currentReviewResult.assessments?.length">No votes have been recorded yet.</p>
              </div>
            </section>

            <div class="ai-panel">
              <h3>Suggest with AI</h3>
              <div class="inline-actions">
                <button class="primary" :disabled="ui.aiLoading" @click="suggestCurrentWithAI">
                  {{ ui.aiLoading ? 'Generating suggestion...' : 'Suggest with AI' }}
                </button>
              </div>

              <div v-if="aiSuggestion" class="ai-result">
                <p><strong>Provider:</strong> OpenAI</p>
                <p><strong>Suggestion:</strong> {{ aiSuggestion.recommendation }}</p>
                <p><strong>Rationale:</strong> {{ aiSuggestion.rationale || 'No rationale provided' }}</p>
              </div>
            </div>

            <div class="discussion-panel">
              <div class="discussion-head">
                <div>
                  <h3>Paper Discussion</h3>
                  <p>Team chat to discuss strengths, concerns, and decisions about this article.</p>
                </div>
                <span class="status-pill source">{{ discussionMessages.length }} messages</span>
              </div>

              <div v-if="ui.discussionLoading" class="discussion-empty">
                Loading conversation...
              </div>
              <div v-else-if="!discussionMessages.length" class="discussion-empty">
                There are no messages for this paper yet. Be the first to comment.
              </div>
              <div v-else class="discussion-thread">
                <article
                  v-for="messageItem in discussionMessages"
                  :key="messageItem.id"
                  class="discussion-message"
                  :class="{ own: messageItem.author?.id === user?.id }"
                >
                  <div class="discussion-meta">
                    <strong>{{ messageItem.author?.username || 'User' }}</strong>
                    <span>{{ formatDateTime(messageItem.created_at) }}</span>
                  </div>
                  <p>{{ messageItem.message }}</p>
                </article>
              </div>

              <div class="discussion-composer">
                <textarea
                  v-model="drafts.discussionMessage"
                  rows="3"
                  placeholder="Write a comment for the team about this paper"
                  @keydown.ctrl.enter.prevent="sendDiscussionMessage"
                />
                <div class="inline-actions">
                  <button class="primary" :disabled="ui.discussionSending" @click="sendDiscussionMessage">
                    {{ ui.discussionSending ? 'Sending...' : 'Send message' }}
                  </button>
                </div>
              </div>
            </div>

            <footer class="review-nav">
              <button class="ghost" :disabled="ui.reviewIndex === 0" @click="previousArticle">< Previous</button>
              <span>Article {{ ui.reviewIndex + 1 }} of {{ reviewResults.length }}</span>
              <button class="ghost" :disabled="ui.reviewIndex >= reviewResults.length - 1" @click="nextArticle">Next ></button>
            </footer>
          </article>

          <article v-else class="empty-articles">
            There are no articles available to review in this project.
          </article>
        </section>

        <div v-if="ui.projectModalOpen" class="modal-overlay" @click.self="ui.projectModalOpen = false">
          <div class="modal-card">
            <h2>New Project</h2>
            <label>
              Project Name
              <input v-model="drafts.projectName" placeholder="E.g.: Machine Learning in Healthcare Review" />
            </label>
            <label>
              Description (optional)
              <textarea v-model="drafts.projectDescription" rows="4" placeholder="Describe the goal of your systematic review" />
            </label>
            <p class="hint">When you create the project, an Inclusion Criteria proposal (PRISMA 2020) will be generated automatically using the configured LLM. You can review and edit it afterwards.</p>
            <div class="modal-actions">
              <button class="ghost" @click="ui.projectModalOpen = false">Cancel</button>
              <button class="primary" :disabled="!drafts.projectName.trim()" @click="createProject">Create</button>
            </div>
          </div>
        </div>
      </template>
    </main>
  </div>
</template>



