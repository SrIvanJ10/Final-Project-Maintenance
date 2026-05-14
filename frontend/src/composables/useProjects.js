/**
 * Composable – project list, selection and CRUD.
 *
 * Manages the reactive `lists` store and all project-level operations
 * (create, update inclusion criteria, add collaborator).
 */

import { computed, reactive, ref } from 'vue'
import * as api from '../lib/api'
import { SCREENS, TABS } from '../constants.js'
import { roleLabel } from '../utils/formatters.js'
import { INCLUDED_RELEVANCE, EXCLUDED_RELEVANCE } from '../utils/relevance.js'

/**
 * @param {object}   deps
 * @param {import('vue').Ref<object|null>} deps.user
 * @param {import('vue').Ref<string>}      deps.status
 * @param {Function} deps.setFlash
 */
export function useProjects({ user, status, setFlash }) {
  // ── Reactive stores ────────────────────────────────────────────────
  const lists = reactive({
    projects: [],
    criteria: [],
    searches: [],
    results: [],
    tasks: [],
  })

  // ── UI state owned by this composable ──────────────────────────────
  const screen = ref(SCREENS.PROJECTS)
  const activeTab = ref(TABS.QUERY)
  const projectModalOpen = ref(false)
  const selectedProjectId = ref(null)
  const loading = ref(false)
  const generatingReport = ref(false)
  const generatedReport = ref(null)

  // ── Drafts ─────────────────────────────────────────────────────────
  const drafts = reactive({
    projectName: '',
    projectDescription: '',
    projectInclusionCriteriaEdit: '',
    collaboratorQuery: '',
    collaboratorRole: 'reviewer',
    reportPrompt: '',
  })

  // ── Computed ───────────────────────────────────────────────────────
  const selectedProject = computed(() =>
    lists.projects.find((p) => p.id === selectedProjectId.value) || null,
  )

  const projectCriteria = computed(() => {
    if (!selectedProject.value) return []
    return lists.criteria.filter((c) => c.project === selectedProject.value.id)
  })

  const currentUserRole = computed(() => {
    if (!selectedProject.value || !user.value) return null
    if (selectedProject.value.owner?.id === user.value.id) return 'owner'
    const membership = selectedProject.value.collaborators?.find((c) => c.id === user.value.id)
    return membership?.role || null
  })

  const isOwner = computed(() => currentUserRole.value === 'owner')
  const canReview = computed(() => ['owner', 'reviewer'].includes(currentUserRole.value))

  const projectSearches = computed(() => {
    const criteriaIds = new Set(projectCriteria.value.map((c) => c.id))
    return lists.searches.filter((s) => criteriaIds.has(s.criteria))
  })

  const projectResults = computed(() => {
    const searchIds = new Set(projectSearches.value.map((s) => s.id))
    if (!searchIds.size) return []
    return lists.results.filter((r) => searchIds.has(r.search))
  })

  // ── Stats ──────────────────────────────────────────────────────────
  const totalCount = computed(() => projectResults.value.length)
  const includedCount = computed(() =>
    projectResults.value.filter((r) => INCLUDED_RELEVANCE.includes(r.relevance)).length,
  )
  const excludedCount = computed(() =>
    projectResults.value.filter((r) => EXCLUDED_RELEVANCE.includes(r.relevance)).length,
  )
  const pendingCount = computed(() =>
    totalCount.value - includedCount.value - excludedCount.value,
  )
  const reviewedCount = computed(() => includedCount.value + excludedCount.value)
  const progressPercent = computed(() => {
    if (!totalCount.value) return 0
    return Math.round((reviewedCount.value / totalCount.value) * 100)
  })

  // ── Draft helpers ──────────────────────────────────────────────────
  function clearProjectDraft() {
    drafts.projectName = ''
    drafts.projectDescription = ''
  }

  function syncProjectDetailDraft() {
    drafts.projectInclusionCriteriaEdit = selectedProject.value?.inclusion_criteria || ''
  }

  // ── Data loading ───────────────────────────────────────────────────
  async function refreshData() {
    if (!user.value) return
    loading.value = true
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

      if (!selectedProjectId.value && lists.projects[0]) {
        selectedProjectId.value = lists.projects[0].id
      }
      if (selectedProjectId.value && !lists.projects.some((p) => p.id === selectedProjectId.value)) {
        selectedProjectId.value = lists.projects[0]?.id || null
      }

      syncProjectDetailDraft()
      status.value = `Signed in as ${user.value.username}`
    } catch (e) {
      setFlash('', e.message)
    } finally {
      loading.value = false
    }
  }

  // ── Navigation ─────────────────────────────────────────────────────
  function openProject(project) {
    selectedProjectId.value = project.id
    screen.value = SCREENS.WORKSPACE
    activeTab.value = TABS.QUERY
    syncProjectDetailDraft()
  }

  function backToProjects() {
    screen.value = SCREENS.PROJECTS
  }

  // ── CRUD ───────────────────────────────────────────────────────────
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

      projectModalOpen.value = false
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

  async function generateReport() {
    if (!selectedProject.value) return
    generatingReport.value = true
    setFlash()
    try {
      const response = await api.generateProjectReport(selectedProject.value.id, drafts.reportPrompt)
      generatedReport.value = response.report
      setFlash('Report generated successfully')
    } catch (e) {
      setFlash('', e.message)
    } finally {
      generatingReport.value = false
    }
  }

  return {
    // stores
    lists,
    // UI state
    screen,
    activeTab,
    projectModalOpen,
    selectedProjectId,
    loading,
    // drafts
    drafts,
    // computed
    selectedProject,
    projectCriteria,
    currentUserRole,
    isOwner,
    canReview,
    projectSearches,
    projectResults,
    totalCount,
    includedCount,
    excludedCount,
    pendingCount,
    reviewedCount,
    progressPercent,
    // methods
    refreshData,
    syncProjectDetailDraft,
    openProject,
    backToProjects,
    createProject,
    saveProjectInclusionCriteria,
    addCollaborator,
    clearProjectDraft,
    generateReport,
    generatingReport,
    generatedReport,
  }
}
