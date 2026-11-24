import type { Amount, GraphEdge, GraphNode, NodeKind, ProductionGraph, Source } from '../api/types'

export const NODE_KINDS: Record<NodeKind, string> = {
  operation: 'Операция', inspection: 'Контроль', transport: 'Транспортировка',
  storage: 'Хранение', source: 'Источник', sink: 'Получатель',
}
export const STATE_LABELS = { current: 'Текущее', ideal: 'Идеальное', target: 'Целевое' } as const

export function userSource(reference = 'user:frontend-manual-input'): Source {
  return { kind: 'user_input', reference, confirmed: false, note: 'Введено пользователем, не подтверждено измерением' }
}
export function measuredSeconds(value: string | number | null | undefined, source: Source): Amount | null {
  if (value === '' || value === null || value === undefined) return null
  const n = Number(value)
  if (!Number.isFinite(n) || n < 0) throw new Error('Время должно быть неотрицательным числом')
  if (!source.reference.trim()) throw new Error('Укажите источник значения')
  return { value: String(value), unit: 's', source }
}
export function optionalPositiveInt(v: string | number): number | null {
  if (!String(v ?? '').trim()) return null
  const n = Number(v)
  if (!Number.isInteger(n) || n < 1) throw new Error('Введите положительное целое число')
  return n
}
export function optionalPositiveDecimal(v: string | number): string | null {
  const text = String(v ?? '').trim()
  if (!text) return null
  const n = Number(text)
  if (!Number.isFinite(n) || n <= 0) throw new Error('Введите положительное число')
  return text
}
export function blankGraph(id = 'draft'): ProductionGraph {
  return { id, nodes: [], edges: [], resources: [], resource_uses: [], target_id: null, assume_independent_resources: false }
}
export function createNode(kind: NodeKind, index: number): GraphNode {
  return { id: `N-${crypto.randomUUID().slice(0, 8)}`, name: `${NODE_KINDS[kind]} ${index + 1}`, kind,
    processing_seconds: null, batch_size: null, parallel_channels: null,
    units_per_finished: null, available_seconds: null, output_item: null }
}
export function createEdge(sourceId: string, targetId: string): GraphEdge {
  if (sourceId === targetId) throw new Error('Нельзя соединить узел сам с собой')
  return { id: `E-${crypto.randomUUID().slice(0, 8)}`, source_id: sourceId, target_id: targetId,
    kind: 'material', verification: 'unresolved', transit_seconds: null, waiting_seconds: null }
}
export function graphProblems(graph: ProductionGraph): string[] {
  const problems: string[] = []
  const nodes = new Set(graph.nodes.map(n => n.id))
  const nodeIds = graph.nodes.map(n => n.id)
  if (nodes.size !== nodeIds.length) problems.push('Повторяющиеся ID узлов')
  // Подсветка ошибок до сохранения; сервер повторно проверяет структуру графа.
  const resources = new Set(graph.resources.map(r=>r.id))
  if(resources.size !== graph.resources.length) problems.push('Повторяющиеся ID ресурсов')
  if(new Set(graph.edges.map(e=>e.id)).size !== graph.edges.length) problems.push('Повторяющиеся ID связей')
  const assignments=new Set<string>()
  for(const use of graph.resource_uses) {
    if(!nodes.has(use.node_id)||!resources.has(use.resource_id)) problems.push(`Неизвестное назначение ресурса: ${use.node_id} / ${use.resource_id}`)
    const key=`${use.node_id}::${use.resource_id}`
    if(assignments.has(key)) problems.push(`Повторное назначение ресурса: ${key}`)
    assignments.add(key)
  }
  const links = new Set<string>()
  for (const edge of graph.edges) {
    if (!nodes.has(edge.source_id) || !nodes.has(edge.target_id)) problems.push(`Связь ${edge.id} содержит неизвестный узел`)
    if (edge.source_id === edge.target_id) problems.push(`Связь ${edge.id} соединяет узел с самим собой`)
    const key = `${edge.source_id}/${edge.target_id}/${edge.kind}/${edge.item_id ?? ''}`
    if (links.has(key)) problems.push(`Дублирующаяся связь: ${edge.source_id} → ${edge.target_id}`)
    links.add(key)
  }
  const outgoing = new Map(graph.nodes.map(n => [n.id, [] as string[]]))
  // Проверка циклов относится только к материальным связям.
  for (const e of graph.edges.filter(e => e.kind === 'material')) outgoing.get(e.source_id)?.push(e.target_id)
  const visited = new Set<string>(); const active = new Set<string>()
  function dfs(id: string): boolean {
    if (active.has(id)) return true
    if (visited.has(id)) return false
    visited.add(id); active.add(id)
    for (const next of outgoing.get(id) || []) if (dfs(next)) return true
    active.delete(id); return false
  }
  if (graph.nodes.some(n => dfs(n.id))) problems.push('Обнаружен цикл материального потока')
  if (graph.target_id && !nodes.has(graph.target_id)) problems.push('Конечный узел не существует')
  return problems
}
export function layoutKey(modelId: string): string { return `udt.graph.layout.${modelId}` }
export type PositionMap = Record<string, { x: number; y: number }>
export function layoutGraph(graph: ProductionGraph, saved: PositionMap = {}): PositionMap {
  const output: PositionMap = {}
  // Автоматическая раскладка по глубине графа; ручные координаты имеют приоритет.
  const depth = new Map<string, number>()
  const prev = new Map<string, string[]>()
  graph.nodes.forEach(n => { depth.set(n.id, 0); prev.set(n.id, []) })
  graph.edges.filter(e => e.kind === 'material').forEach(e => prev.get(e.target_id)?.push(e.source_id))
  for (let pass = 0; pass < graph.nodes.length; pass++) {
    let changed = false
    for (const n of graph.nodes) {
      const parents = prev.get(n.id) || []
      const next = parents.length ? Math.max(...parents.map(p => depth.get(p) || 0)) + 1 : 0
      if (next > (depth.get(n.id) || 0)) { depth.set(n.id, next); changed = true }
    }
    if (!changed) break
  }
  const rows = new Map<number, number>()
  graph.nodes.forEach(n => {
    const col = Math.min(depth.get(n.id) || 0, graph.nodes.length)
    const row = rows.get(col) || 0
    output[n.id] = saved[n.id] ?? { x: 80 + col * 295, y: 90 + row * 180 }
    rows.set(col, row + 1)
  })
  return output
}
