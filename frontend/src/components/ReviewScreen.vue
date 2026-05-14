<script setup>
import { formatAuthors, sourceLabel, formatDateTime } from '../utils/formatters.js'
import { relevanceClass, relevanceTag, reviewerDecisionText, consensusLabel } from '../utils/relevance.js'

defineProps({
  selectedProject: Object,
  reviewedCount: Number,
  totalCount: Number,
  progressPercent: Number,
  includedCount: Number,
  excludedCount: Number,
  currentReviewResult: Object,
  reviewIndex: Number,
  reviewResultsLength: Number,
  canReview: Boolean,
  aiLoading: Boolean,
  aiSuggestion: Object,
  discussionMessages: Array,
  discussionLoading: Boolean,
  discussionSending: Boolean,
  discussionMessage: String,
  user: Object,
})

const emit = defineEmits([
  'back',
  'exclude',
  'include',
  'suggest-ai',
  'send-message',
  'update:discussionMessage',
  'previous',
  'next'
])
</script>

<template>
  <section class="review-screen">
    <button class="back-link" @click="emit('back')">< Back to Project</button>
    <h1>{{ selectedProject.title }}</h1>

    <!-- Progress Card -->
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
          <p>Article {{ reviewIndex + 1 }} of {{ reviewResultsLength }}</p>
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

      <div v-if="canReview" class="review-actions">
        <button class="danger" @click="emit('exclude')">Exclude</button>
        <button class="success" @click="emit('include')">Include</button>
      </div>
      <div v-else class="info-box">
        <p>You are in <strong>View Mode</strong>. Only Owners and Reviewers can vote on articles.</p>
      </div>

      <!-- Team Consensus Section -->
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

      <!-- AI Suggestion Panel -->
      <div class="ai-panel">
        <h3>Suggest with AI</h3>
        <div v-if="canReview" class="inline-actions">
          <button class="primary" :disabled="aiLoading" @click="emit('suggest-ai')">
            {{ aiLoading ? 'Generating suggestion...' : 'Suggest with AI' }}
          </button>
        </div>

        <div v-if="aiSuggestion" class="ai-result">
          <p><strong>Provider:</strong> OpenAI</p>
          <p><strong>Suggestion:</strong> {{ aiSuggestion.recommendation }}</p>
          <p><strong>Rationale:</strong> {{ aiSuggestion.rationale || 'No rationale provided' }}</p>
        </div>
      </div>

      <!-- Discussion Panel -->
      <div class="discussion-panel">
        <div class="discussion-head">
          <div>
            <h3>Paper Discussion</h3>
            <p>Team chat to discuss strengths, concerns, and decisions about this article.</p>
          </div>
          <span class="status-pill source">{{ discussionMessages.length }} messages</span>
        </div>

        <div v-if="discussionLoading" class="discussion-empty">
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
            :value="discussionMessage"
            @input="emit('update:discussionMessage', $event.target.value)"
            rows="3"
            placeholder="Write a comment for the team about this paper"
            @keydown.ctrl.enter.prevent="emit('send-message')"
          />
          <div class="inline-actions">
            <button class="primary" :disabled="discussionSending" @click="emit('send-message')">
              {{ discussionSending ? 'Sending...' : 'Send message' }}
            </button>
          </div>
        </div>
      </div>

      <footer class="review-nav">
        <button class="ghost" :disabled="reviewIndex === 0" @click="emit('previous')">< Previous</button>
        <span>Article {{ reviewIndex + 1 }} of {{ reviewResultsLength }}</span>
        <button class="ghost" :disabled="reviewIndex >= reviewResultsLength - 1" @click="emit('next')">Next ></button>
      </footer>
    </article>

    <article v-else class="empty-articles">
      There are no articles available to review in this project.
    </article>
  </section>
</template>
