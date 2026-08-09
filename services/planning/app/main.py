from __future__ import annotations

import hmac
import os
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Request

from .schemas import (
    AssignmentRequest,
    BottleneckRequest,
    ChatRequest,
    ChatResponse,
    DelayRequest,
    ForecastRequest,
    RootCauseRequest,
    ScheduleRequest,
)
from .scheduler import get_scheduler
from .services import (
    heuristic_assignment,
    moving_average_forecast,
    rule_based_root_cause,
)

# No default: an unset key must crash the process at import time rather than
# silently start an internet-reachable service protected by "dev-secret".
API_KEY = os.environ.get("HTPLUS_PLANNING_API_KEY") or ""
if not API_KEY:
    raise RuntimeError("HTPLUS_PLANNING_API_KEY is not set")

app = FastAPI(title="HTPlus Planning Engine", version="0.1.0")

JOBS: Dict[str, Dict[str, Any]] = {}
JOBS_LOCK = threading.Lock()


def require_api_key(request: Request):
    header = request.headers.get("Authorization", "")
    scheme, _, key = header.partition(" ")
    # compare_digest avoids leaking the key length/prefix through timing.
    if scheme.lower() != "bearer" or not hmac.compare_digest(key.strip(), API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _run_job(job_id: str, fn, *args):
    def worker():
        try:
            data = fn(*args)
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "success", "data": data, "finished_at": datetime.utcnow().isoformat()}
        except Exception as error:  # noqa: BLE001
            with JOBS_LOCK:
                JOBS[job_id] = {"status": "failed", "error": str(error), "finished_at": datetime.utcnow().isoformat()}

    threading.Thread(target=worker, daemon=True).start()


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "service": "htplus-ai",
        "time": datetime.utcnow().isoformat(),
        "fallback_engine": True,
    }


@app.post("/api/v1/forecast", dependencies=[Depends(require_api_key)])
def forecast(payload: ForecastRequest):
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", "created_at": datetime.utcnow().isoformat()}
    _run_job(
        job_id,
        moving_average_forecast,
        payload.product_ids,
        [item.dict() for item in payload.history],
        payload.horizon_days,
    )
    return {"success": True, "forecast_id": job_id}


@app.post("/api/v1/schedule/recommend", dependencies=[Depends(require_api_key)])
def schedule_recommend(payload: ScheduleRequest):
    job_id = str(uuid.uuid4())
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", "created_at": datetime.utcnow().isoformat()}
    scheduler = get_scheduler(payload.algorithm)
    _run_job(
        job_id,
        scheduler.schedule,
        [wo.dict() for wo in payload.workorders],
        payload.constraints.dict(),
        payload.objective,
    )
    return {"success": True, "job_id": job_id}


@app.post("/api/v1/assignment/recommend", dependencies=[Depends(require_api_key)])
def assignment_recommend(payload: AssignmentRequest):
    result = heuristic_assignment(
        [wo.dict() for wo in payload.workorders],
        [emp.dict() for emp in payload.employees],
        {int(k): v for k, v in payload.skill_matrix.items()},
    )
    return {"success": True, "assignment_result": result, "model": "heuristic_fallback"}


@app.post("/api/v1/bottleneck/predict", dependencies=[Depends(require_api_key)])
def bottleneck_predict(payload: BottleneckRequest):
    return {
        "success": True,
        "bottleneck_result": [
            {"workcenter_id": 1, "machine_id": 2, "score": 0.82, "factor_type": "load", "period": payload.period},
            {"workcenter_id": 3, "machine_id": 5, "score": 0.64, "factor_type": "setup", "period": payload.period},
        ],
        "model": "stub",
    }


@app.post("/api/v1/delay/predict", dependencies=[Depends(require_api_key)])
def delay_predict(payload: DelayRequest):
    predictions = []
    for wo in payload.workorders:
        if int(wo.priority) < 0:
            predictions.append({"workorder_id": wo.workorder_id, "delay_hours": 2.5, "reason": "low priority"})
        else:
            predictions.append({"workorder_id": wo.workorder_id, "delay_hours": 0.0, "reason": "on track"})
    return {"success": True, "delay_result": predictions, "model": "stub"}


@app.post("/api/v1/root-cause", dependencies=[Depends(require_api_key)])
def root_cause(payload: RootCauseRequest):
    causes = rule_based_root_cause(payload.history)
    return {"success": True, "causes": causes, "model": "rule_fallback"}


@app.post("/api/v1/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)])
def chat(payload: ChatRequest):
    context = payload.context or {}
    reply = (
        f"Đã nhận câu hỏi về workcenter {context.get('workcenter_id', '?')}. "
        "Đây là engine dự phòng; gợi ý: kiểm tra downtime và capacity rule."
    )
    return ChatResponse(
        reply=reply,
        recommendations=[{"type": "schedule", "summary": "Review capacity at the work center."}],
        payload={"session_id": payload.session_id, "message": payload.message},
    )


@app.get("/api/v1/job/{job_id}", dependencies=[Depends(require_api_key)])
def get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"success": job["status"] == "success", "status": job["status"], "data": job.get("data"), "error": job.get("error")}


@app.get("/api/v1/recommendation/{job_id}/explain", dependencies=[Depends(require_api_key)])
def explain(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "success": True,
        "explanation": "Feature attribution not available in fallback engine; based on priority and due date ordering.",
        "payload": job.get("data"),
    }
