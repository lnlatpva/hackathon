<script setup lang="ts">
import { computed } from 'vue'
import { CircleHelp, ArrowUpRight } from 'lucide-vue-next'
import type { Metric } from '../api/types'
const props = defineProps<{ title: string; metric?: Metric | null; symbol?: string; hint?: string }>()
const formatted = computed(() => {
  if (!props.metric || props.metric.value === null) return '—'
  const numeric = Number(props.metric.value)
  if (!Number.isFinite(numeric)) return String(props.metric.value)
  return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(numeric)
})
</script>
<template>
  <article class="metric-card"><div class="metric-card-top"><span>{{ title }}</span><CircleHelp :size="15" :title="hint || metric?.reasons?.join('; ') || 'Показатель расчёта'" /></div><div class="metric-card-number">{{ formatted }} <small v-if="metric?.value !== null && metric?.value !== undefined">{{ symbol || metric?.unit }}</small></div><div class="metric-card-footer"><span class="small-status" :class="metric?.status || 'unavailable'"><span class="status-dot"/>{{ metric?.status === 'unavailable' || !metric ? 'Недостаточно данных' : metric.status === 'estimated' ? 'Расчётная оценка' : 'Рассчитано' }}</span><ArrowUpRight :size="16" /></div></article>
</template>
