<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { Boxes, ArrowRight, Eye, EyeOff, LockKeyhole, Factory, Network, TrendingUp, CheckCircle2 } from 'lucide-vue-next'
import { errorMessage } from '../api/client'
const router = useRouter(); const route = useRoute(); const auth = useAuthStore()
const login = ref(''); const password = ref(''); const showPassword = ref(false); const setup = ref(false)
const busy = ref(false); const error = ref('')
const canSubmit = computed(() => login.value.trim().length >= 3 && password.value.length >= (setup.value ? 12 : 1))
async function submit() {
  if (!canSubmit.value || busy.value) return
  busy.value = true; error.value = ''
  try { await auth.login(login.value.trim(), password.value, setup.value); await router.replace(typeof route.query.redirect === 'string' ? route.query.redirect : '/models') }
  catch (e) { error.value = errorMessage(e) }
  finally { busy.value = false }
}
</script>
<template>
  <div class="login-layout">
    <div class="login-showcase">
      <div class="login-brand"><span class="login-brand-mark"><Boxes :size="28" /></span><div>UDT<span class="brand-dot">.</span><small>UNIVERSAL DIGITAL TWIN</small></div></div>
      <div class="login-message"><div class="eyebrow light"><span class="tiny-circle" /> ПРОИЗВОДСТВО В ЦИФРАХ</div><h1>Видеть процессы.<br /><em>Понимать ограничения.</em><br />Управлять изменениями.</h1><p>Единое пространство для моделирования производственных процессов, поиска узких мест и оценки сценариев оптимизации.</p></div>
      <div class="showcase-features"><div><Factory :size="21"/><span>Модель производства</span></div><div><Network :size="21"/><span>Граф операций</span></div><div><TrendingUp :size="21"/><span>Аналитика KPI</span></div></div>
      <div class="showcase-watermark">UDT / 2026</div>
    </div>
    <div class="login-form-wrap">
      <form class="login-form" @submit.prevent="submit">
        <div class="login-form-top"><div class="login-small-logo"><Boxes :size="22" /></div><span>ВЕБ-ПЛАТФОРМА UDT</span></div>
        <div class="eyebrow">{{ setup ? 'ПЕРВОНАЧАЛЬНАЯ НАСТРОЙКА' : 'С ВОЗВРАЩЕНИЕМ' }}</div>
        <h2>{{ setup ? 'Создать администратора' : 'Войти в систему' }}</h2>
        <p class="form-description">{{ setup ? 'Доступно только для новой базы при включённом UDT_ALLOW_SETUP.' : 'Авторизуйтесь для доступа к производственным моделям и аналитике.' }}</p>
        <label class="field-label" for="login">Логин</label>
        <input id="login" v-model="login" class="field-input" autocomplete="username" placeholder="Введите логин" autofocus required minlength="3" />
        <label class="field-label" for="password">Пароль</label>
        <div class="input-with-icon"><input id="password" v-model="password" :type="showPassword ? 'text' : 'password'" class="field-input" autocomplete="current-password" placeholder="Введите пароль" required :minlength="setup ? 12 : 1" /><button type="button" aria-label="Показать пароль" @click="showPassword = !showPassword"><EyeOff v-if="showPassword" :size="18"/><Eye v-else :size="18"/></button></div>
        <div v-if="error" role="alert" class="alert error-alert">{{ error }}</div>
        <button class="button primary login-submit" type="submit" :disabled="!canSubmit || busy"><span>{{ busy ? 'Подключение...' : setup ? 'Создать администратора' : 'Войти в UDT' }}</span><ArrowRight :size="18" /></button>
        <div class="login-mode-switch"><button type="button" @click="setup = !setup; error = ''">{{ setup ? 'Вернуться ко входу' : 'Первый запуск? Создать администратора' }}</button></div>
        <div class="security-note"><LockKeyhole :size="15" /> Сессия хранится в текущей вкладке браузера</div>
      </form>
      <div class="login-legal"><CheckCircle2 :size="16" /> Учебный MVP · Направление А · Фабрика процессов</div>
    </div>
  </div>
</template>
