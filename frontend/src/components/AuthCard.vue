<script setup>
import { AUTH_MODES } from '../constants.js'

const props = defineProps({
  auth: { type: Object, required: true },
  status: { type: String, default: '' },
})

const emit = defineEmits(['login', 'register'])

function onSubmit() {
  emit(props.auth.mode === AUTH_MODES.LOGIN ? 'login' : 'register')
}

function toggleMode() {
  props.auth.mode = props.auth.mode === AUTH_MODES.LOGIN ? AUTH_MODES.REGISTER : AUTH_MODES.LOGIN
}
</script>

<template>
  <section class="auth-card">
    <h1>Mnemosyne</h1>
    <p class="subtitle">
      {{ auth.mode === 'login'
        ? 'Sign in to manage your systematic reviews.'
        : 'Create your account to start working on your systematic reviews.' }}
    </p>
    <p class="status-label">{{ status }}</p>
    <form class="auth-form" @submit.prevent="onSubmit">
      <label>
        Username
        <input v-model="auth.username" required />
      </label>
      <label v-if="auth.mode === 'register'">
        Email
        <input v-model="auth.email" type="email" required />
      </label>
      <label>
        Password
        <input v-model="auth.password" type="password" required />
      </label>
      <button type="submit">
        {{ auth.mode === 'login' ? 'Sign in' : 'Create account' }}
      </button>
      <button type="button" class="ghost" @click="toggleMode">
        {{ auth.mode === 'login' ? 'Create an account' : 'I already have an account' }}
      </button>
    </form>
  </section>
</template>
