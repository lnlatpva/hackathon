<script setup lang="ts">
import { Inbox } from 'lucide-vue-next'
defineProps<{ title: string; text: string }>()
</script>
<template><div class="empty-state"><div class="empty-icon"><Inbox :size="25" /></div><h3>{{ title }}</h3><p>{{ text }}</p><slot /></div></template>
