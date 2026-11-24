<script setup lang="ts">
import { reactive, ref } from 'vue'
import { Play, Info, ChevronDown } from 'lucide-vue-next'
import type { CalculationFacts, CalculationRequest, Source, SourceKind, Amount } from '../api/types'
const props = defineProps<{busy?: boolean; buttonLabel?: string; disabled?: boolean}>()
const emit = defineEmits<{submit:[request:CalculationRequest]}>()
const input = reactive({available:'',demand:'',accepted:'',presented:'',period:'',busy:'',resourceAvailable:'',downtime:'',scheduled:'',inventoryBegin:'',inventoryEnd:'',totalCost:'',revenue:'',takt:'', periodKey:''})
const sourceKind = ref<SourceKind>('user_input'); const sourceRef = ref('user:frontend-input'); const confirmed = ref(false)
const optimistic = ref(false); const advanced = ref(false); const error = ref('')
function source():Source {return {kind:sourceKind.value,reference:sourceRef.value.trim(),confirmed:confirmed.value && sourceKind.value!=='user_input'}}
function count(value:string|number):{value:number;source:Source}|undefined {
 const text=String(value ?? '').trim();if(!text)return undefined
 const n=Number(text);if(!Number.isInteger(n)||n<0)throw new Error('Количество должно быть целым неотрицательным числом')
 return {value:n,source:source()}
}
function amount(value:string|number,unit:string):Amount|undefined {
 const text=String(value ?? '').trim();if(!text)return undefined
 const n=Number(text);if(!Number.isFinite(n)||n<0)throw new Error('Числовое значение должно быть неотрицательным')
 return {value:text,unit,source:source()}
}
function submit() {
 error.value=''
 try {
  const allValues=Object.values(input).filter(Boolean)
  if(allValues.length && !sourceRef.value.trim())throw new Error('Укажите источник исходных значений')
  const facts:CalculationFacts={
    available_seconds:amount(input.available,'s'), demand:count(input.demand), accepted:count(input.accepted), presented:count(input.presented),
    period_seconds:amount(input.period,'s'),busy_seconds:amount(input.busy,'s'), resource_available_seconds:amount(input.resourceAvailable,'s'),
    downtime_seconds:amount(input.downtime,'s'),scheduled_seconds:amount(input.scheduled,'s'),
    inventory_begin:amount(input.inventoryBegin,'RUB'), inventory_end:amount(input.inventoryEnd,'RUB'),
    total_cost:amount(input.totalCost,'RUB'), revenue:amount(input.revenue,'RUB'),
  }
  Object.keys(facts).forEach(k => {if(facts[k as keyof CalculationFacts]===undefined)delete facts[k as keyof CalculationFacts]})
  // Предварительная проверка в форме; те же ограничения контролируются FastAPI.
  if (facts.accepted && facts.presented && facts.accepted.value > facts.presented.value)
    throw new Error('Принятых изделий не может быть больше предъявленных')
  if (facts.busy_seconds && facts.resource_available_seconds && Number(facts.busy_seconds.value) > Number(facts.resource_available_seconds.value))
    throw new Error('Занятость ресурса не может превышать его доступное время')
  if (facts.downtime_seconds && facts.scheduled_seconds && Number(facts.downtime_seconds.value) > Number(facts.scheduled_seconds.value))
    throw new Error('Простой не может превышать плановое время')
  if (String(input.takt).trim() && Number(input.takt) <= 0)
    throw new Error('Заданный такт должен быть положительным числом')
  emit('submit',{facts,optimistic_lead_time:optimistic.value, ...(String(input.takt ?? '').trim()?{takt_seconds:amount(input.takt,'s')}:{}), ...(input.periodKey.trim()?{period_key:input.periodKey.trim()}: {})})
 } catch(e){error.value=e instanceof Error?e.message:'Неверные данные'}
}
</script>
<template>
  <form class="calc-form" @submit.prevent="submit">
    <div class="calc-form-title"><div><h3>Параметры запуска</h3><p>Заполняйте только подтверждённые или явно оценочные данные.</p></div><Info :size="19"/></div>
    <div class="field-grid"><div><label class="field-label">Доступное время, с</label><input v-model="input.available" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Спрос, шт.</label><input v-model="input.demand" type="number" min="0" step="1" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Принято изделий, шт.</label><input v-model="input.accepted" type="number" min="0" step="1" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Предъявлено, шт.</label><input v-model="input.presented" type="number" min="0" step="1" class="field-input" placeholder="Неизвестно"/></div></div>
    <button type="button" class="disclosure-btn" @click="advanced=!advanced">Дополнительные измерения <ChevronDown :size="16" :class="{flipped:advanced}"/></button>
    <div v-if="advanced" class="calc-advanced"><div class="field-grid"><div><label class="field-label">Период наблюдения, с</label><input v-model="input.period" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Занятость ресурса, с</label><input v-model="input.busy" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Фонд ресурса, с</label><input v-model="input.resourceAvailable" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Простой, с</label><input v-model="input.downtime" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Плановое время, с</label><input v-model="input.scheduled" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Заданный такт, с</label><input v-model="input.takt" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">НЗП на начало, ₽</label><input v-model="input.inventoryBegin" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">НЗП на конец, ₽</label><input v-model="input.inventoryEnd" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Затраты за период, ₽</label><input v-model="input.totalCost" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div><div><label class="field-label">Выручка за период, ₽</label><input v-model="input.revenue" type="number" min="0" step="any" class="field-input" placeholder="Неизвестно"/></div></div><label class="field-label">Ключ периода (для сравнения)</label><input v-model="input.periodKey" class="field-input" maxlength="120" placeholder="Например, учебная смена 1"/></div>
    <div class="source-strip"><div class="source-strip-title">Происхождение введённых данных</div><div class="field-grid"><div><label class="field-label">Тип источника</label><select v-model="sourceKind" class="field-input"><option value="user_input">Ввод пользователя (непроверен)</option><option value="document">Документ</option><option value="normative">Норматив</option><option value="measured">Фактический замер</option><option value="synthetic_test_fixture">Синтетический пример</option></select></div><div><label class="field-label">Ссылка на источник</label><input v-model="sourceRef" class="field-input" placeholder="Документ или запись замера"/></div></div><label class="checkbox-row"><input v-model="confirmed" type="checkbox" :disabled="sourceKind==='user_input'"/> Данные проверены по указанному источнику</label></div>
    <label class="checkbox-row"><input v-model="optimistic" type="checkbox"/> Разрешить оптимистическую оценку ВПП при конфликте ресурсов</label>
    <p class="side-note">Без входных данных система сохраняет расчёт, но часть KPI покажет «Нет данных». Неизвестное не приравнивается к нулю.</p>
    <div v-if="error" class="alert error-alert">{{ error }}</div>
    <button type="submit" class="button primary full-width" :disabled="busy||disabled"><Play :size="16"/> {{ busy?'Расчёт...':buttonLabel||'Запустить расчёт' }}</button>
  </form>
</template>
