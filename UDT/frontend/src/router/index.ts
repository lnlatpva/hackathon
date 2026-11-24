import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/models' },
    { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
    { path: '/models', name: 'models', component: () => import('../views/ModelsView.vue') },
    { path: '/models/:id/editor', name: 'editor', component: () => import('../views/EditorView.vue') },
    { path: '/models/:id/analytics', name: 'analytics', component: () => import('../views/AnalyticsView.vue') },
    { path: '/models/:id/scenarios', name: 'scenarios', component: () => import('../views/ScenariosView.vue') },
    { path: '/models/:id/history', name: 'history', component: () => import('../views/HistoryView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/models' },
  ],
})
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.meta.public) return auth.isLoggedIn && auth.user ? '/models' : true
  if (!auth.isLoggedIn) return { name: 'login', query: { redirect: to.fullPath } }
  if (!auth.user) {
    try { await auth.loadUser() } catch { auth.logout(); return { name: 'login', query: { redirect: to.fullPath } } }
  }
  return true
})
