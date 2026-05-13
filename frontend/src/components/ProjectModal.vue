<script setup>
defineProps({
  projectName: { type: String, default: '' },
  projectDescription: { type: String, default: '' },
})

const emit = defineEmits([
  'update:projectName',
  'update:projectDescription',
  'create',
  'close',
])
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="modal-card">
      <h2>New Project</h2>
      <label>
        Project Name
        <input
          :value="projectName"
          @input="emit('update:projectName', $event.target.value)"
          placeholder="E.g.: Machine Learning in Healthcare Review"
        />
      </label>
      <label>
        Description (optional)
        <textarea
          :value="projectDescription"
          @input="emit('update:projectDescription', $event.target.value)"
          rows="4"
          placeholder="Describe the goal of your systematic review"
        />
      </label>
      <p class="hint">
        When you create the project, an Inclusion Criteria proposal (PRISMA 2020) will be
        generated automatically using the configured LLM. You can review and edit it afterwards.
      </p>
      <div class="modal-actions">
        <button class="ghost" @click="emit('close')">Cancel</button>
        <button class="primary" :disabled="!projectName.trim()" @click="emit('create')">Create</button>
      </div>
    </div>
  </div>
</template>
