<script setup>
import { sourceLabel, formatAuthors } from '../utils/formatters.js'
import { relevanceClass, relevanceTag, consensusLabel } from '../utils/relevance.js'
import { SOURCE_FILTERS, DECISION_FILTERS } from '../constants.js'

defineProps({
  currentResults: Array,
  articleSourceFilter: String,
  articleDecisionFilter: String,
  canReview: Boolean,
  currentPendingCount: Number,
})

const emit = defineEmits(['update:articleSourceFilter', 'update:articleDecisionFilter', 'export', 'start-review'])
</script>

<template>
  <div class="articles-tab">
    <div class="articles-header">
      <h2>Article List</h2>
      <div class="inline-actions">
        <label class="source-filter">
          Source
          <select :value="articleSourceFilter" @input="emit('update:articleSourceFilter', $event.target.value)">
            <option :value="SOURCE_FILTERS.ALL">All</option>
            <option :value="SOURCE_FILTERS.SCOPUS">SCOPUS</option>
            <option :value="SOURCE_FILTERS.SEMANTIC">Semantic Scholar</option>
          </select>
        </label>
        <label class="source-filter">
          Status
          <select :value="articleDecisionFilter" @input="emit('update:articleDecisionFilter', $event.target.value)">
            <option :value="DECISION_FILTERS.ALL">All</option>
            <option :value="DECISION_FILTERS.PENDING">Pending</option>
            <option :value="DECISION_FILTERS.INCLUDED">Included</option>
            <option :value="DECISION_FILTERS.EXCLUDED">Excluded</option>
          </select>
        </label>
        <button class="ghost" @click="emit('export')">Export Results</button>
        <button v-if="canReview" class="success" :disabled="!currentResults.length" @click="emit('start-review')">
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
</template>
