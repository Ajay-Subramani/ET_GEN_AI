from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import get_settings
from app.graph import run_recommendation
from app.repository import Repository


app = FastAPI(title="AI Investor Agent", version="0.1.0")


class RecommendationRequest(BaseModel):
    symbol: str
    user_id: str


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "env": settings.app_env}


@app.get("/demo/users")
def demo_users() -> dict[str, object]:
    repo = Repository()
    return {
        "default_user_id": get_settings().default_user_id,
        "demo_user": repo.get_user_portfolio(get_settings().default_user_id),
    }


@app.post("/analyze")
def analyze(payload: RecommendationRequest) -> dict[str, object]:
    recommendation = run_recommendation(payload.symbol, payload.user_id)
    body = recommendation.model_dump()
    body["summary"] = recommendation.summary
    return body
