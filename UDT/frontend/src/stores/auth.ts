import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api, TOKEN_KEY } from '../api/client'
import type { CurrentUser } from '../api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<CurrentUser | null>(null)
  const token = ref(sessionStorage.getItem(TOKEN_KEY))
  const isLoggedIn = computed(() => Boolean(token.value))
  const isEditor = computed(() => user.value?.role === 'administrator' || user.value?.role === 'technologist')
  const canCalculate = computed(() => user.value?.role !== 'observer' && Boolean(user.value))
  async function loadUser() { user.value = await api.me(); return user.value }
  async function login(login: string, password: string, setup = false) {
    const credentials = setup ? await api.setup(login, password) : await api.login(login, password)
    sessionStorage.setItem(TOKEN_KEY, credentials.access_token)
    token.value = credentials.access_token
    try { await loadUser() } catch (error) { logout(); throw error }
  }
  function logout() {
    sessionStorage.removeItem(TOKEN_KEY)
    token.value = null
    user.value = null
  }
  return { user, token, isLoggedIn, isEditor, canCalculate, loadUser, login, logout }
})
