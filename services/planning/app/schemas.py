from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class HistoryItem(BaseModel):
    date: str
    product_id: int
    qty: float


class ForecastRequest(BaseModel):
    company_id: int = 1
    product_ids: List[int]
    horizon_days: int = 90
    granularity: str = "day"
    history: List[HistoryItem] = []


class WorkOrderInput(BaseModel):
    workorder_id: int
    product_id: int
    qty: float
    routing: List[int] = []
    due: Optional[str] = None
    priority: int = 0


class ConstraintInput(BaseModel):
    workcenters: List[Dict[str, Any]] = []
    machines: List[Dict[str, Any]] = []
    shifts: List[Dict[str, Any]] = []
    holidays: List[str] = []
    rules: Dict[str, Any] = {}
    lock_workorder_ids: List[int] = []


class ScheduleRequest(BaseModel):
    workorders: List[WorkOrderInput]
    constraints: ConstraintInput = ConstraintInput()
    objective: str = "min_tardiness"
    algorithm: Literal["rule_engine", "solver_cpsat"] = "rule_engine"


class EmployeeInput(BaseModel):
    employee_id: int
    skills: List[int] = []
    max_hours: float = 8.0
    ot_hours: float = 0.0


class AssignmentRequest(BaseModel):
    workorders: List[WorkOrderInput]
    employees: List[EmployeeInput]
    skill_matrix: Dict[str, List[int]] = {}
    shifts: List[Dict[str, Any]] = []


class BottleneckRequest(BaseModel):
    period: str = "day"


class DelayRequest(BaseModel):
    workorders: List[WorkOrderInput]


class RootCauseRequest(BaseModel):
    workorder_id: int
    history: List[Dict[str, Any]] = []


class ChatRequest(BaseModel):
    session_id: str
    message: str
    context: Dict[str, Any] = {}


class ChatResponse(BaseModel):
    reply: str
    recommendations: List[Dict[str, Any]] = []
    payload: Dict[str, Any] = {}
