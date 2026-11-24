<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { LayoutGrid, Workflow, ChartNoAxesCombined, GitCompareArrows, History, LogOut, Menu, X, Boxes, ShieldCheck, CircleHelp, ArrowUpRight } from 'lucide-vue-next'
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const menuOpen = ref(false)
const modelId = computed(() => typeof route.params.id === 'string' ? route.params.id : null)
const inModel = computed(() => Boolean(modelId.value))
const currentPage = computed(() => {
  const pages: Record<string, string> = { models: 'Модели производства', editor: 'Редактор', analytics: 'Аналитика', scenarios: 'Сценарии', history: 'История' }
  return pages[String(route.name)] || 'Рабочее пространство'
})
const links = computed(() => [
  { label: 'Все модели', to: '/models', icon: LayoutGrid },
  ...(modelId.value ? [
    { label: 'Редактор схемы', to: `/models/${modelId.value}/editor`, icon: Workflow },
    { label: 'Аналитика', to: `/models/${modelId.value}/analytics`, icon: ChartNoAxesCombined },
    { label: 'Сценарии', to: `/models/${modelId.value}/scenarios`, icon: GitCompareArrows },
    { label: 'История расчётов', to: `/models/${modelId.value}/history`, icon: History },
  ] : []),
])
const roleLabels: Record<string, string> = { administrator: 'Администратор', technologist: 'Технолог', manager: 'Руководитель', observer: 'Наблюдатель' }
function logout() { auth.logout(); router.replace('/login') }
onMounted(() => window.addEventListener('udt:unauthorized', logout))
onBeforeUnmount(() => window.removeEventListener('udt:unauthorized', logout))
</script>

<template>
  <RouterView v-if="route.name === 'login'" />
  <div v-else class="app-layout">
    <div v-if="menuOpen" class="mobile-scrim" @click="menuOpen = false" />
    <aside class="sidebar" :class="{ 'sidebar-open': menuOpen }">
      <div class="sidebar-brand">
        <div class="brand-mark"><Boxes :size="24" :stroke-width="2.1" /></div>
        <div><div class="brand-name">UDT<span class="brand-dot">.</span></div><div class="brand-sub">UNIVERSAL DIGITAL TWIN</div></div>
        <button class="mobile-close icon-btn" aria-label="Закрыть меню" @click="menuOpen = false"><X :size="19" /></button>
      </div>
      <div class="sidebar-kicker">РАБОЧЕЕ ПРОСТРАНСТВО</div>
      <nav class="nav-list" aria-label="Главная навигация">
        <RouterLink v-for="link in links" :key="link.to" :to="link.to" class="nav-link" :class="{ active: route.path === link.to }" @click="menuOpen = false">
          <component :is="link.icon" :size="19" :stroke-width="1.8" />
          <span>{{ link.label }}</span>
        </RouterLink>
      </nav>
      <div v-if="!inModel" class="sidebar-hint"><div class="hint-icon"><Workflow :size="18" /></div><strong>Цифровая фабрика</strong><span>Создавайте модели процессов и находите ограничения производства.</span></div>
      <div class="sidebar-spacer" />
      <div class="sidebar-footer">
        <div class="sidebar-foot-note"><ShieldCheck :size="15" /> Направление А · MVP</div>
        <div class="profile-card">
          <div class="avatar">{{ (auth.user?.login || 'U').charAt(0).toUpperCase() }}</div>
          <div class="profile-text"><strong>{{ auth.user?.login || 'Пользователь' }}</strong><small>{{ roleLabels[auth.user?.role || 'observer'] }}</small></div>
          <button class="logout-btn" title="Выйти" aria-label="Выйти" @click="logout"><LogOut :size="18" /></button>
        </div>
      </div>
    </aside>
    <main class="main-area">
      <header class="topbar">
        <div class="topbar-left"><button class="mobile-menu icon-btn" aria-label="Открыть меню" @click="menuOpen = true"><Menu :size="21" /></button><span class="topbar-breadcrumb">UDT</span><span class="crumb-separator">/</span><span class="topbar-current">{{ currentPage }}</span></div>
        <div class="topbar-right"><span class="topbar-online"><span class="online-pulse" /> Рабочая среда</span><a href="/docs" target="_blank" rel="noreferrer" class="topbar-docs"><CircleHelp :size="16" /> API <ArrowUpRight :size="13" /></a></div>
      </header>
      <div class="content-frame"><RouterView /></div>
    </main>
  </div>
</template>
