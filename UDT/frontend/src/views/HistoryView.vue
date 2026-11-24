<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, errorMessage } from '../api/client'
import type { CalculationRun, ProductionModel } from '../api/types'
import EmptyState from '../components/EmptyState.vue'
import { History, ChevronRight, FileJson2, Clock3, LockKeyhole, CircleAlert, LoaderCircle, Copy, Check } from 'lucide-vue-next'
const route=useRoute(), id=computed(()=>String(route.params.id))
const model=ref<ProductionModel|null>(null),runs=ref<CalculationRun[]>([]),selected=ref<CalculationRun|null>(null),loading=ref(true),error=ref(''),copied=ref(false)
async function load(){loading.value=true;error.value='';try{model.value=await api.model(id.value);runs.value=await api.runs(id.value);selected.value=runs.value[0]||null}catch(e){error.value=errorMessage(e)}finally{loading.value=false}}
onMounted(load);watch(id,load)
function stamp(s:string){return new Date(s).toLocaleString('ru-RU',{day:'2-digit',month:'long',year:'numeric',hour:'2-digit',minute:'2-digit'})}
function count(run:CalculationRun){return Object.values(run.result.metrics).filter(m=>m.status!=='unavailable').length}
function display(value: string | number | null){if(value===null)return '—';const n=Number(value);return Number.isFinite(n)?new Intl.NumberFormat('ru-RU',{maximumFractionDigits:3}).format(n):String(value)}
async function copyHash(hash:string){await navigator.clipboard.writeText(hash);copied.value=true;setTimeout(()=>copied.value=false,1800)}
</script>
<template>
 <div class="page-page"><div class="page-header"><div><div class="eyebrow"><span class="tiny-circle"/> ВОСПРОИЗВОДИМОСТЬ</div><h1>История расчётов</h1><p class="page-description">Снимки входных параметров, рассчитанные KPI и история экспериментов по модели {{model?.name||''}}.</p></div></div>
 <div v-if="error" class="alert error-alert"><CircleAlert :size="17"/> {{error}}</div>
 <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22"/> Загрузка истории...</div>
 <template v-else><div v-if="!runs.length" class="panel"><EmptyState title="История пока пуста" text="После первого расчёта здесь появятся его параметры, KPI и контрольный хеш входных данных."/></div><div v-else class="history-layout"><div class="panel history-table"><div class="panel-heading"><div><h2>Все запуски</h2><p>{{runs.length}} сохранённых расчётов</p></div><History :size="20"/></div><button v-for="run in runs" :key="run.id" class="history-item" :class="{active:selected?.id===run.id}" @click="selected=run"><div class="history-icon"><Clock3 :size="18"/></div><div><strong>{{stamp(run.created_at)}}</strong><small>{{run.scenario_id?'Сценарный':'Базовый'}} · {{count(run)}} доступных KPI</small></div><ChevronRight :size="18"/></button></div><div v-if="selected" class="panel history-details"><div class="panel-heading"><div><h2>Детали расчёта</h2><p>{{stamp(selected.created_at)}}</p></div><LockKeyhole :size="19"/></div><div class="history-hash"><small>SHA-256 входных данных</small><div><code>{{selected.input_hash}}</code><button class="icon-btn" aria-label="Копировать хеш" @click="copyHash(selected.input_hash)"><Check v-if="copied" :size="16"/><Copy v-else :size="16"/></button></div></div><div class="field-divider"><FileJson2 :size="17"/> Результаты KPI</div><div class="metric-list"><div v-for="(metric,key) in selected.result.metrics" :key="key" class="metric-list-row"><div><span>{{key}}</span><small v-if="metric.status==='unavailable'" :title="metric.reasons.join('; ')">Недостаточно данных</small><small v-else>{{metric.kind}}</small></div><div><strong>{{display(metric.value)}}</strong><small>{{metric.unit||'—'}}</small></div></div></div><details class="snapshot-details"><summary>Посмотреть снимок входных данных</summary><pre>{{JSON.stringify(selected.input_snapshot,null,2)}}</pre></details><details class="snapshot-details"><summary>Посмотреть полный результат расчёта</summary><pre>{{JSON.stringify(selected.result,null,2)}}</pre></details></div></div></template>
 </div>
</template>
