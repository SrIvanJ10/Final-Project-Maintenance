<script setup>
defineProps({
  totalCount: Number,
  includedCount: Number,
  excludedCount: Number,
  pendingCount: Number,
})
</script>

<template>
  <section class="stats-grid">
    <article class="stat-card">
      <h3>Total</h3>
      <strong>{{ totalCount }}</strong>
    </article>
    <article class="stat-card green">
      <h3>Included</h3>
      <strong>{{ includedCount }}</strong>
    </article>
    <article class="stat-card red">
      <h3>Excluded</h3>
      <strong>{{ excludedCount }}</strong>
    </article>
    <article class="stat-card yellow">
      <h3>Pending</h3>
      <strong>{{ pendingCount }}</strong>
    </article>
  </section>
</template>
