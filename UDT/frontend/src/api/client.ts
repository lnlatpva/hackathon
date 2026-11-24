import axios from 'axios'
import type { AuthToken, CalculationRequest, CalculationRun, CurrentUser, ProductionGraph, ProductionModel, Scenario, Override, Amount, StateType } from './types'

export const TOKEN_KEY = 'udt.access_token'

const client = axios.create({ baseURL: '/api', timeout: 30000 })
client.interceptors.request.use(config => {
  const token = sessionStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})
client.interceptors.response.use(r => r, error => {
  if (error.response?.status === 401 && !String(error.config?.url || '').includes('/auth/login')) {
    sessionStorage.removeItem(TOKEN_KEY)
    window.dispatchEvent(new Event('udt:unauthorized'))
  }
  return Promise.reject(error)
})

export function errorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) return 'Не удалось подключиться к серверу. Проверьте запуск API.'
    const detail = error.response.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) return detail.map((e: {loc?: string[]; msg?: string}) => `${e.loc?.join('.') || 'Поле'}: ${e.msg || ''}`).join('; ')
    if (detail?.message) return [detail.message, ...(detail.issues || []).map((e: {message: string}) => e.message)].join('; ')
    return `Ошибка сервера: ${error.response.status}`
  }
  return error instanceof Error ? error.message : 'Неизвестная ошибка'
}

export const api = {
  async login(login: string, password: string) { const { data } = await client.post<AuthToken>('/auth/login', { login, password }); return data },
  async setup(login: string, password: string) { const { data } = await client.post<AuthToken>('/auth/setup', { login, password }); return data },
  async me() { const { data } = await client.get<CurrentUser>('/auth/me'); return data },
  async models() { const { data } = await client.get<ProductionModel[]>('/models'); return data },
  async model(id: string) { const { data } = await client.get<ProductionModel>(`/models/${id}`); return data },
  async createModel(body: {name: string; state_type: StateType; graph?: ProductionGraph; node_costs?: Record<string, Amount>}) {
    const { data } = await client.post<ProductionModel>('/models', body); return data
  },
  async updateModel(id: string, body: {name: string; state_type: StateType; graph: ProductionGraph; expected_revision: number; node_costs: Record<string, Amount>}) {
    const { data } = await client.put<ProductionModel>(`/models/${id}`, body); return data
  },
  async deleteModel(id: string, confirmName: string) { await client.delete(`/models/${id}`, {data: {confirm_name: confirmName}}) },
  async publish(id: string) { const { data } = await client.post<ProductionModel>(`/models/${id}/publish`); return data },
  async clone(id: string) { const { data } = await client.post<ProductionModel>(`/models/${id}/versions`); return data },
  async versions(id: string) { const { data } = await client.get<ProductionModel[]>(`/models/${id}/versions`); return data },
  async scenarios(id: string) { const { data } = await client.get<Scenario[]>(`/models/${id}/scenarios`); return data },
  async createScenario(id: string, body: {name: string; overrides: Override[]; cost_overrides?: Record<string, Amount>}) {
    const { data } = await client.post<Scenario>(`/models/${id}/scenarios`, body); return data
  },
  async updateScenario(id: string, body: {name: string; overrides: Override[]; cost_overrides?: Record<string, Amount>}) {
    const { data } = await client.put<Scenario>(`/scenarios/${id}`, body); return data
  },
  async runModel(id: string, request: CalculationRequest) { const { data } = await client.post<CalculationRun>(`/models/${id}/calculate`, request); return data },
  async runScenario(id: string, request: CalculationRequest) { const { data } = await client.post<CalculationRun>(`/scenarios/${id}/calculate`, request); return data },
  async runs(id: string) { const { data } = await client.get<CalculationRun[]>(`/models/${id}/runs`); return data },
  async run(id: string) { const { data } = await client.get<CalculationRun>(`/runs/${id}`); return data },
}
