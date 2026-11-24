<script setup lang="ts">
import { computed, onMounted, ref, toRaw, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { EChartsCoreOption } from 'echarts/core'
import { api, errorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { CalculationRequest, CalculationRun, Override, ProductionModel, Scenario, Amount } from '../api/types'
import { userSource } from '../lib/graph'
import CalculationForm from '../components/CalculationForm.vue'
import KpiChart from '../components/KpiChart.vue'
import EmptyState from '../components/EmptyState.vue'
import { GitCompareArrows, Plus, Play, CircleAlert, Check, ArrowRight, LoaderCircle, Save, Trash2, Info, FlaskConical } from 'lucide-vue-next'
const route=useRoute(),router=useRouter(),auth=useAuthStore()
const id=computed(()=>String(route.params.id)), model=ref<ProductionModel|null>(null), list=ref<Scenario[]>([]), active=ref<Scenario|null>(null), runResult=ref<CalculationRun|null>(null)
const loading=ref(true),busy=ref(false),error=ref(''),success=ref(''),name=ref(''),formVisible=ref(false),calculating=ref(false)
const overrides=ref<Override[]>([]),costOverrides=ref<Record<string,Amount>>({})
const nodeId=ref(''),param=ref<Override['field']>('processing_seconds'),value=ref(''),reason=ref(''),costNode=ref(''),costValue=ref('')
const selectedResourceUseId = ref(''); const resourceNewWork = ref(''); const resourceReason = ref('')
const syncSingleResource = ref(true)
// Автосинхронизация времени возможна лишь при одном назначенном ресурсе операции.
const singleAssignment = computed(() => {
 if(!model.value || !nodeId.value) return null
 const uses = model.value.graph.resource_uses.filter(u=>u.node_id===nodeId.value)
 return uses.length===1 ? uses[0]! : null
})
const assignments = computed(() => model.value?.graph.resource_uses.map(u => ({
  key: `${u.node_id}::${u.resource_id}`,
  label: `${model.value?.graph.nodes.find(n=>n.id===u.node_id)?.name||u.node_id} — ${model.value?.graph.resources.find(r=>r.id===u.resource_id)?.name||u.resource_id}`,
  work: u.work_seconds_per_output?.value ?? null,
})) || [])
function resourceChangeLabel(change:Override) {
 if (change.target_type !== 'resource_use') return model.value?.graph.nodes.find(n=>n.id===change.target_id)?.name || change.target_id
 return assignments.value.find(u=>u.key===change.target_id)?.label || change.target_id
}
function changeFieldLabel(change:Override) {
 return change.target_type === 'resource_use' ? 'Занятость оператора, с/выход' : nodeFields.find(f=>f.field===change.field)?.label || change.field
}
function addSyncedResourceChange(node:string, newWork:string, cause:string) {
 if (!model.value) return
 const uses = model.value.graph.resource_uses.filter(u=>u.node_id===node)
 if(uses.length!==1) throw new Error('Для автоматической синхронизации нужен ровно один назначенный ресурс')
 const target=`${node}::${uses[0]!.resource_id}`
 if (overrides.value.some(o=>o.target_type==='resource_use'&&o.target_id===target&&o.field==='work_seconds_per_output')) throw new Error('Занятость ресурса уже изменена в сценарии')
 overrides.value=[...overrides.value,{target_type:'resource_use',target_id:target,field:'work_seconds_per_output',new_value:newWork,reason:cause}]
}
function syncExisting(change:Override) {
 try { addSyncedResourceChange(change.target_id,change.new_value,`Допущение: занятость равна новой длительности операции (${change.new_value} с)`);error.value='' }
 catch (e) { error.value=errorMessage(e) }
}
function canSync(change:Override):boolean {
 if(change.target_type!=='node'||change.field!=='processing_seconds'||!model.value) return false
 const uses=model.value.graph.resource_uses.filter(u=>u.node_id===change.target_id)
 return uses.length===1 && !overrides.value.some(o=>o.target_type==='resource_use'&&o.target_id===`${change.target_id}::${uses[0]!.resource_id}`&&o.field==='work_seconds_per_output')
}
const nodeFields: {field:Override['field'];label:string}[]=[
 {field:'processing_seconds',label:'Длительность операции, с'}, {field:'batch_size',label:'Размер партии, шт.'}, {field:'units_per_finished',label:'Единиц выхода на изделие'},
 {field:'parallel_channels',label:'Параллельных каналов'}, {field:'available_seconds',label:'Доступное время, с'},
]
const calc=computed(()=>runResult.value?.result)
const baseCap=computed(()=>calc.value?.baseline_analysis?.capacity.known_upper_bound ?? null)
const nextCap=computed(()=>calc.value?.analysis.capacity.known_upper_bound??null)
const barOption=computed<EChartsCoreOption>(()=>({
 grid:{left:30,right:25,top:25,bottom:35,containLabel:true},tooltip:{trigger:'axis'},
 xAxis:{type:'category',data:['Исходная модель','Сценарий'],axisLabel:{color:'#69778f'}},
 yAxis:{type:'value',axisLabel:{color:'#69778f'},splitLine:{lineStyle:{color:'#e9edf4'}}},
 series:[{type:'bar',barMaxWidth:95,data:[{value:Number(baseCap.value),itemStyle:{color:'#aab6da',borderRadius:[6,6,0,0]}},{value:Number(nextCap.value),itemStyle:{color:'#607af4',borderRadius:[6,6,0,0]}}]}]
}))
async function load(){loading.value=true;error.value='';try{model.value=await api.model(id.value);list.value=await api.scenarios(id.value);if(active.value){const fresh=list.value.find(s=>s.id===active.value?.id);if(fresh)open(fresh)}}catch(e){error.value=errorMessage(e)}finally{loading.value=false}}
onMounted(load);watch(id,()=>{active.value=null;runResult.value=null;load()})
function newScenario(){active.value=null;runResult.value=null;overrides.value=[];costOverrides.value={};name.value='';formVisible.value=true;error.value='';success.value=''}
function open(scenario: Scenario) {
  const saved = toRaw(scenario)
  overrides.value = structuredClone(saved.overrides)
  costOverrides.value = structuredClone(saved.cost_overrides ?? {})
  active.value = scenario
  name.value = saved.name
  formVisible.value = true
  runResult.value = null
  error.value = ''
  success.value = ''
}
function addOverride(){
 try{
  if(!nodeId.value||!String(value.value ?? '').trim()||!reason.value.trim())throw new Error('Укажите узел, новое значение и обоснование')
  if(reason.value.trim().length>500)throw new Error('Обоснование не должно превышать 500 символов')
  const number=Number(value.value)
  if(!Number.isFinite(number)||number<0)throw new Error('Новое значение должно быть неотрицательным числом')
  if((param.value==='batch_size'||param.value==='parallel_channels')&&(!Number.isInteger(number)||number<=0))throw new Error('Для партии и каналов требуется положительное целое число')
  if((param.value==='processing_seconds'||param.value==='units_per_finished')&&number<=0)throw new Error('Время обработки и коэффициент должны быть положительными')
  const item:Override={target_type:'node',target_id:nodeId.value,field:param.value,new_value:String(value.value).trim(),reason:reason.value.trim()}
  if(overrides.value.some(o=>o.target_id===item.target_id&&o.field===item.field))throw new Error('Этот параметр уже переопределён')
  const previous=overrides.value
  try {
    overrides.value=[...overrides.value,item]
    if (param.value==='processing_seconds'&&syncSingleResource.value&&singleAssignment.value) {
      addSyncedResourceChange(nodeId.value,item.new_value,`Гипотеза: занятость совпадает с длительностью ${item.new_value} с`)
    }
  } catch (e) { overrides.value=previous; throw e }
  reason.value='';value.value='';error.value=''
 }catch(e){error.value=errorMessage(e)}
}
function addResourceOverride(){
 try {
   if(!selectedResourceUseId.value || !String(resourceNewWork.value).trim() || !resourceReason.value.trim()) throw new Error('Выберите назначенный ресурс, время занятости и основание')
   if(resourceReason.value.trim().length>500) throw new Error('Обоснование не должно превышать 500 символов')
   const number = Number(resourceNewWork.value)
   if(!Number.isFinite(number)||number<0)throw new Error('Занятость должна быть неотрицательным числом')
   if(overrides.value.some(o=>o.target_type==='resource_use'&&o.target_id===selectedResourceUseId.value&&o.field==='work_seconds_per_output')) throw new Error('Этот ресурс уже изменён в сценарии')
   overrides.value=[...overrides.value,{target_type:'resource_use',target_id:selectedResourceUseId.value,field:'work_seconds_per_output',new_value:String(resourceNewWork.value).trim(),reason:resourceReason.value.trim()}]
   resourceNewWork.value=''; resourceReason.value='';error.value=''
 }catch(e){error.value=errorMessage(e)}
}
function addCost(){
 try {
  if(!costNode.value||!String(costValue.value ?? '').trim())throw new Error('Укажите операцию и стоимость')
  const num=Number(costValue.value);if(!Number.isFinite(num)||num<0)throw new Error('Стоимость не может быть отрицательной')
  costOverrides.value={...costOverrides.value,[costNode.value]:{value:costValue.value,unit:'RUB/output',source:{...userSource('user:scenario-cost'),kind:'synthetic_scenario',note:'Параметр сценария (гипотеза)'}}}
  costValue.value='';error.value=''
 }catch(e){error.value=errorMessage(e)}
}
async function persist(){if(!auth.isEditor||busy.value)return;busy.value=true;error.value='';success.value='';try{
  if(!name.value.trim())throw new Error('Введите название сценария')
  if(name.value.trim().length>220)throw new Error('Название сценария слишком длинное (максимум 220 символов)')
  if(active.value){const updated=await api.updateScenario(active.value.id,{name:name.value,overrides:overrides.value,cost_overrides:costOverrides.value});open(updated);success.value='Изменения сценария сохранены'}
  else{const created=await api.createScenario(id.value,{name:name.value,overrides:overrides.value,cost_overrides:costOverrides.value});open(created);success.value='Сценарий сохранён'}
  list.value=await api.scenarios(id.value)
 }catch(e){error.value=errorMessage(e)}finally{busy.value=false}}
// Сравнение сохраняет отдельный расчёт, не изменяя исходную опубликованную модель.
async function calculate(request:CalculationRequest){if(!active.value)return;busy.value=true;error.value='';success.value='';try{runResult.value=await api.runScenario(active.value.id,request);calculating.value=false;success.value='Сценарий рассчитан и сохранён в истории'}catch(e){error.value=errorMessage(e)}finally{busy.value=false}}
const readable=(x:string|number|null)=>x===null?'Нет данных':new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(Number(x))
</script>
<template>
  <div class="page-page"><div class="page-header"><div><div class="eyebrow"><span class="tiny-circle"/> WHAT-IF АНАЛИЗ</div><h1>Сценарное моделирование</h1><p class="page-description">Меняйте параметры производства и сравнивайте результаты без изменения исходной модели.</p></div><button v-if="model?.status==='published'&&auth.isEditor" class="button primary" @click="newScenario"><Plus :size="17"/> Новый сценарий</button></div>
   <div v-if="error" class="alert error-alert"><CircleAlert :size="17"/> {{error}}</div><div v-if="success" class="alert success-alert"><Check :size="17"/> {{success}}</div>
   <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22"/> Загрузка сценариев...</div>
   <template v-else-if="model"><div v-if="model.status!=='published'" class="info-banner"><div class="banner-icon"><Info :size="22"/></div><div><strong>Сначала опубликуйте модель</strong><p>Сценарии создаются на основе зафиксированной версии. Вернитесь в редактор и опубликуйте граф.</p></div><button class="button secondary" @click="router.push({name:'editor',params:{id}})">В редактор <ArrowRight :size="16"/></button></div>
    <div v-else class="scenario-layout"><section class="panel scenario-list-panel"><div class="panel-heading"><div><h2>Сценарии</h2><p>{{list.length}} вариантов изменений</p></div><FlaskConical :size="20"/></div><div v-if="!list.length" class="scenario-list-empty">Сценариев пока нет. Создайте первый вариант оптимизации.</div><button v-for="s in list" :key="s.id" class="scenario-list-item" :class="{active:active?.id===s.id}" @click="open(s)"><div class="scenario-circle"><GitCompareArrows :size="18"/></div><div><strong>{{s.name}}</strong><small>{{s.overrides.length}} изменений · {{Object.keys(s.cost_overrides||{}).length}} стоимостных</small></div><ArrowRight :size="16"/></button><button v-if="auth.isEditor" class="button secondary full-width" @click="newScenario"><Plus :size="16"/> Новый сценарий</button></section>
    <section class="scenario-main"><div v-if="formVisible" class="panel scenario-config"><div class="panel-heading"><div><h2>{{active?'Параметры сценария':'Создание сценария'}}</h2><p>Изменения будут применены только к расчёту сценария</p></div></div><label class="field-label">Название сценария</label><input v-model="name" :disabled="!auth.isEditor" class="field-input" placeholder="Например, Ускорение сборки"/>
      <div class="field-divider">Изменения параметров</div><div v-for="(o,index) in overrides" :key="`${o.target_id}-${o.field}`" class="override-chip"><div><strong>{{resourceChangeLabel(o)}}</strong><small>{{changeFieldLabel(o)}} → {{o.new_value}}</small><em>{{o.reason}}</em><div v-if="auth.isEditor && canSync(o)"><button class="button secondary compact" @click="syncExisting(o)">Добавить такую же занятость оператору</button></div></div><button v-if="auth.isEditor" class="icon-btn" aria-label="Удалить изменение" @click="overrides.splice(index,1)"><Trash2 :size="17"/></button></div><div v-if="!overrides.length" class="inspector-help">Параметры пока не изменены.</div>
      <div v-if="auth.isEditor" class="override-editor"><div class="field-grid"><div><label class="field-label">Операция</label><select v-model="nodeId" class="field-input"><option value="">Выберите узел</option><option v-for="n in model.graph.nodes" :key="n.id" :value="n.id">{{n.name}}</option></select></div><div><label class="field-label">Изменяемый параметр</label><select v-model="param" class="field-input"><option v-for="f in nodeFields" :key="f.field" :value="f.field">{{f.label}}</option></select></div><div><label class="field-label">Новое значение</label><input v-model="value" type="number" min="0" step="any" class="field-input" placeholder="Введите значение"/></div><div><label class="field-label">Основание изменения</label><input v-model="reason" class="field-input" placeholder="Например, пробное улучшение"/></div></div><label v-if="param==='processing_seconds'&&singleAssignment" class="checkbox-row"><input v-model="syncSingleResource" type="checkbox"/> Также изменить занятость единственного назначенного оператора на то же время (допущение)</label>
        <button class="button secondary" @click="addOverride"><Plus :size="16"/> Добавить параметр</button></div>
      <div class="field-divider">Изменение занятости ресурсов</div>
      <p class="inspector-help">Доступны только ресурсы, уже назначенные операциям. Сценарий не меняет исходную модель. Занятость может отличаться от длительности операции.</p>
      <div v-if="auth.isEditor" class="override-editor"><div class="field-grid">
        <div><label class="field-label">Оператор / назначение</label><select v-model="selectedResourceUseId" class="field-input"><option value="">Выберите ресурс</option><option v-for="a in assignments" :key="a.key" :value="a.key">{{a.label}} (было {{a.work??'неизвестно'}} с)</option></select></div>
        <div><label class="field-label">Новая занятость, с/выход</label><input v-model="resourceNewWork" class="field-input" type="number" min="0" step="any" placeholder="Например, 100"/></div>
        <div><label class="field-label">Основание изменения</label><input v-model="resourceReason" class="field-input" placeholder="Гипотетическое сокращение работы"/></div>
      </div><button class="button secondary" @click="addResourceOverride"><Plus :size="16"/> Добавить занятость ресурса</button></div>
      <div class="field-divider">Изменение стоимости операции</div><div v-for="(cost,key) in costOverrides" :key="key" class="override-chip"><div><strong>{{model.graph.nodes.find(n=>n.id===key)?.name||key}}</strong><small>{{cost.value}} {{cost.unit}}</small></div><button v-if="auth.isEditor" class="icon-btn" aria-label="Удалить изменение стоимости" @click="delete costOverrides[key]"><Trash2 :size="17"/></button></div><div v-if="auth.isEditor" class="override-editor"><div class="field-grid"><div><label class="field-label">Операция</label><select v-model="costNode" class="field-input"><option value="">Выберите операцию</option><option v-for="n in model.graph.nodes.filter(n=>n.kind==='operation'||n.kind==='inspection')" :key="n.id" :value="n.id">{{n.name}}</option></select></div><div><label class="field-label">Новая стоимость ₽/выход</label><input v-model="costValue" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div></div><button class="button secondary" @click="addCost"><Plus :size="16"/> Добавить стоимость</button></div><div class="modal-actions" v-if="auth.isEditor"><button class="button primary" :disabled="busy||!name.trim()" @click="persist"><Save :size="16"/> {{active?'Сохранить сценарий':'Создать сценарий'}}</button></div></div>
      <div v-else class="panel"><EmptyState title="Выберите сценарий" text="Откройте вариант из списка или создайте новый, чтобы изменить параметры производства и сравнить результаты."/></div>
      <div v-if="active" class="panel scenario-results"><div class="panel-heading"><div><h2>Расчёт «до / после»</h2><p>Сопоставимые показатели исходной модели и сценария</p></div><Play :size="20"/></div><button v-if="auth.canCalculate" class="button secondary" @click="calculating=!calculating"><Play :size="16"/> {{calculating?'Скрыть параметры':'Рассчитать сценарий'}}</button><div v-if="calculating" class="scenario-calc-form"><CalculationForm :busy="busy" :disabled="!auth.canCalculate" button-label="Сравнить до / после" @submit="calculate"/></div><template v-if="runResult"><div class="comparison-cards"><div><small>Исходная мощность</small><strong>{{readable(baseCap)}}</strong><span>верхняя оценка / период</span></div><div><small>После изменений</small><strong>{{readable(nextCap)}}</strong><span>верхняя оценка / период</span></div><div><small>Изменение</small><strong>{{readable(calc?.capacity_delta??null)}}</strong><span>изделий / период</span></div></div><KpiChart v-if="baseCap!==null&&nextCap!==null" :option="barOption" :height="260"/><p v-else class="side-note">Недостаточно данных для сопоставимого расчёта мощности. Неизвестные значения не заменяются нулями.</p><div v-if="calc?.baseline_analysis" class="result-note">Исходный граф: {{calc.baseline_analysis.graph.valid?'корректен':'с ошибками'}} · Изменённый граф: {{calc.analysis.graph.valid?'корректен':'с ошибками'}}</div></template><div v-else class="chart-empty">Запустите расчёт. Результат сохранится в истории и будет доступен для повторного просмотра.</div></div>
    </section></div>
   </template>
  </div>
</template>
