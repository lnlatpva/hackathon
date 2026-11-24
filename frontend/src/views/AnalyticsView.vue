<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { EChartsCoreOption } from 'echarts/core'
import { api, errorMessage } from '../api/client'
import type { CalculationRequest, CalculationRun, Metric, ProductionModel } from '../api/types'
import { useAuthStore } from '../stores/auth'
import MetricCard from '../components/MetricCard.vue'
import KpiChart from '../components/KpiChart.vue'
import CalculationForm from '../components/CalculationForm.vue'
import EmptyState from '../components/EmptyState.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { Activity, ChartNoAxesCombined, ArrowRight, CircleAlert, Clock3, AlertTriangle, SlidersHorizontal, ChevronDown, ClipboardList, LoaderCircle } from 'lucide-vue-next'
const route=useRoute(),router=useRouter(),auth=useAuthStore()
const id=computed(()=>String(route.params.id));const model=ref<ProductionModel|null>(null);const runs=ref<CalculationRun[]>([])
const latest=ref<CalculationRun|null>(null);const busy=ref(false);const loading=ref(true);const error=ref('');const showForm=ref(false)
const metrics=computed(()=>latest.value?.result.metrics||{})
const titles:Record<string,string>={
 takt_seconds_per_finished:'Время такта', capacity_upper_bound:'Предел мощности', first_unit_lead_seconds:'Первое изделие',
 customer_quality_percent:'Качество заказчика',actual_utilization_percent:'Загрузка ресурса',downtime_percent:'Доля простоя',availability_percent:'Доступность',
 throughput_accepted_per_second:'Фактический выпуск', inventory_change_currency:'Изменение НЗП',cost_per_accepted_unit:'Себестоимость',profit:'Прибыль',
 cost_per_finished_from_nodes:'Стоимость по операциям',input_takt_seconds:'Введённый такт'
}
function getMetricTitle(code: string | undefined): string {
  if (!code) return 'Показатель'
  return titles[code] ?? code
}
const primaryCodes=['takt_seconds_per_finished','capacity_upper_bound','first_unit_lead_seconds','customer_quality_percent']
const secondaryCodes=['throughput_accepted_per_second','actual_utilization_percent','downtime_percent','availability_percent','inventory_change_currency','cost_per_accepted_unit','profit','cost_per_finished_from_nodes']
const missingCount=computed(()=>Object.values(metrics.value).filter(m=>m.status==='unavailable').length)
const constraints=computed(()=>latest.value?.result.analysis.capacity.constraints||[])
const capacityOption=computed<EChartsCoreOption>(()=>({
 grid:{left:32,right:30,top:24,bottom:65,containLabel:true},tooltip:{trigger:'axis',axisPointer:{type:'shadow'}},
 xAxis:{type:'category',data:constraints.value.map(c=> c.owner_type==='resource' ? `Ресурс: ${c.owner_id}` : model.value?.graph.nodes.find(n=>n.id===c.owner_id)?.name||c.owner_id),axisLabel:{color:'#718096',rotate:25,interval:0,width:115,overflow:'truncate'}},
 yAxis:{type:'value',name:'изделий / период',nameTextStyle:{color:'#8691a6'},axisLabel:{color:'#8792a5'},splitLine:{lineStyle:{color:'#e9edf4'}}},
 series:[{name:'Верхняя оценка',type:'bar',data:constraints.value.map(c=>Number(c.finished_equivalent_capacity)),barMaxWidth:48,itemStyle:{color:'#617cf0',borderRadius:[6,6,0,0]}}]
}))
const trends=computed(()=>runs.value.slice(0,12).reverse().map((r,i)=>({date: new Date(r.created_at).toLocaleDateString('ru-RU',{day:'2-digit',month:'short'}),value:r.result.metrics.capacity_upper_bound?.value===null?null:Number(r.result.metrics.capacity_upper_bound?.value??NaN)})).filter(r=>r.value!==null&&!Number.isNaN(r.value)))
const trendOption=computed<EChartsCoreOption>(()=>({grid:{left:30,right:22,top:20,bottom:24,containLabel:true},tooltip:{trigger:'axis'},xAxis:{type:'category',boundaryGap:false,data:trends.value.map(x=>x.date),axisLabel:{color:'#8792a5'},axisLine:{lineStyle:{color:'#e2e8f0'}}},yAxis:{type:'value',axisLabel:{color:'#8792a5'},splitLine:{lineStyle:{color:'#e9edf4'}}},series:[{type:'line',data:trends.value.map(x=>x.value),smooth:true,symbolSize:8,lineStyle:{color:'#617cf0',width:3},itemStyle:{color:'#617cf0'},areaStyle:{color:'rgba(97,124,240,.08)'}}]}))
async function load(){loading.value=true;error.value='';try{model.value=await api.model(id.value);runs.value=await api.runs(id.value);latest.value=runs.value[0]||null}catch(e){error.value=errorMessage(e)}finally{loading.value=false}}
async function run(payload:CalculationRequest){busy.value=true;error.value='';try{latest.value=await api.runModel(id.value,payload);runs.value=await api.runs(id.value);showForm.value=false}catch(e){error.value=errorMessage(e)}finally{busy.value=false}}
onMounted(load);watch(id,load)
function fmt(n:string|number|null|undefined){if(n==null)return '—';return new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(Number(n))}
</script>
<template>
 <div class="page-page">
  <div class="page-header"><div><div class="eyebrow"><span class="tiny-circle"/> ПРОИЗВОДСТВЕННЫЙ АНАЛИЗ</div><h1>Аналитика процесса</h1><p class="page-description">{{model?.name||'Модель'}} · Оценка мощности, такта и ограничений без вымышленных измерений.</p></div><button v-if="auth.canCalculate" class="button primary" @click="showForm=!showForm"><SlidersHorizontal :size="17"/> {{showForm?'Скрыть параметры':'Новый расчёт'}}</button></div>
  <div v-if="error" class="alert error-alert"><CircleAlert :size="17"/> {{error}}</div>
  <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22"/> Загружаем аналитику...</div>
  <template v-else>
   <div v-if="showForm" class="panel calc-panel"><CalculationForm :busy="busy" :disabled="!auth.canCalculate" @submit="run"/></div>
   <template v-if="latest"><div class="analysis-report-bar"><span><Activity :size="16"/> Последний расчёт · {{new Date(latest.created_at).toLocaleString('ru-RU')}}</span><span class="muted">{{ latest.scenario_id ? 'Сценарий' : 'Базовая модель' }}</span><button class="link-button" @click="router.push({name:'history',params:{id}})">История расчётов <ArrowRight :size="16"/></button></div>
    <div class="metric-grid"><MetricCard v-for="code in primaryCodes" :key="code" :title="getMetricTitle(code)" :metric="metrics[code]" :symbol="code==='capacity_upper_bound'?'шт. / период':code==='customer_quality_percent'?'%':'с'"/></div>
    <div class="two-column-panels"><div class="panel chart-panel"><div class="panel-heading"><div><h2>Ограничения по операциям</h2><p>Верхняя теоретическая оценка мощности, не фактический выпуск</p></div><ChartNoAxesCombined :size="20"/></div><KpiChart v-if="constraints.length" :option="capacityOption" :height="290"/><div v-else class="chart-empty">Для графика пока недостаточно исходных данных о времени и ресурсах.</div></div><div class="panel chart-panel"><div class="panel-heading"><div><h2>Динамика расчётов</h2><p>Доступные оценки мощности по истории запусков</p></div><Clock3 :size="20"/></div><KpiChart v-if="trends.length>=2" :option="trendOption" :height="290"/><div v-else class="chart-empty">График появится после нескольких сопоставимых расчётов.</div></div></div>
    <div class="two-column-panels lower-panels"><div class="panel details-panel"><div class="panel-heading"><div><h2>Другие показатели</h2><p>Статус каждого KPI зависит от достаточности данных</p></div></div><div class="metric-list"><div v-for="code in secondaryCodes" :key="code" class="metric-list-row"><div><span>{{titles[code]}}</span><small v-if="metrics[code]?.status==='unavailable'" :title="metrics[code]?.reasons?.join('; ')">Недостаточно данных</small></div><div><strong>{{fmt(metrics[code]?.value)}}</strong><small>{{metrics[code]?.value != null ? metrics[code]?.unit : '—'}}</small></div></div></div></div>
    <div class="panel details-panel"><div class="panel-heading"><div><h2>Узкие места</h2><p>Кандидаты на ограничение производительности</p></div><AlertTriangle :size="19"/></div><div v-if="latest.result.analysis.bottlenecks.length" class="bottlenecks"><div v-for="b in latest.result.analysis.bottlenecks" :key="`${b.owner_type}:${b.owner_id}:${b.code}`" class="bottleneck-row"><div class="bottleneck-icon"><AlertTriangle :size="18"/></div><div><strong>{{model?.graph.nodes.find(n=>n.id===b.owner_id)?.name||model?.graph.resources.find(r=>r.id===b.owner_id)?.name||b.owner_id}}</strong><p>{{b.explanation}}</p><small>{{b.code}}</small></div></div></div><div v-else class="chart-empty">{{missingCount?'Для обоснованного вывода может потребоваться больше данных.':'Выявленных ограничений нет.'}}</div><div v-if="latest.result.analysis.capacity.missing.length" class="missing-note"><strong>Не хватает данных</strong><p v-for="m in latest.result.analysis.capacity.missing.slice(0,5)" :key="m">{{m}}</p></div></div></div>
    <div v-if="missingCount" class="info-banner"><div class="banner-icon"><CircleAlert :size="21"/></div><div><strong>{{missingCount}} показателей недоступно</strong><p>Это ожидаемо для неполной модели. UDT не подменяет неизвестные измерения нулями; причины можно просмотреть в данных каждого KPI.</p></div></div>
   </template>
   <div v-else class="panel"><EmptyState title="Расчётов пока нет" text="Запустите первый расчёт. Он сохранится в истории вместе с параметрами и версиями алгоритмов."><button v-if="auth.canCalculate" class="button primary" @click="showForm=true"><SlidersHorizontal :size="17"/> Задать параметры расчёта</button></EmptyState></div>
  </template>
 </div>
</template>
