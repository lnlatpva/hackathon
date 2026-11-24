export type UserRole = 'administrator' | 'technologist' | 'manager' | 'observer'
export type StateType = 'current' | 'ideal' | 'target'
export type NodeKind = 'operation' | 'inspection' | 'transport' | 'storage' | 'source' | 'sink'
export type SourceKind = 'measured' | 'normative' | 'synthetic_test_fixture' | 'synthetic_scenario' | 'document' | 'derived' | 'user_input'

export interface Source { kind: SourceKind; reference: string; confirmed: boolean; note?: string | null }
export interface Amount { value: string | number; unit: string; source: Source }
export interface GraphNode {
  id: string; name: string; kind: NodeKind
  processing_seconds?: Amount | null
  batch_size?: number | null
  units_per_finished?: string | number | null
  parallel_channels?: number | null
  available_seconds?: Amount | null
  output_item?: string | null
}
export interface GraphEdge {
  id: string; source_id: string; target_id: string
  kind: 'material' | 'information'
  item_id?: string | null
  transit_seconds?: Amount | null
  waiting_seconds?: Amount | null
  verification: 'confirmed' | 'inferred' | 'unresolved'
  source?: Source | null
}
export interface ResourcePool { id: string; name: string; available_seconds?: Amount | null }
export interface ResourceUse { node_id: string; resource_id: string; work_seconds_per_output?: Amount | null }
export interface ProductionGraph {
  id: string
  nodes: GraphNode[]; edges: GraphEdge[]
  resources: ResourcePool[]; resource_uses: ResourceUse[]
  target_id?: string | null
  assume_independent_resources: boolean
}
export interface ProductionModel {
  id: string; family_id: string; version: number; name: string
  status: 'draft' | 'published'; state_type: StateType
  revision: number; graph: ProductionGraph; node_costs: Record<string, Amount>
}
export interface Override { target_type: 'node' | 'edge' | 'resource' | 'resource_use'; target_id: string; field: 'processing_seconds' | 'batch_size' | 'units_per_finished' | 'parallel_channels' | 'available_seconds' | 'transit_seconds' | 'waiting_seconds' | 'work_seconds_per_output'; new_value: string; reason: string }
export interface Scenario { id: string; model_id: string; name: string; overrides: Override[]; cost_overrides: Record<string, Amount> }
export interface Count { value: number; source: Source }
export interface CalculationFacts {
  available_seconds?: Amount | null
  demand?: Count | null
  accepted?: Count | null
  presented?: Count | null
  period_seconds?: Amount | null
  busy_seconds?: Amount | null
  resource_available_seconds?: Amount | null
  downtime_seconds?: Amount | null
  scheduled_seconds?: Amount | null
  inventory_begin?: Amount | null
  inventory_end?: Amount | null
  total_cost?: Amount | null
  revenue?: Amount | null
}
export interface CalculationRequest {
  facts: CalculationFacts
  period_key?: string | null
  takt_seconds?: Amount | null
  optimistic_lead_time?: boolean
}
export interface Metric {
  code: string; value: string | number | null; unit: string | null
  status: 'calculated' | 'estimated' | 'unavailable'
  kind: 'observed' | 'normative' | 'projected' | 'estimated' | 'unknown'
  reasons: string[]; sources: string[]; period_key?: string | null
}
export interface Constraint { owner_type: 'operation' | 'resource'; owner_id: string; finished_equivalent_capacity: string | number; sources: string[] }
export interface Bottleneck { code: string; owner_type: 'operation' | 'resource'; owner_id: string; explanation: string; calculated_value: string | number; threshold_value?: string | number | null }
export interface Analysis {
  graph: { valid: boolean; issues: { code: string; message: string; node_id?: string | null; blocking: boolean }[]; order: string[] }
  capacity: { status: string; known_upper_bound: string | number | null; complete: boolean; constraints: Constraint[]; missing: string[]; assumptions: string[] }
  lead_time: { metric: Metric; critical_nodes: string[]; assumptions: string[] }
  bottlenecks: Bottleneck[]
}
export interface CalculationResult {
  model_hash: string
  metrics: Record<string, Metric>
  analysis: Analysis
  baseline_analysis: Analysis | null
  capacity_delta: string | null
  baseline_node_cost: Metric | null
  node_cost_delta: string | null
}
export interface CalculationRun {
  id: string; model_id: string; scenario_id: string | null
  created_at: string; input_hash: string
  input_snapshot: { request: CalculationRequest; graph: ProductionGraph; overrides?: Override[] | null }
  result: CalculationResult
}
export interface CurrentUser { id: string; login: string; role: UserRole }
export interface AuthToken { access_token: string; token_type: string }
