import { describe, expect, it } from 'vitest'
import { blankGraph, createEdge, graphProblems, layoutGraph, measuredSeconds, optionalPositiveInt, optionalPositiveDecimal, userSource } from '../lib/graph'
import type { ProductionGraph } from '../api/types'
const graph=():ProductionGraph=>({id:'demo',nodes:[{id:'A',name:'A',kind:'operation'},{id:'B',name:'B',kind:'operation'},{id:'C',name:'C',kind:'inspection'}],edges:[],resources:[],resource_uses:[],target_id:'C',assume_independent_resources:false})
describe('Производственный граф',()=>{
 it('создаёт пустой граф без вымышленных измерений',()=>{const g=blankGraph();expect(g.nodes).toEqual([]);expect(g.target_id).toBeNull()})
 it('не создаёт цикл в новом графе',()=>{expect(graphProblems(graph())).toEqual([])})
 it('отклоняет самосвязь',()=>{expect(()=>createEdge('A','A')).toThrow()})
 it('находит материальный цикл',()=>{const g=graph();g.edges=[createEdge('A','B'),createEdge('B','C'),createEdge('C','A')];expect(graphProblems(g)).toContain('Обнаружен цикл материального потока')})
 it('информационная обратная связь не делает материальный DAG циклическим',()=>{const g=graph();g.edges=[createEdge('A','B'),{...createEdge('B','A'),kind:'information'}];expect(graphProblems(g)).toEqual([])})
 it('отклоняет ссылку на неизвестный узел',()=>{const g=graph();g.edges=[createEdge('A','Z')];expect(graphProblems(g).some(s=>s.includes('неизвестный'))).toBe(true)})
 it('отклоняет повторяющиеся связи',()=>{const g=graph();g.edges=[createEdge('A','C'),createEdge('A','C')];expect(graphProblems(g).some(s=>s.includes('Дублирующаяся'))).toBe(true)})
 it('не принимает назначение неизвестного ресурса',()=>{const g=graph();g.resource_uses=[{node_id:'A',resource_id:'NONE'}];expect(graphProblems(g).some(s=>s.includes('Неизвестное назначение ресурса'))).toBe(true)})
 it('не принимает повторное назначение ресурса',()=>{const g=graph();g.resources=[{id:'R1',name:'Оператор'}];g.resource_uses=[{node_id:'A',resource_id:'R1'},{node_id:'A',resource_id:'R1'}];expect(graphProblems(g).some(s=>s.includes('Повторное назначение ресурса'))).toBe(true)})
 it('создаёт стабильную раскладку по глубине графа',()=>{const g=graph();g.edges=[createEdge('A','C'),createEdge('B','C')];const pos=layoutGraph(g);expect(pos.C!.x).toBeGreaterThan(pos.A!.x);expect(pos.A!.x).toBe(pos.B!.x)})
 it('сохраняет пользовательские координаты',()=>{const pos=layoutGraph(graph(),{A:{x:7,y:9}});expect(pos.A).toEqual({x:7,y:9})})
})
describe('Работа с неизвестными значениями',()=>{
 it('не подменяет пустой ввод нулём',()=>{expect(measuredSeconds('',userSource())).toBeNull()})
 it('сохраняет источник пользовательского ввода',()=>{expect(measuredSeconds('20',userSource('user:test'))?.source.reference).toBe('user:test')})
 it('отклоняет отрицательное время',()=>{expect(()=>measuredSeconds('-1',userSource())).toThrow()})
 it('не подставляет 1 для неизвестного количества',()=>{expect(optionalPositiveInt('')).toBeNull()})
 it('отклоняет дробное число каналов',()=>{expect(()=>optionalPositiveInt('1.5')).toThrow()})
 it('сохраняет точную строку положительного коэффициента',()=>{expect(optionalPositiveDecimal('0.125')).toBe('0.125')})
})
