/**
 * Composable – article review workflow.
 *
 * Owns the review-screen state: filtered results, navigation index,
 * AI suggestions, and the include / exclude actions.
 */

import { computed, ref } from 'vue'
import * as api from '../lib/api'
import { SCREENS, SOURCE_FILTERS, DECISION_FILTERS } from '../constants.js'
import { INCLUDED_RELEVANCE, EXCLUDED_RELEVANCE } from '../utils/relevance.js'
import { providerLabel } from '../utils/formatters.js'
import { generateResultsCsv, downloadCsv } from '../utils/csv.js'

/**
 * Parse the result IDs assigned to a screening task via its `notes` JSON.
 * @param {object} task
 * @returns {number[]}
 */
export function parseTaskAssignments(task) {
  if (!task?.notes) return []
  try {
    const payload = JSON.parse(task.notes)
    return Array.isArray(payload?.assigned_result_ids) ? payload.assigned_result_ids : []
  } catch {
    return []
  }
}

/**
 * @param {object}  deps
 * @param {import('vue').Ref<object|null>}  deps.user
 * @param {import('vue').ComputedRef}       deps.selectedProject
 * @param {import('vue').ComputedRef}       deps.projectSearches
 * @param {import('vue').ComputedRef}       deps.projectResults
 * @param {import('vue').ComputedRef}       deps.canReview
 * @param {import('vue').Reactive}          deps.lists
 * @param {import('vue').Ref<string>}       deps.screen
 * @param {Function}                        deps.setFlash
 * @param {Function}                        deps.refreshData
 */
export function useReview({
  user,
  selectedProject,
  projectSearches,
  projectResults,
  canReview,
  lists,
  screen,
  setFlash,
  refreshData,
}) {
  // ── Filters ────────────────────────────────────────────────────────
  const articleSourceFilter = ref(SOURCE_FILTERS.ALL)
  const articleDecisionFilter = ref(DECISION_FILTERS.ALL)

  // ── Review navigation ──────────────────────────────────────────────
  const reviewIndex = ref(0)
  const aiLoading = ref(false)
  const aiSuggestion = ref(null)

  // ── Task-based filtering ───────────────────────────────────────────
  const projectTasks = computed(() => {
    const searchIds = new Set(projectSearches.value.map((s) => s.id))
    return lists.tasks.filter((task) => searchIds.has(task.search))
  })

  const currentUserProjectTasks = computed(() => {
    return projectTasks.value.filter((task) => task.reviewer?.id === user.value?.id)
  })

  // ── Filtered results ──────────────────────────────────────────────
  const currentResults = computed(() => {
    const sourceFilter = articleSourceFilter.value
    const decisionFilter = articleDecisionFilter.value
    const searchOrder = new Map(projectSearches.value.map((s, idx) => [s.id, idx]))

    return projectResults.value
      .filter((r) => {
        if (sourceFilter === SOURCE_FILTERS.ALL) return true
        return r.article?.article_source === sourceFilter
      })
      .filter((r) => {
        if (decisionFilter === DECISION_FILTERS.ALL) return true
        if (decisionFilter === DECISION_FILTERS.PENDING) return r.relevance === 'not_reviewed'
        if (decisionFilter === DECISION_FILTERS.INCLUDED) return INCLUDED_RELEVANCE.includes(r.relevance)
        if (decisionFilter === DECISION_FILTERS.EXCLUDED) return EXCLUDED_RELEVANCE.includes(r.relevance)
        return true
      })
      .slice()
      .sort((a, b) => {
        const searchCmp = (searchOrder.get(a.search) ?? 999999) - (searchOrder.get(b.search) ?? 999999)
        if (searchCmp !== 0) return searchCmp
        return (a.rank || 0) - (b.rank || 0)
      })
  })

  const reviewResults = computed(() => {
    const assignedIds = new Set(currentUserProjectTasks.value.flatMap(parseTaskAssignments))
    const hasDistributedTasks = projectTasks.value.some((task) => parseTaskAssignments(task).length > 0)

    if (!hasDistributedTasks) return currentResults.value
    return currentResults.value.filter((result) => assignedIds.has(result.id))
  })

  const currentPendingCount = computed(() =>
    reviewResults.value.filter((r) => r.relevance === 'not_reviewed').length,
  )

  const currentReviewResult = computed(() => {
    if (!reviewResults.value.length) return null
    return reviewResults.value[reviewIndex.value] || reviewResults.value[0]
  })

  // ── Index helpers ──────────────────────────────────────────────────
  function pickFirstPendingIndex() {
    const index = reviewResults.value.findIndex((r) => r.relevance === 'not_reviewed')
    return index === -1 ? 0 : index
  }

  function clampReviewIndex() {
    if (!reviewResults.value.length) {
      reviewIndex.value = 0
      return
    }
    if (reviewIndex.value < 0) reviewIndex.value = 0
    if (reviewIndex.value > reviewResults.value.length - 1) {
      reviewIndex.value = reviewResults.value.length - 1
    }
  }

  // ── Actions ────────────────────────────────────────────────────────
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

      reviewIndex.value = pickFirstPendingIndex()
      aiSuggestion.value = null
      screen.value = SCREENS.REVIEW
    } catch (e) {
      setFlash('', e.message)
    }
  }

  async function reviewCurrent(nextRelevance) {
    if (!currentReviewResult.value) return

    try {
      const currentNotes = currentReviewResult.value.current_user_assessment?.notes || ''
      await api.assessRelevance(currentReviewResult.value.id, nextRelevance, currentNotes)
      await refreshData()

      const nextPending = reviewResults.value.findIndex((r) => r.relevance === 'not_reviewed')
      if (nextPending !== -1) {
        reviewIndex.value = nextPending
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
    aiLoading.value = true
    aiSuggestion.value = null
    try {
      const interaction = await api.suggestWithAI(currentReviewResult.value.id)
      aiSuggestion.value = interaction
      setFlash(`AI suggestion generated with ${providerLabel(interaction.llm_provider)}`)
    } catch (e) {
      setFlash('', e.message)
    } finally {
      aiLoading.value = false
    }
  }

  function nextArticle() {
    if (reviewIndex.value < reviewResults.value.length - 1) {
      reviewIndex.value += 1
      aiSuggestion.value = null
    }
  }

  function previousArticle() {
    if (reviewIndex.value > 0) {
      reviewIndex.value -= 1
      aiSuggestion.value = null
    }
  }

  /** Export the currently filtered results as a CSV download. */
  function exportResultsCsv() {
    if (!currentResults.value.length) {
      setFlash('', 'There are no results to export')
      return
    }
    const csv = generateResultsCsv(currentResults.value)
    const filename = `${selectedProject.value?.title || 'results'}-articles.csv`
    downloadCsv(csv, filename)
  }

  return {
    // filters
    articleSourceFilter,
    articleDecisionFilter,
    // review state
    reviewIndex,
    aiLoading,
    aiSuggestion,
    // computed
    projectTasks,
    currentResults,
    reviewResults,
    currentPendingCount,
    currentReviewResult,
    // methods
    clampReviewIndex,
    pickFirstPendingIndex,
    startReview,
    reviewCurrent,
    suggestCurrentWithAI,
    nextArticle,
    previousArticle,
    exportResultsCsv,
  }
}
