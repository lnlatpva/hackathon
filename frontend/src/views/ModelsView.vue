<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { api, errorMessage } from '../api/client'
import type { ProductionGraph, ProductionModel, StateType } from '../api/types'
import { createNode, blankGraph, STATE_LABELS } from '../lib/graph'
import StatusBadge from '../components/StatusBadge.vue'
import EmptyState from '../components/EmptyState.vue'
import { Plus, Search, ArrowUpRight, Workflow, Layers3, Boxes, FilePlus2, ArrowRight, FlaskConical, Factory, X, LoaderCircle, Network, Trash2 } from 'lucide-vue-next'
const router = useRouter(); const auth = useAuthStore()
const list = ref<ProductionModel[]>([]); const loading = ref(true); const error = ref(''); const saving = ref(false)
const search = ref(''); const filter = ref<'all'|'draft'|'published'>('all'); const modal = ref(false)
const deleteTarget = ref<ProductionModel | null>(null); const deleteTyped = ref(''); const deleting = ref(false)
const name = ref(''); const stateType = ref<StateType>('current'); const template = ref<'empty'|'factory'|'synthetic'>('empty')
// Объединяем версии по family_id: одна модель отображается одной карточкой.
const displayed = computed(() => {
  const grouped = new Map<string, ProductionModel[]>()
  for (const model of list.value) {
    const versions = grouped.get(model.family_id) || []
    versions.push(model)
    grouped.set(model.family_id, versions)
  }
  return [...grouped.entries()].map(([familyId, versions]) => {
    const all = versions.sort((a, b) => b.version - a.version)
    const matches = all.filter(v => filter.value === 'all' || v.status === filter.value)
    return { familyId, latest: all[0]!, versions: matches }
  }).filter(group => group.versions.length > 0 &&
    `${group.latest.name} ${group.familyId} ${group.versions.map(v => v.name).join(' ')}`.toLowerCase().includes(search.value.toLowerCase()))
    .sort((a, b) => a.latest.name.localeCompare(b.latest.name, 'ru'))
})
const uniqueFamilies = computed(() => new Set(list.value.map(m => m.family_id)).size)
const publishedCount = computed(() => list.value.filter(m => m.status === 'published').length)
async function refresh() { loading.value = true; error.value = ''; try { list.value = await api.models() } catch (e) { error.value = errorMessage(e) } finally { loading.value = false } }
onMounted(refresh)
const factoryNames = [
 'Сборка корпуса пилота и крышки нижней', 'Сборка корпуса управления и крышки верхней', 'Сборка дросселя',
 'Установка тарелки и дросселя', 'Сборка мембраны', 'Сборка пробки', 'Сборка пульта управления',
 'Установка 6 болтов в пульт управления', 'Установка штуцеров и патрубка', 'Контроль качества ОТК',
]
function factorySkeleton(): ProductionGraph {
 const graph = blankGraph('factory-draft')
 graph.nodes = factoryNames.map((title, i) => ({...createNode(i === 9 ? 'inspection' : 'operation',i), id:`WS${i+1}`, name:`РМ ${i+1} · ${title}`}))
 return graph
}
async function create() {
  if (!name.value.trim()) return
  saving.value = true; error.value = ''
  try {
    let graph: ProductionGraph | undefined
    if (template.value === 'factory') graph = factorySkeleton()
    if (template.value === 'synthetic') { const response = await fetch('/demo_graph.json'); if (!response.ok) throw new Error('Не найден демо-файл'); graph = await response.json() as ProductionGraph }
    const created = await api.createModel({ name: name.value.trim(), state_type: stateType.value, ...(graph ? { graph } : {}) })
    modal.value = false
    router.push({ name: 'editor', params: { id: created.id } })
  } catch (e) { error.value = errorMessage(e) } finally { saving.value = false }
}
function openCreate() { name.value=''; stateType.value='current'; template.value='empty'; error.value=''; modal.value = true }
function requestDelete(model: ProductionModel) { deleteTarget.value = model; deleteTyped.value=''; error.value='' }
// Удаление всех версий допускается только после подтверждения точного названия.
async function removeFamily() {
  const target = deleteTarget.value
  if (!target || deleteTyped.value !== target.name || deleting.value) return
  deleting.value = true; error.value = ''
  try {
    await api.deleteModel(target.id, deleteTyped.value)
    deleteTarget.value = null; deleteTyped.value = ''
    await refresh()
  } catch (e) { error.value = errorMessage(e) }
  finally { deleting.value = false }
}

