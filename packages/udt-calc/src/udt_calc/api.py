"""Опциональный роутер FastAPI; импорт для сохранения независимости ядра фреймворка."""
from __future__ import annotations
from .contracts import Amount, Model, Scenario
from .engine import analyze
from .scenarios import compare_scenario
from pydantic import BaseModel


class AnalyzeRequest(BaseModel):
    model: Model
    takt_seconds: Amount | None = None
    demand: int | None = None
    optimistic_lead_time: bool = False


class CompareRequest(BaseModel):
    model: Model
    scenario: Scenario
    takt_seconds: Amount | None = None
    demand: int | None = None


def create_router():
    from fastapi import APIRouter, HTTPException
    from .scenarios import ScenarioError
    router = APIRouter(prefix="/api/v1/calculation", tags=["calculation"])

    @router.post("/analyze")
    def calculate(request: AnalyzeRequest):
        return analyze(request.model, takt_seconds=request.takt_seconds, demand=request.demand,
                       optimistic_lead_time=request.optimistic_lead_time)

    @router.post("/compare")
    def compare(request: CompareRequest):
        try:
            return compare_scenario(request.model, request.scenario,
                                    takt_seconds=request.takt_seconds, demand=request.demand)
        except ScenarioError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return router