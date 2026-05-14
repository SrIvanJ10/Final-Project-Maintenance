<script setup>
import { onMounted, watch } from 'vue'

// ── Constants & Utils ──────────────────────────────────────────────
import { SCREENS, TABS } from './constants.js'

// ── Composables ────────────────────────────────────────────────────
import { useFlash } from './composables/useFlash.js'
import { useAuth } from './composables/useAuth.js'
import { useProjects } from './composables/useProjects.js'
import { useSearch } from './composables/useSearch.js'
import { useReview } from './composables/useReview.js'
import { useDiscussion } from './composables/useDiscussion.js'

// ── Components ─────────────────────────────────────────────────────
import AuthCard from './components/AuthCard.vue'
import TopBar from './components/TopBar.vue'
import ToastStack from './components/ToastStack.vue'
import ProjectsScreen from './components/ProjectsScreen.vue'
import ProjectModal from './components/ProjectModal.vue'
import WorkspaceScreen from './components/WorkspaceScreen.vue'
import StatsGrid from './components/StatsGrid.vue'
import QueryTab from './components/QueryTab.vue'
import ArticlesTab from './components/ArticlesTab.vue'
import ReviewScreen from './components/ReviewScreen.vue'

// ── Setup ──────────────────────────────────────────────────────────
const { msg, err, setFlash, dismissFlash } = useFlash()

const {
  user,
  status,
  auth,
  boot,
  login,
  register,
  logout
} = useAuth({
  setFlash,
  onAuthenticated: () => projects.refreshData()
})

const projects = useProjects({ user, status, setFlash })

const search = useSearch({
  selectedProject: projects.selectedProject,
  projectCriteria: projects.projectCriteria,
  setFlash,
  refreshData: projects.refreshData,
  activeTab: projects.activeTab
})

const review = useReview({
  user,
  selectedProject: projects.selectedProject,
  projectSearches: projects.projectSearches,
  projectResults: projects.projectResults,
  canReview: projects.canReview,
  lists: projects.lists,
  screen: projects.screen,
  setFlash,
  refreshData: projects.refreshData
})

const discussion = useDiscussion({
  selectedProject: projects.selectedProject,
  currentReviewResult: review.currentReviewResult,
  screen: projects.screen,
  setFlash
})

// ── Watchers ───────────────────────────────────────────────────────
watch(
  () => [projects.screen.value, projects.selectedProject.value?.id, review.currentReviewResult.value?.article?.id],
  () => {
    discussion.loadDiscussionThread()
    review.loadTimeline()
  }
)

onMounted(boot)
</script>

<template>
  <div class="page-shell">
    <main class="app-container">
      <!-- Auth Screen -->
      <AuthCard
        v-if="!user"
        :auth="auth"
        :status="status"
        @login="login"
        @register="register"
      />

      <template v-else>
        <!-- Top Bar -->
        <TopBar
          :status="status"
          :loading="projects.loading.value"
          @refresh="projects.refreshData"
          @logout="logout"
        />

        <!-- Notifications -->
        <ToastStack
          :msg="msg"
          :err="err"
          @dismiss="dismissFlash"
        />

        <!-- Projects List -->
        <ProjectsScreen
          v-if="projects.screen.value === SCREENS.PROJECTS"
          :projects="projects.lists.projects"
          @open-project="projects.openProject"
          @open-modal="projects.projectModalOpen = true"
        />

        <!-- Workspace (Search & Articles) -->
        <WorkspaceScreen
          v-if="projects.screen.value === SCREENS.WORKSPACE && projects.selectedProject.value"
          :selected-project="projects.selectedProject.value"
          :can-review="projects.canReview.value"
          :is-owner="projects.isOwner.value"
          :drafts="projects.drafts"
          :generating-report="projects.generatingReport.value"
          :generated-report="projects.generatedReport.value"
          :total-count="projects.totalCount.value"
          :pending-count="projects.pendingCount.value"
          @generate-report="projects.generateReport"
          @save-criteria="projects.saveProjectInclusionCriteria"
          @add-collaborator="projects.addCollaborator"
          @back="projects.backToProjects"
        >
          <template #stats>
            <StatsGrid
              :total-count="projects.totalCount.value"
              :included-count="projects.includedCount.value"
              :excluded-count="projects.excludedCount.value"
              :pending-count="projects.pendingCount.value"
            />
          </template>

          <template #tabs>
            <section class="workspace-panel">
              <nav class="tabs">
                <button
                  class="tab"
                  :class="{ active: projects.activeTab.value === TABS.QUERY }"
                  @click="projects.activeTab.value = TABS.QUERY"
                >
                  SCOPUS / Semantic Scholar Query
                </button>
                <button
                  class="tab"
                  :class="{ active: projects.activeTab.value === TABS.ARTICLES }"
                  @click="projects.activeTab.value = TABS.ARTICLES"
                >
                  Articles ({{ projects.totalCount.value }})
                </button>
              </nav>

              <QueryTab
                v-if="projects.activeTab.value === TABS.QUERY"
                :source-type="search.sourceType.value"
                :drafts="search.drafts"
                :can-review="projects.canReview.value"
                @change-source="search.onChangeSource"
                @save-query="search.saveQuery"
                @run-semantic="search.runSemanticSearch"
                @import-scopus="search.importScopus"
              />

              <ArticlesTab
                v-else
                v-model:article-source-filter="review.articleSourceFilter.value"
                v-model:article-decision-filter="review.articleDecisionFilter.value"
                :current-results="review.currentResults.value"
                :can-review="projects.canReview.value"
                :current-pending-count="review.currentPendingCount.value"
                @export="review.exportResultsCsv"
                @start-review="review.startReview"
              />
            </section>
          </template>
        </WorkspaceScreen>

        <!-- Review Screen -->
        <ReviewScreen
          v-if="projects.screen.value === SCREENS.REVIEW && projects.selectedProject.value"
          v-model:discussion-message="discussion.discussionMessage.value"
          :selected-project="projects.selectedProject.value"
          :reviewed-count="projects.reviewedCount.value"
          :total-count="projects.totalCount.value"
          :progress-percent="projects.progressPercent.value"
          :included-count="projects.includedCount.value"
          :excluded-count="projects.excludedCount.value"
          :current-review-result="review.currentReviewResult.value"
          :review-index="review.reviewIndex.value"
          :review-results-length="review.reviewResults.value.length"
          :can-review="projects.canReview.value"
          :ai-loading="review.aiLoading.value"
          :ai-suggestion="review.aiSuggestion.value"
          :timeline-events="review.timelineEvents.value"
          :timeline-loading="review.timelineLoading.value"
          :discussion-messages="discussion.discussionMessages.value"
          :discussion-loading="discussion.discussionLoading.value"
          :discussion-sending="discussion.discussionSending.value"
          :user="user"
          @back="projects.screen.value = SCREENS.WORKSPACE"
          @exclude="review.reviewCurrent('not_relevant')"
          @include="review.reviewCurrent('highly_relevant')"
          @suggest-ai="review.suggestCurrentWithAI"
          @send-message="discussion.sendDiscussionMessage"
          @previous="review.previousArticle"
          @next="review.nextArticle"
        />

        <!-- Modals -->
        <ProjectModal
          v-if="projects.projectModalOpen.value"
          v-model:project-name="projects.drafts.projectName"
          v-model:project-description="projects.drafts.projectDescription"
          @create="projects.createProject"
          @close="projects.projectModalOpen.value = false"
        />
      </template>
    </main>
  </div>
</template>
