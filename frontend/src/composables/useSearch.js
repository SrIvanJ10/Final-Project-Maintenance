/**
 * Composable – search criteria, query saving, and search execution.
 *
 * Manages the SCOPUS / Semantic Scholar query drafts and the
 * criteria upsert logic that was previously inlined in App.vue.
 */

import { computed, reactive, ref } from 'vue'
import * as api from '../lib/api'
import { SOURCES, TABS } from '../constants.js'

/**
 * @param {object}   deps
 * @param {import('vue').ComputedRef}  deps.selectedProject
 * @param {import('vue').ComputedRef}  deps.projectCriteria
 * @param {Function} deps.setFlash
 * @param {Function} deps.refreshData
 * @param {import('vue').Ref<string>}  deps.activeTab
 */
export function useSearch({ selectedProject, projectCriteria, setFlash, refreshData, activeTab }) {
  const sourceType = ref(SOURCES.SCOPUS)

  const drafts = reactive({
    scopusQuery: '',
    semanticKeywords: '',
  })

  const sourceCriteria = computed(() => {
    return projectCriteria.value.find((c) => c.source_type === sourceType.value) || null
  })

  /** Sync the draft inputs from the currently selected criteria. */
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

  /**
   * Create or update a search-criteria record for the given source type.
   * @param {string} st – source type constant
   * @returns {Promise<object>} the created / updated criteria object
   */
  async function upsertCriteriaForSource(st) {
    if (!selectedProject.value) {
      throw new Error('Select a project first')
    }

    const existing = projectCriteria.value.find((c) => c.source_type === st)
    const basePayload = {
      project: selectedProject.value.id,
      name:
        st === SOURCES.SCOPUS
          ? `SCOPUS - ${selectedProject.value.title}`
          : `Semantic Scholar - ${selectedProject.value.title}`,
      description: 'Project search configuration',
      source_type: st,
      publication_year_from: null,
      publication_year_to: null,
      inclusion_criteria: '',
      exclusion_criteria: '',
      is_active: true,
    }

    if (st === SOURCES.SCOPUS) {
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

  /** Save the current query / keywords without executing a search. */
  async function saveQuery() {
    setFlash()
    try {
      await upsertCriteriaForSource(sourceType.value)
      setFlash('Configuration saved')
      await refreshData()
    } catch (e) {
      setFlash('', e.message)
    }
  }

  /** Save and immediately run a Semantic Scholar search. */
  async function runSemanticSearch() {
    setFlash()
    try {
      const criteria = await upsertCriteriaForSource(SOURCES.SEMANTIC)
      await api.executeSearch(criteria.id)
      setFlash('Search executed in Semantic Scholar')
      activeTab.value = TABS.ARTICLES
      await refreshData()
    } catch (e) {
      setFlash('', e.message)
    }
  }

  /** Upload a SCOPUS CSV file and import its results. */
  async function importScopus(event) {
    const file = event?.target?.files?.[0]
    if (!file) return

    setFlash()
    try {
      const criteria = await upsertCriteriaForSource(SOURCES.SCOPUS)
      await api.importScopusResults(criteria.id, file, drafts.scopusQuery.trim())
      setFlash('SCOPUS results imported successfully')
      activeTab.value = TABS.ARTICLES
      await refreshData()
    } catch (e) {
      setFlash('', e.message)
    } finally {
      event.target.value = ''
    }
  }

  /** Called when the user switches the source type dropdown. */
  function onChangeSource(value) {
    sourceType.value = value
    syncDraftsFromCriteria()
  }

  return {
    sourceType,
    drafts,
    sourceCriteria,
    syncDraftsFromCriteria,
    saveQuery,
    runSemanticSearch,
    importScopus,
    onChangeSource,
  }
}
