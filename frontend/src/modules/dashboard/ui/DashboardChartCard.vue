<template>
  <a-card class="dashboard-card dashboard-chart-card" :title="title" :loading="loading">
    <template v-if="$slots.extra" #extra><slot name="extra" /></template>
    <div v-if="$slots.summary" class="dashboard-chart-summary"><slot name="summary" /></div>
    <div class="dashboard-chart-content"><slot /></div>
  </a-card>
</template>

<script setup>
defineProps({ title: { type: String, required: true }, loading: Boolean })
</script>

<style scoped>
.dashboard-chart-summary {
  padding-bottom: 18px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--gray-150);
}
.dashboard-chart-content {
  min-width: 0;
}
</style>
