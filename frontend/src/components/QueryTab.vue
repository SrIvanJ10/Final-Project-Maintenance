<script setup>
import { SOURCES } from '../constants.js'

defineProps({
  sourceType: String,
  drafts: Object,
  canReview: Boolean,
})

const emit = defineEmits(['change-source', 'save-query', 'run-semantic', 'import-scopus'])
</script>

<template>
  <div class="query-tab">
    <h2>Search Configuration</h2>

    <label>
      Source
      <select :value="sourceType" @change="emit('change-source', $event.target.value)">
        <option :value="SOURCES.SCOPUS">SCOPUS</option>
        <option :value="SOURCES.SEMANTIC">Semantic Scholar</option>
      </select>
    </label>

    <template v-if="sourceType === SOURCES.SCOPUS">
      <label>
        SCOPUS Search Query
        <textarea
          v-model="drafts.scopusQuery"
          rows="5"
          placeholder='E.g.: TITLE-ABS-KEY("machine learning" AND "healthcare") AND PUBYEAR > 2019'
        />
      </label>
      <p class="hint">Define your search query using SCOPUS syntax</p>
      <button v-if="canReview" class="primary" @click="emit('save-query')">Save Query</button>

      <hr />

      <h3>Upload SCOPUS Results</h3>
      <p class="info-box">
        <strong>Instructions:</strong> Export the results from SCOPUS in CSV format and upload them here. The file should include columns such as Title, Authors, Year, Abstract, DOI, etc.
      </p>
      <label v-if="canReview" class="upload-btn">
        Upload CSV File
        <input type="file" accept=".csv,.json,application/json,text/csv" @change="emit('import-scopus', $event)" />
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
      <div v-if="canReview" class="inline-actions">
        <button class="primary" @click="emit('save-query')">Save Configuration</button>
        <button class="success" @click="emit('run-semantic')">Search in Semantic Scholar</button>
      </div>
    </template>
  </div>
</template>
