<script setup>
defineProps({
  msg: { type: String, default: '' },
  err: { type: String, default: '' },
})

const emit = defineEmits(['dismiss'])
</script>

<template>
  <div v-if="msg || err" class="toast-stack">
    <div v-if="msg" class="toast toast-ok">
      <span>{{ msg }}</span>
      <button type="button" class="toast-close" @click="emit('dismiss')">×</button>
    </div>
    <div v-if="err" class="toast toast-error">
      <span>{{ err }}</span>
      <button type="button" class="toast-close" @click="emit('dismiss')">×</button>
    </div>
  </div>
</template>