</script>
<template>
  <div class="page-page">
    <div class="page-header"><div><div class="eyebrow"><span class="tiny-circle"/> РАБОЧЕЕ ПРОСТРАНСТВО</div><h1>Модели производства</h1><p class="page-description">Создавайте цифровые модели, исследуйте процессы и проверяйте изменения до их внедрения.</p></div><button v-if="auth.isEditor" class="button primary" @click="openCreate"><Plus :size="17"/> Новая модель</button></div>
    <div class="overview-grid"><div class="overview-card"><div class="overview-icon purple"><Boxes :size="21" /></div><div><strong>{{ uniqueFamilies }}</strong><span>Производственных моделей</span></div></div><div class="overview-card"><div class="overview-icon blue"><Layers3 :size="21" /></div><div><strong>{{ list.length }}</strong><span>Версий процессов</span></div></div><div class="overview-card"><div class="overview-icon green"><Workflow :size="21" /></div><div><strong>{{ publishedCount }}</strong><span>Опубликованных версий</span></div></div></div>
    <div class="section-row"><div><h2>Все модели <span class="count-pill">{{ displayed.length }}</span></h2><p class="section-sub">Ваши производственные процессы и их версии</p></div></div>
    <div class="toolbar-row"><div class="searchbox"><Search :size="18"/><input v-model="search" placeholder="Найти модель по названию..." aria-label="Поиск модели" /></div><div class="seg-tabs"><button :class="{active:filter==='all'}" @click="filter='all'">Все</button><button :class="{active:filter==='draft'}" @click="filter='draft'">Черновики</button><button :class="{active:filter==='published'}" @click="filter='published'">Опубликовано</button></div></div>
    <div v-if="error && !modal" class="alert error-alert">{{ error }}</div>
    <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22"/> Загружаем модели...</div>
    <EmptyState v-else-if="!displayed.length" :title="list.length ? 'По вашему запросу ничего не найдено' : 'Пока нет моделей'" :text="list.length ? 'Попробуйте изменить строку поиска или фильтр.' : 'Создайте производственный процесс, чтобы начать работу с цифровым двойником.'"><button v-if="auth.isEditor && !list.length" class="button primary" @click="openCreate"><Plus :size="17"/> Создать первую модель</button></EmptyState>
        <div v-else class="models-grid">
      <article v-for="group in displayed" :key="group.familyId" class="model-card">
        <div class="model-card-top"><div class="model-symbol"><Network :size="23" /></div><StatusBadge :status="group.latest.status" /></div>
        <h3>{{ group.latest.name }}</h3>
        <p>{{ STATE_LABELS[group.latest.state_type] }} состояние производственного процесса</p>
        <div class="model-stats"><div><strong>{{ group.latest.graph.nodes.length }}</strong><span>операций / узлов (последняя версия)</span></div><div><strong>{{ group.latest.graph.edges.length }}</strong><span>связей</span></div></div>
        <div class="family-versions"><strong>Версии модели</strong><div class="family-version-buttons">
          <button v-for="version in group.versions" :key="version.id" class="family-version-button" @click="router.push({name:'editor',params:{id:version.id}})">
            Версия {{ version.version }} · {{ version.status === 'draft' ? 'черновик' : 'опубликована' }} <ArrowUpRight :size="15" />
          </button>
        </div></div>
        <div class="model-card-bottom"><span>{{ group.versions.length }} {{ group.versions.length === 1 ? 'версия в фильтре' : 'версии в фильтре' }}</span>
          <button v-if="auth.user?.role === 'administrator'" class="button danger-outline compact" :aria-label="`Удалить модель ${group.latest.name}`" @click="requestDelete(group.latest)"><Trash2 :size="15" /> Удалить</button>
        </div>
      </article>
    </div>
    <div class="info-banner"><div class="banner-icon"><FlaskConical :size="22" /></div><div><strong>Фабрика процессов — пилотный кейс</strong><p>Можно создать каркас из 10 рабочих мест на основе учебных материалов. Время и технологические связи останутся неизвестными, пока их не подтвердят.</p></div><button v-if="auth.isEditor" class="button secondary" @click="openCreate(); template='factory'; name='Фабрика процессов — сборка пульта'">Создать каркас <ArrowRight :size="16" /></button></div>
    <div v-if="deleteTarget" class="modal-backdrop" @click.self="deleteTarget=null"><div class="modal-card" role="dialog" aria-modal="true" aria-label="Удаление модели">
      <h2>Удалить модель навсегда?</h2>
      <p class="muted">Будут безвозвратно удалены <strong>все версии</strong> модели «{{ deleteTarget.name }}», их сценарии и история расчётов. Архивирования и восстановления через интерфейс нет.</p>
      <p class="muted">Чтобы подтвердить удаление, введи точное название модели:</p>
      <label class="field-label" for="confirm-model-name">{{ deleteTarget.name }}</label>
      <input id="confirm-model-name" v-model="deleteTyped" class="field-input" autocomplete="off" />
      <div v-if="error" class="alert error-alert">{{error}}</div>
      <div class="modal-actions"><button class="button ghost" @click="deleteTarget=null;error=''">Отмена</button><button class="button danger-outline" :disabled="deleting||deleteTyped!==deleteTarget?.name" @click="removeFamily"><Trash2 :size="16"/> {{deleting?'Удаление...':'Удалить навсегда'}}</button></div>
    </div></div>
    <div v-if="modal" class="modal-backdrop" @click.self="modal=false"><div class="modal-card" role="dialog" aria-modal="true" aria-label="Новая модель"><div class="modal-heading"><div class="modal-icon"><FilePlus2 :size="22" /></div><button class="icon-btn" aria-label="Закрыть" @click="modal=false"><X :size="19"/></button></div><h2>Новая модель</h2><p class="muted">Выберите основу для производственного процесса.</p><form @submit.prevent="create"><label class="field-label" for="model-name">Название</label><input id="model-name" v-model="name" class="field-input" required maxlength="220" placeholder="Например, Сборочная линия №1"/><label class="field-label">Состояние процесса</label><select v-model="stateType" class="field-input"><option value="current">Текущее</option><option value="ideal">Идеальное</option><option value="target">Целевое</option></select><label class="field-label">Основа модели</label><div class="template-options"><label :class="{active:template==='empty'}"><input v-model="template" type="radio" value="empty"/><Boxes :size="20"/><span><strong>С нуля</strong><small>Пустая схема</small></span></label><label :class="{active:template==='factory'}"><input v-model="template" type="radio" value="factory"/><Factory :size="20"/><span><strong>Фабрика процессов</strong><small>10 рабочих мест, без замеров</small></span></label><label :class="{active:template==='synthetic'}"><input v-model="template" type="radio" value="synthetic"/><FlaskConical :size="20"/><span><strong>Демо</strong><small>Синтетические тестовые числа</small></span></label></div><div v-if="error" class="alert error-alert">{{ error }}</div><div class="modal-actions"><button type="button" class="button ghost" @click="modal=false">Отмена</button><button class="button primary" :disabled="saving || !name.trim()" type="submit">{{ saving ? 'Создание...' : 'Создать модель' }}<ArrowRight :size="17"/></button></div></form></div></div>
  </div>
</template>
