<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@xyflow/vue'
import { Settings2, ClipboardCheck, Truck, Package, CircleDot, Flag, TriangleAlert } from 'lucide-vue-next'
import type { GraphNode } from '../api/types'
const props = defineProps<{ data: { node: GraphNode; isCritical?: boolean }; selected?: boolean }>()
const icon = computed(() => ({ operation:Settings2,inspection:ClipboardCheck,transport:Truck,storage:Package,source:CircleDot,sink:Flag })[props.data.node.kind])
const labels = { operation:'ОПЕРАЦИЯ', inspection:'КОНТРОЛЬ',transport:'ЛОГИСТИКА',storage:'ХРАНЕНИЕ',source:'НАЧАЛО ПОТОКА',sink:'КОНЕЦ ПОТОКА' }
</script>
<template>
  <div class="flow-node" :class="{ 'flow-node-selected': selected, 'flow-node-critical': data.isCritical }">
    <Handle type="target" :position="Position.Left" class="flow-handle" />
    <div class="flow-node-top"><span class="flow-node-icon"><component :is="icon" :size="15" /></span><span>{{ labels[data.node.kind] }}</span><TriangleAlert v-if="data.isCritical" :size="15" class="flow-warning" /></div>
    <div class="flow-node-name">{{ data.node.name }}</div>
    <div class="flow-node-bottom"><span>{{ data.node.processing_seconds?.value != null ? `${data.node.processing_seconds.value} с` : 'Время не указано' }}</span><span class="flow-node-code">{{ data.node.id.slice(0, 12) }}</span></div>
    <Handle type="source" :position="Position.Right" class="flow-handle" />
  </div>
</template>
