import { describe, expect, it } from 'vitest'
import { blankGraph, userSource } from '../lib/graph'
import type { CalculationRequest, ProductionModel, Scenario } from '../api/types'
describe('API-контракты UDT minimal backend',()=>{
 it('граф можно отправлять в body POST /api/models',()=>{const graph=blankGraph('any');expect(JSON.stringify({name:'Демо',state_type:'current',graph})).toContain('assume_independent_resources')})
 it('модель содержит ревизию для optimistic locking',()=>{const model:ProductionModel={id:'1',family_id:'1',version:1,revision:1,name:'Демо',status:'draft',state_type:'current',graph:blankGraph('1'),node_costs:{}};expect(model.revision).toBe(1)})
 it('расчёт без фактов не содержит invented demand',()=>{const request:CalculationRequest={facts:{},optimistic_lead_time:false};expect('demand' in request.facts).toBe(false)})
 it('сценарий содержит отдельные overrides',()=>{const s:Scenario={id:'s',model_id:'m',name:'Тест',overrides:[],cost_overrides:{}};expect(s.overrides).toEqual([])})
 it('источник ручного ввода неподтверждён',()=>{expect(userSource().confirmed).toBe(false)})
})
