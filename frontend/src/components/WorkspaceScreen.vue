<script setup>
import { roleLabel } from '../utils/formatters.js'

defineProps({
  selectedProject: { type: Object, required: true },
  canReview: { type: Boolean, default: false },
  isOwner: { type: Boolean, default: false },
  drafts: { type: Object, required: true },
})

const emit = defineEmits(['save-criteria', 'add-collaborator', 'back'])
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

    <slot name="stats"></slot>
    <slot name="tabs"></slot>
  </div>
</template>
