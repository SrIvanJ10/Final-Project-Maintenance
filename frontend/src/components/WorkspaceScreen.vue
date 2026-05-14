<script setup>
import { roleLabel } from '../utils/formatters.js'

defineProps({
  selectedProject: { type: Object, required: true },
  canReview: { type: Boolean, default: false },
  isOwner: { type: Boolean, default: false },
  drafts: { type: Object, required: true },
  generatingReport: { type: Boolean, default: false },
  generatedReport: { type: String, default: null },
  totalCount: { type: Number, default: 0 },
  pendingCount: { type: Number, default: 0 },
})

const emit = defineEmits(['save-criteria', 'add-collaborator', 'generate-report', 'back'])
</script>

<template>
  <div class="workspace-screen">
    <button class="back-link" @click="emit('back')">< Back to Projects</button>

    <h1>{{ selectedProject.title }}</h1>
    <p class="workspace-description">{{ selectedProject.description || 'No description' }}</p>

    <!-- Inclusion Criteria Panel -->
    <section class="workspace-panel">
      <div class="query-tab">
        <h2>Inclusion Criteria (PRISMA 2020)</h2>
        <textarea
          v-model="drafts.projectInclusionCriteriaEdit"
          rows="8"
          placeholder="Define the project inclusion criteria"
        />
        <div v-if="canReview" class="inline-actions">
          <button class="primary" @click="emit('save-criteria')">Save Criteria</button>
        </div>
      </div>
    </section>

    <!-- Team Panel -->
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
        <div v-if="isOwner" class="inline-actions">
          <input
            v-model="drafts.collaboratorQuery"
            placeholder="collaborator username"
            @keydown.enter.prevent="emit('add-collaborator')"
          />
          <select v-model="drafts.collaboratorRole">
            <option value="reviewer">Reviewer</option>
            <option value="viewer">Viewer</option>
            <option value="advisor">Advisor</option>
          </select>
          <button class="primary" @click="emit('add-collaborator')">Add collaborator</button>
        </div>
      </div>
    </section>

    <!-- AI Report Panel -->
    <section class="workspace-panel" v-if="selectedProject.status === 'completed' || (totalCount > 0 && pendingCount === 0)">
      <div class="query-tab">
        <h2>Generate AI Report</h2>
        <p class="hint">The screening phase is finished. You can now generate an automated review report based on the included articles.</p>
        <textarea v-model="drafts.reportPrompt" rows="3" placeholder="Enter custom instructions for the LLM report..."></textarea>
        <div class="inline-actions">
          <button class="primary" :disabled="generatingReport" @click="emit('generate-report')">
            {{ generatingReport ? 'Generating...' : 'Generate Report' }}
          </button>
        </div>
        <div v-if="generatedReport" class="report-result" style="margin-top: 1rem; padding: 1rem; background: var(--bg-surface); border: 1px solid var(--border-color); border-radius: 4px; white-space: pre-wrap; font-family: monospace;">
          {{ generatedReport }}
        </div>
      </div>
    </section>

    <slot name="stats"></slot>
    <slot name="tabs"></slot>
  </div>
</template>
