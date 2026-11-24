<script setup lang="ts">
import { computed, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { VueFlow, Background, Controls, MiniMap, addEdge } from '@xyflow/vue'
import type { Node as FlowNodeType, Edge as FlowEdgeType, Connection } from '@xyflow/vue'
import { api, errorMessage } from '../api/client'
import { useAuthStore } from '../stores/auth'
import type { GraphNode, GraphEdge, NodeKind, ProductionGraph, ProductionModel, StateType, SourceKind, Amount, ResourcePool } from '../api/types'
import { createNode, createEdge, NODE_KINDS, STATE_LABELS, graphProblems, layoutGraph, layoutKey, optionalPositiveInt, optionalPositiveDecimal, measuredSeconds, userSource } from '../lib/graph'
import FlowNode from '../components/FlowNode.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { ArrowLeft, Plus, Save, Send, Copy, ChevronDown, Trash2, Settings2, Link2, Layers3, Gauge, RotateCcw, Info, Check, CircleAlert, LockKeyhole, LoaderCircle, ChevronRight, Wrench } from 'lucide-vue-next'
const route = useRoute(); const router = useRouter(); const auth = useAuthStore()
const id = computed(() => String(route.params.id))
const model = ref<ProductionModel | null>(null); const graph = ref<ProductionGraph>({id:'',nodes:[],edges:[],resources:[],resource_uses:[],target_id:null,assume_independent_resources:false})
const nodeCosts = ref<Record<string, Amount>>({})
const name = ref(''); const stateType = ref<StateType>('current'); const loading = ref(true); const busy = ref(false)
const error = ref(''); const success = ref(''); const selectedNodeId = ref<string | null>(null); const selectedEdgeId = ref<string | null>(null)
const inspectorTab = ref<'details'|'resources'|'model'>('details')
const newKind = ref<NodeKind>('operation'); const versionList = ref<ProductionModel[]>([]); const versionMenu = ref(false)
const flowNodes = shallowRef<FlowNodeType[]>([]); const flowEdges = shallowRef<FlowEdgeType[]>([])
const criticalNodes = ref<string[]>([])
// Редактирование разрешено только для черновиков; опубликованные версии доступны для просмотра.
const editable = computed(() => auth.isEditor && model.value?.status === 'draft')
const selectedNode = computed(() => graph.value.nodes.find(n => n.id === selectedNodeId.value) || null)
const selectedEdge = computed(() => graph.value.edges.find(e => e.id === selectedEdgeId.value) || null)
const localProblems = computed(() => graphProblems(graph.value))
const nodeForm = reactive({ name:'', kind:'operation' as NodeKind, processing:'', available:'', batch:'', units:'', channels:'', output:'', cost:'', sourceKind:'user_input' as SourceKind, sourceRef:'user:frontend-manual-input', confirmed:false })
const edgeForm = reactive({kind:'material' as 'material'|'information',verification:'unresolved' as 'confirmed'|'inferred'|'unresolved',transit:'',waiting:'',item:'',sourceRef:''})
const resourceName = ref(''); const resourceSeconds = ref(''); const assignmentResourceId = ref(''); const assignmentWorkSeconds = ref('')
const editingAssignmentId = ref(''); const editedWorkSeconds = ref('')
const sources: {code:SourceKind;label:string}[] = [
 {code:'user_input',label:'Ввод пользователя'}, {code:'document',label:'Документ'}, {code:'normative',label:'Норматив'},
 {code:'measured',label:'Фактический замер'}, {code:'synthetic_test_fixture',label:'Синтетический тест'},
]
function message(e: unknown) { error.value=errorMessage(e); success.value='' }
function quiet() { error.value=''; success.value='' }
function savedLayout() {
  try { return JSON.parse(localStorage.getItem(layoutKey(id.value)) || '{}') as Record<string,{x:number;y:number}> } catch { return {} }
}
function syncFlow() {
  const positions = layoutGraph(graph.value, savedLayout())
  flowNodes.value = graph.value.nodes.map(n => ({ id:n.id, type:'udt', position:positions[n.id] || {x:0,y:0}, data:{node:n, isCritical:criticalNodes.value.includes(n.id)}, draggable:editable.value, connectable:editable.value }))
  flowEdges.value = graph.value.edges.map(e => ({ id:e.id, source:e.source_id, target:e.target_id,
    type:'smoothstep', animated:e.kind==='information', label:e.kind==='information' ? 'Информация' : undefined,
    style:{stroke:e.verification==='confirmed' ? '#7693c4' : '#a6afc1', strokeWidth:2, strokeDasharray:e.verification!=='confirmed' ? '6 5':undefined},
    data:{edge:e}, selected:e.id===selectedEdgeId.value }))
}
function storePositions() {
  try {
    const next = Object.fromEntries(flowNodes.value.map(n=>[n.id,n.position]))
    localStorage.setItem(layoutKey(id.value),JSON.stringify(next))
  } catch { /* Координаты — необязательные локальные данные интерфейса. */ }
}
function onDragStop(payload: {node:FlowNodeType}) { if (!editable.value) return; storePositions() }
function onConnect(connection: Connection) {
  if (!editable.value || !connection.source || !connection.target) return
  quiet()
  try {
    const edge = createEdge(connection.source, connection.target)
    const updated = {...graph.value, edges:[...graph.value.edges,edge]}
    const problems = graphProblems(updated)
    if (problems.length) throw new Error(problems.join('; '))
    graph.value = updated
    // Vue Flow возвращает новый массив, а связь модели хранит дополнительные поля проверки.
    flowEdges.value = addEdge({id:edge.id,source:edge.source_id,target:edge.target_id,type:'smoothstep'},flowEdges.value)
    selectEdge(edge.id)
    syncFlow()
  } catch (e) { message(e) }
}
function selectNode(nodeId: string) {
  selectedNodeId.value = nodeId; selectedEdgeId.value=null; inspectorTab.value='details'; editingAssignmentId.value='' 
  const n = graph.value.nodes.find(x=>x.id===nodeId); if(!n)return
  nodeForm.name=n.name;nodeForm.kind=n.kind
  nodeForm.processing=String(n.processing_seconds?.value ?? '')
  nodeForm.available=String(n.available_seconds?.value ?? '')
  nodeForm.batch=String(n.batch_size ?? '')
  nodeForm.units=String(n.units_per_finished ?? '')
  nodeForm.channels=String(n.parallel_channels ?? '')
  nodeForm.output=n.output_item || ''
  nodeForm.cost=String(nodeCosts.value[n.id]?.value ?? '')
  const src=n.processing_seconds?.source || n.available_seconds?.source || nodeCosts.value[n.id]?.source || userSource()
  nodeForm.sourceKind=src.kind; nodeForm.sourceRef=src.reference; nodeForm.confirmed=src.confirmed
}
function selectEdge(edgeId: string) {
  selectedEdgeId.value=edgeId; selectedNodeId.value=null; inspectorTab.value='details'
  const e=graph.value.edges.find(x=>x.id===edgeId);if(!e)return
  edgeForm.kind=e.kind;edgeForm.verification=e.verification;edgeForm.transit=String(e.transit_seconds?.value??'');edgeForm.waiting=String(e.waiting_seconds?.value??'');edgeForm.item=e.item_id||''
  edgeForm.sourceRef=e.source?.reference||''
}
function updateNode() {
  if (!selectedNode.value || !editable.value) return
  quiet()
  try {
    const src = {kind:nodeForm.sourceKind,reference:nodeForm.sourceRef.trim(),confirmed:nodeForm.confirmed && nodeForm.sourceKind!=='user_input',note:nodeForm.sourceKind==='user_input'?'Введено вручную, без проверки документа':null}
    const n:GraphNode = {...selectedNode.value,
      name:nodeForm.name.trim(),kind:nodeForm.kind,
      processing_seconds:measuredSeconds(nodeForm.processing,src),available_seconds:measuredSeconds(nodeForm.available,src),
      batch_size:optionalPositiveInt(nodeForm.batch),parallel_channels:optionalPositiveInt(nodeForm.channels),
      units_per_finished:optionalPositiveDecimal(nodeForm.units),output_item:nodeForm.output.trim()||null}
    if(!n.name)throw new Error('Имя операции обязательно')
    const costs={...nodeCosts.value}
    if(String(nodeForm.cost ?? '').trim()) {
      const costNumber=Number(nodeForm.cost); if(!Number.isFinite(costNumber)||costNumber<0)throw new Error('Стоимость должна быть неотрицательным числом')
      if(!src.reference)throw new Error('Для стоимости нужен источник')
      costs[n.id]={value:String(nodeForm.cost).trim(),unit:'RUB/output',source:src}
    } else delete costs[n.id]
    graph.value={...graph.value,nodes:graph.value.nodes.map(x=>x.id===n.id?n:x)}
    nodeCosts.value=costs; syncFlow(); success.value='Параметры применены к черновику. Сохраните модель.'
  } catch(e){message(e)}
}
function updateEdge() {
  if (!selectedEdge.value || !editable.value) return
  quiet()
  try {
    if(edgeForm.verification==='confirmed'&&!edgeForm.sourceRef.trim()) throw new Error('Для подтверждённой связи укажите источник')
    const src=userSource(edgeForm.sourceRef.trim()||'user:unverified-link')
    const e:GraphEdge={...selectedEdge.value,kind:edgeForm.kind,verification:edgeForm.verification,
      item_id:edgeForm.item.trim()||null,transit_seconds:measuredSeconds(edgeForm.transit,src),
      waiting_seconds:measuredSeconds(edgeForm.waiting,src),source:edgeForm.sourceRef.trim() ? src:null}
    graph.value={...graph.value,edges:graph.value.edges.map(x=>x.id===e.id?e:x)}
    syncFlow(); success.value='Связь изменена. Сохраните модель.'
  } catch(e){message(e)}
}
function addNode() {
  if (!editable.value)return
  quiet(); storePositions()
  const n=createNode(newKind.value,graph.value.nodes.length)
  graph.value={...graph.value,nodes:[...graph.value.nodes,n]};syncFlow(); selectNode(n.id)
}
function deleteSelected() {
  if (!editable.value)return
  const label=selectedNode.value?.name || selectedEdge.value?.id
  if(!label || !confirm(`Удалить «${label}» из черновика?`))return
  quiet()
  if(selectedNode.value) {
    const nid=selectedNode.value.id
    graph.value={...graph.value,nodes:graph.value.nodes.filter(n=>n.id!==nid),edges:graph.value.edges.filter(e=>e.source_id!==nid&&e.target_id!==nid),resource_uses:graph.value.resource_uses.filter(u=>u.node_id!==nid),target_id:graph.value.target_id===nid?null:graph.value.target_id}
    const costs={...nodeCosts.value};delete costs[nid];nodeCosts.value=costs
  } else if(selectedEdge.value) graph.value={...graph.value,edges:graph.value.edges.filter(e=>e.id!==selectedEdge.value?.id)}
  selectedNodeId.value=null;selectedEdgeId.value=null;syncFlow()
}
function addResource() {
  if(!editable.value || !resourceName.value.trim())return
  try {
    const a=measuredSeconds(resourceSeconds.value,userSource())
    const r:ResourcePool={id:`R-${crypto.randomUUID().slice(0,8)}`,name:resourceName.value.trim(),available_seconds:a}
    graph.value={...graph.value,resources:[...graph.value.resources,r]}
    resourceName.value='';resourceSeconds.value='';success.value='Ресурс добавлен в черновик'
  }catch(e){message(e)}
}
function addAssignment() {
  if(!selectedNode.value || !assignmentResourceId.value || !editable.value)return
  try {
    const src=userSource()
    const work=measuredSeconds(assignmentWorkSeconds.value,src)
    const exists=graph.value.resource_uses.some(x=>x.node_id===selectedNode.value?.id&&x.resource_id===assignmentResourceId.value)
    if(exists)throw new Error('Этот ресурс уже назначен операции')
    graph.value={...graph.value,resource_uses:[...graph.value.resource_uses,{node_id:selectedNode.value.id,resource_id:assignmentResourceId.value,work_seconds_per_output:work}]}
    assignmentWorkSeconds.value='';success.value='Ресурс назначен операции'
  }catch(e){message(e)}
}
function startAssignmentEdit(resourceId:string, work:string | number | null | undefined) {
  if (!editable.value) return
  editingAssignmentId.value = resourceId
  editedWorkSeconds.value = String(work ?? '')
  quiet()
}
function applyAssignmentEdit() {
  if(!editable.value || !selectedNode.value || !editingAssignmentId.value)return
  try {
    const work = measuredSeconds(editedWorkSeconds.value, userSource())
    const current = selectedNode.value.id
    const rid = editingAssignmentId.value
    graph.value = {...graph.value, resource_uses:graph.value.resource_uses.map(u =>
      u.node_id === current && u.resource_id === rid ? {...u,work_seconds_per_output:work} : u)}
    editingAssignmentId.value = ''; editedWorkSeconds.value = ''
    quiet(); success.value = 'Занятость обновлена в черновике. Нажмите «Сохранить» наверху.'
  } catch(e) {message(e)}
}
function removeResource(rid:string) {
  if(!editable.value||!confirm('Удалить ресурс и все его назначения?'))return
  graph.value={...graph.value,resources:graph.value.resources.filter(r=>r.id!==rid),resource_uses:graph.value.resource_uses.filter(u=>u.resource_id!==rid)}
}
function loadModel(row:ProductionModel) {
  model.value=row;name.value=row.name;stateType.value=row.state_type
  graph.value=structuredClone(row.graph);nodeCosts.value=structuredClone(row.node_costs||{})
  selectedNodeId.value=null;selectedEdgeId.value=null;syncFlow()
}
async function load() {
  loading.value=true;quiet()
  try {
    const row=await api.model(id.value);loadModel(row)
    versionList.value=await api.versions(id.value)
    const runs=await api.runs(id.value)
    criticalNodes.value=runs[0]?.result.analysis.bottlenecks.filter(b=>b.owner_type==='operation').map(b=>b.owner_id)||[]
    syncFlow()
  }catch(e){message(e)}finally{loading.value=false}
}
watch(id,load);onMounted(load)
async function save() {
  if(!model.value || !editable.value || busy.value)return
  quiet()
  if(localProblems.value.length){error.value=localProblems.value.join('; ');return}
  busy.value=true
  try {
    storePositions()
    const saved=await api.updateModel(id.value,{name:name.value,state_type:stateType.value,expected_revision:model.value.revision,graph:graph.value,node_costs:nodeCosts.value})
    loadModel(saved);success.value=`Изменения сохранены · ревизия ${saved.revision}`
  }catch(e){message(e)}finally{busy.value=false}
}
async function publish() {
  if(!model.value||!editable.value||busy.value)return
  if(!confirm('Опубликовать версию? После публикации изменить её нельзя, потребуется новая версия.'))return
  await save();if(error.value)return
  busy.value=true
  try{const published=await api.publish(id.value);loadModel(published);success.value='Модель опубликована. Теперь доступны сценарии.'}
  catch(e){message(e)}finally{busy.value=false}
}
async function clone() {
  if(!model.value||!auth.isEditor)return
  if(!confirm('Создать новую редактируемую версию на основе этой модели?'))return
  quiet();busy.value=true
  try{const created=await api.clone(id.value);await router.push({name:'editor',params:{id:created.id}})}
  catch(e){message(e)}finally{busy.value=false}
}
</script>
<template>
  <div class="editor-layout">
    <div v-if="loading" class="loading-state"><LoaderCircle class="spin" :size="22"/> Загрузка редактора...</div>
    <template v-else-if="model">
      <div class="editor-header"><div class="editor-header-main"><button class="icon-btn" aria-label="К моделям" @click="router.push('/models')"><ArrowLeft :size="20"/></button><div class="editor-heading"><div class="eyebrow">ПРОИЗВОДСТВЕННАЯ МОДЕЛЬ <span class="breadcrumb-dot">•</span> {{ STATE_LABELS[model.state_type] }} СОСТОЯНИЕ</div><h1>{{ model.name }}</h1></div><StatusBadge :status="model.status" /></div><div class="editor-actions"><div class="version-control"><button class="button tertiary compact" @click="versionMenu=!versionMenu">Версия {{ model.version }} <ChevronDown :size="15"/></button><div v-if="versionMenu" class="version-dropdown"><button v-for="v in versionList" :key="v.id" :class="{selected:v.id===id}" @click="versionMenu=false;router.push({name:'editor',params:{id:v.id}})">Версия {{ v.version }} · {{ v.status }}</button></div></div><button v-if="auth.isEditor" class="button secondary compact" :disabled="busy" @click="clone"><Copy :size="16"/> Новая версия</button><button v-if="editable" class="button secondary compact" :disabled="busy" @click="save"><Save :size="16"/> Сохранить</button><button v-if="editable" class="button primary compact" :disabled="busy" @click="publish"><Send :size="16"/> Опубликовать</button></div></div>
      <div v-if="error" class="alert error-alert editor-alert"><CircleAlert :size="17"/> {{ error }}</div><div v-else-if="success" class="alert success-alert editor-alert"><Check :size="17"/> {{ success }}</div>
      <div class="editor-workspace">
        <section class="canvas-section">
          <div class="canvas-topbar"><div class="canvas-title"><Layers3 :size="18"/><strong>Схема процесса</strong><span class="canvas-count">{{ graph.nodes.length }} узлов · {{ graph.edges.length }} связей</span></div><button class="button tertiary compact" @click="inspectorTab='model';selectedNodeId=null;selectedEdgeId=null"><Settings2 :size="15"/> Настройки</button></div>
          <div class="graph-canvas">
            <VueFlow v-model:nodes="flowNodes" v-model:edges="flowEdges" :nodes-draggable="editable" :nodes-connectable="editable" :elements-selectable="true" :delete-key-code="null" :fit-view-on-init="true" :min-zoom="0.25" :max-zoom="2" @connect="onConnect" @node-click="(event:any)=>selectNode(event.node.id)" @edge-click="(event:any)=>selectEdge(event.edge.id)" @node-drag-stop="onDragStop">
              <Background variant="dots" :gap="18" :size="1" pattern-color="#cbd5e1" />
              <Controls position="bottom-left" />
              <MiniMap position="bottom-right" pannable zoomable />
              <template #node-udt="{data, selected}"><FlowNode :data="data as any" :selected="selected"/></template>
            </VueFlow>
            <div v-if="!graph.nodes.length" class="canvas-empty"><Workflow :size="34"/><strong>Схема пока пустая</strong><span>Добавьте первую операцию через панель ниже</span></div>
            <div v-if="!editable" class="readonly-indicator"><LockKeyhole :size="14"/> Просмотр · редактирование недоступно</div>
            <div v-if="editable" class="canvas-addbar"><span>Добавить на схему</span><select v-model="newKind" aria-label="Тип нового узла"><option v-for="(label,key) in NODE_KINDS" :key="key" :value="key">{{ label }}</option></select><button class="button primary compact" @click="addNode"><Plus :size="16"/> Узел</button></div>
          </div>
          <div class="canvas-footer"><Info :size="15"/><span>Перетаскивайте узлы и соединяйте точки справа и слева. Позиции сохраняются локально в этом браузере.</span><span v-if="localProblems.length" class="footer-warning">{{ localProblems.length }} ошибок графа</span></div>
        </section>
        <aside class="inspector"><div class="inspector-head"><div><span class="eyebrow">ПАРАМЕТРЫ</span><h2>{{ selectedNode ? 'Свойства операции' : selectedEdge ? 'Свойства связи' : 'Настройка модели' }}</h2></div><Settings2 :size="19"/></div><div class="inspector-tabs"><button :class="{active:inspectorTab==='details'}" @click="inspectorTab='details'">Параметры</button><button :class="{active:inspectorTab==='resources'}" @click="inspectorTab='resources'">Ресурсы</button><button :class="{active:inspectorTab==='model'}" @click="inspectorTab='model'">Модель</button></div>
          <div class="inspector-body">
            <template v-if="inspectorTab==='details'&&selectedNode"><div class="inspector-selected"><div class="inspector-tag">{{ NODE_KINDS[selectedNode.kind] }}</div><strong>{{ selectedNode.id }}</strong></div><label class="field-label">Название</label><input v-model="nodeForm.name" :disabled="!editable" class="field-input"/><label class="field-label">Тип узла</label><select v-model="nodeForm.kind" :disabled="!editable" class="field-input"><option v-for="(label,key) in NODE_KINDS" :key="key" :value="key">{{ label }}</option></select>
              <div class="field-divider"><Gauge :size="16"/> Производственные параметры</div>
              <div class="field-grid"><div><label class="field-label">Время партии, с</label><input v-model="nodeForm.processing" :disabled="!editable" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Фонд времени, с</label><input v-model="nodeForm.available" :disabled="!editable" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Размер партии, шт.</label><input v-model="nodeForm.batch" :disabled="!editable" type="number" min="1" step="1" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Параллельные каналы</label><input v-model="nodeForm.channels" :disabled="!editable" type="number" min="1" step="1" class="field-input" placeholder="Неизвестно"/></div></div>
              <label class="field-label">Выходов операции на готовое изделие</label><input v-model="nodeForm.units" :disabled="!editable" type="number" min="0.000001" step="any" class="field-input" placeholder="Неизвестно"/><label class="field-label">Код выходной подсборки</label><input v-model="nodeForm.output" :disabled="!editable" class="field-input" placeholder="Неизвестно"/><label class="field-label">Стоимость, ₽/выход операции</label><input v-model="nodeForm.cost" :disabled="!editable" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/>
              <div class="field-divider"><Info :size="16"/> Происхождение значений</div><label class="field-label">Тип источника</label><select v-model="nodeForm.sourceKind" :disabled="!editable" class="field-input"><option v-for="s in sources" :key="s.code" :value="s.code">{{ s.label }}</option></select><label class="field-label">Источник / ссылка</label><input v-model="nodeForm.sourceRef" :disabled="!editable" class="field-input" placeholder="Документ, страница или наблюдение"/><label class="checkbox-row"><input v-model="nodeForm.confirmed" type="checkbox" :disabled="!editable||nodeForm.sourceKind==='user_input'"/> Источник подтверждён</label>
              <button v-if="editable" class="button primary full-width" @click="updateNode"><Check :size="16"/> Применить параметры</button><button v-if="editable" class="button danger-outline full-width" @click="deleteSelected"><Trash2 :size="16"/> Удалить узел</button>
            </template>
            <template v-else-if="inspectorTab==='details'&&selectedEdge"><div class="inspector-selected"><div class="inspector-tag">СВЯЗЬ</div><strong>{{ selectedEdge.source_id }} → {{ selectedEdge.target_id }}</strong></div><label class="field-label">Тип связи</label><select v-model="edgeForm.kind" :disabled="!editable" class="field-input"><option value="material">Материальный поток</option><option value="information">Информационный поток</option></select><label class="field-label">Подтверждение</label><select v-model="edgeForm.verification" :disabled="!editable" class="field-input"><option value="unresolved">Не установлено</option><option value="inferred">Предположение</option><option value="confirmed">Подтверждено источником</option></select><label class="field-label">Время перемещения, с</label><input v-model="edgeForm.transit" :disabled="!editable" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/><label class="field-label">Время ожидания, с</label><input v-model="edgeForm.waiting" :disabled="!editable" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/><label class="field-label">Код передаваемого материала</label><input v-model="edgeForm.item" :disabled="!editable" class="field-input" placeholder="При наличии"/><label class="field-label">Источник связи</label><input v-model="edgeForm.sourceRef" :disabled="!editable" class="field-input" placeholder="Документ, страница"/><div class="side-note">Незаполненные времена остаются неизвестными и могут блокировать точный ВПП.</div><button v-if="editable" class="button primary full-width" @click="updateEdge"><Check :size="16"/> Применить параметры</button><button v-if="editable" class="button danger-outline full-width" @click="deleteSelected"><Trash2 :size="16"/> Удалить связь</button></template>
            <template v-else-if="inspectorTab==='details'"><div class="inspector-placeholder"><Link2 :size="30"/><h3>Выберите узел или связь</h3><p>Нажмите на элемент схемы, чтобы увидеть и изменить его свойства.</p><span>Для добавления связи протяните линию от правого порта узла к левому порту другого.</span></div></template>
            <template v-if="inspectorTab==='resources'"><div class="field-divider"><Wrench :size="16"/> Ресурсные ограничения</div><p class="inspector-help">Ресурсы учитываются ядром при оценке ограничений производственной мощности.</p><div v-for="r in graph.resources" :key="r.id" class="resource-row"><div><strong>{{ r.name }}</strong><small>{{ r.available_seconds?.value ?? 'Неизвестно' }} секунд доступного времени</small></div><button v-if="editable" class="icon-btn" title="Удалить ресурс" @click="removeResource(r.id)"><Trash2 :size="16"/></button></div><div v-if="!graph.resources.length" class="inspector-help">Ресурсы ещё не заданы.</div><template v-if="editable"><label class="field-label">Название нового ресурса</label><input v-model="resourceName" class="field-input" placeholder="Например, оператор сборки"/><label class="field-label">Доступный фонд, с</label><input v-model="resourceSeconds" class="field-input" type="number" min="0" step="any" placeholder="Неизвестно"/><button class="button secondary full-width" @click="addResource"><Plus :size="16"/> Добавить ресурс</button></template><div v-if="selectedNode" class="field-divider">Назначения: {{ selectedNode.name }}</div><div v-for="u in graph.resource_uses.filter(u=>u.node_id===selectedNode?.id)" :key="u.resource_id" class="resource-row">
                  <div><strong>{{ graph.resources.find(r=>r.id===u.resource_id)?.name }}</strong><small>{{ u.work_seconds_per_output?.value ?? 'Неизвестно' }} с/выход операции</small>
                    <div v-if="editable && editingAssignmentId===u.resource_id" class="resource-edit-row">
                      <input v-model="editedWorkSeconds" class="field-input" type="number" step="any" min="0" placeholder="Неизвестно" aria-label="Занятость, секунд на выход" />
                      <button class="button primary compact" @click="applyAssignmentEdit">Применить</button>
                      <button class="button ghost compact" @click="editingAssignmentId=''">Отмена</button>
                    </div>
                  </div>
                  <button v-if="editable && editingAssignmentId!==u.resource_id" class="button ghost compact" @click="startAssignmentEdit(u.resource_id,u.work_seconds_per_output?.value)">Изменить</button>
                  <button v-if="editable" class="icon-btn" aria-label="Удалить назначение" @click="graph={...graph,resource_uses:graph.resource_uses.filter(x=>x!==u)}"><Trash2 :size="16"/></button>
                </div><template v-if="selectedNode&&editable"><label class="field-label">Ресурс</label><select v-model="assignmentResourceId" class="field-input"><option value="">Выберите ресурс</option><option v-for="r in graph.resources" :key="r.id" :value="r.id">{{ r.name }}</option></select><label class="field-label">Занятость, с/выход</label><input v-model="assignmentWorkSeconds" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/><button class="button secondary full-width" @click="addAssignment"><Plus :size="16"/> Назначить ресурс</button></template></template>
            <template v-if="inspectorTab==='model'"><div class="field-divider"><Settings2 :size="16"/> Общие параметры</div><label class="field-label">Название модели</label><input v-model="name" :disabled="!editable" class="field-input"/><label class="field-label">Состояние потока</label><select v-model="stateType" :disabled="!editable" class="field-input"><option value="current">Текущее</option><option value="ideal">Идеальное</option><option value="target">Целевое</option></select><label class="field-label">Конечный узел модели</label><select v-model="graph.target_id" :disabled="!editable" class="field-input"><option :value="null">Не определён</option><option v-for="n in graph.nodes" :key="n.id" :value="n.id">{{ n.name }}</option></select><label class="checkbox-row"><input v-model="graph.assume_independent_resources" type="checkbox" :disabled="!editable"/> Предполагать независимость ресурсов</label><p class="side-note">Включайте только при обоснованном предположении: иначе вычисление критического пути параллельных операций может быть недоступно.</p><div class="field-divider">Контроль модели</div><p v-if="!localProblems.length" class="check-ok"><Check :size="16"/> Локальных структурных ошибок нет</p><div v-for="problem in localProblems" :key="problem" class="alert error-alert">{{ problem }}</div><p class="inspector-help">На публикации сервер повторно проверит граф через NetworkX. Отсутствующие измерения не подменяются нулями.</p></template>
          </div>
        </aside>
      </div>
      <div class="editor-bottom-bar"><span><span class="online-pulse"/> {{ model.status === 'draft' ? 'Черновик модели' : 'Зафиксированная версия' }} · ревизия {{ model.revision }}</span><div><button class="button tertiary compact" @click="router.push({name:'analytics',params:{id}})">Аналитика <ChevronRight :size="16"/></button><button v-if="model.status==='published'" class="button primary compact" @click="router.push({name:'scenarios',params:{id}})">Сценарии <ChevronRight :size="16"/></button></div></div>
    </template>
    <div v-else class="alert error-alert">{{ error || 'Модель не найдена' }}</div>
  </div>
</template>
