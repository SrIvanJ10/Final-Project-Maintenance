<script setup>
defineProps({
  projects: { type: Array, required: true },
})

const emit = defineEmits(['open-project', 'open-modal'])
</script>

<template>
  <section class="projects-screen">
    <header class="hero">
      <h1>Systematic Literature Reviews</h1>
      <p>Manage your systematic review projects and the inclusion/exclusion process</p>
      <button class="primary large" @click="emit('open-modal')">+ New Project</button>
    </header>

    <div v-if="!projects.length" class="empty-projects">
      <div class="folder-icon">[ ]</div>
      <h2>No projects yet</h2>
      <p>Create your first systematic review project</p>
      <button class="primary" @click="emit('open-modal')">+ Create Project</button>
    </div>

    <div v-else class="project-grid">
      <article
        v-for="project in projects"
        :key="project.id"
        class="project-card"
        @click="emit('open-project', project)"
      >
        <div>
          <h3>{{ project.title }}</h3>
          <p>{{ project.description || 'No description' }}</p>
        </div>
        <span class="open-link">Open project ></span>
      </article>
    </div>
  </section>
</template>
