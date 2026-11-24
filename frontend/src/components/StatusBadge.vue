<script setup lang="ts">
defineProps<{ status: string }>()
const labels: Record<string, string> = { draft: 'Черновик', published: 'Опубликовано', current: 'Текущее', ideal: 'Идеальное', target: 'Целевое', calculated: 'Рассчитано', estimated: 'Оценка', unavailable: 'Нет данных' }
</script>
<template><span class="status-badge" :class="`status-${status}`"><span class="status-dot"/>{{ labels[status] || status }}</span></template>
