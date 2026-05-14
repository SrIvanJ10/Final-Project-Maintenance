<script setup>
defineProps({
  status: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['refresh', 'logout'])
</script>

<template>
  <header class="top-bar">
    <p class="status-label">{{ status }}</p>
    <div class="top-actions">
      <button class="ghost" @click="emit('refresh')" :disabled="loading">Refresh</button>
      <button class="ghost" @click="emit('logout')">Sign out</button>
    </div>
  </header>
</template>
