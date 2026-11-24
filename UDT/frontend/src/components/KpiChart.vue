<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { EChartsCoreOption, EChartsType } from 'echarts/core'
echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])
const props = defineProps<{ option: EChartsCoreOption; height?: number }>()
const chart = ref<HTMLElement | null>(null)
let instance: EChartsType | undefined
let observer: ResizeObserver | undefined
function render() { if (!instance && chart.value) instance = echarts.init(chart.value); instance?.setOption(props.option, { notMerge: true }) }
onMounted(async () => { await nextTick(); render(); if (chart.value) { observer = new ResizeObserver(() => instance?.resize()); observer.observe(chart.value) } })
watch(() => props.option, render, { deep: true })
onBeforeUnmount(() => { observer?.disconnect(); instance?.dispose(); instance = undefined })
</script>
<template><div ref="chart" class="kpi-chart" :style="{height: `${height || 300}px`}" role="img" aria-label="График производственных показателей" /></template>
