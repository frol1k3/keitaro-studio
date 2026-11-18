import json
import logging
import re
from pathlib import Path
from typing import List, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.db import ActivityLog, make_session_factory
from app.keitaro import KeitaroClient, KeitaroError
from app.service import create_campaign, get_campaign_detail, update_offers


class CreateCampaignInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    country: str
    offer_id: int = Field(gt=0)
    domain_id: int = Field(gt=0)
    group_id: int = Field(gt=0)
    traffic_source_id: int = Field(gt=0)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Название не может быть пустым")
        return value

    @field_validator("country")
    @classmethod
    def clean_country(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{2}", value):
            raise ValueError("Укажите двухбуквенный ISO-код страны")
        return value


class OfferInput(BaseModel):
    offer_id: int = Field(gt=0)
    share: int = Field(ge=0, le=100)
    state: Literal["active", "disabled"] = "active"


class UpdateOffersInput(BaseModel):
    expected_version: str = Field(min_length=16, max_length=16)
    offers: List[OfferInput] = Field(min_length=1)


def create_app(settings=None, transport=None):
    settings = settings or Settings()
    app = FastAPI(title="Keitaro Campaign Wrapper", version="1.0.0")
    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")
    client = KeitaroClient(settings.keitaro_base_url or "http://localhost", settings.keitaro_api_key, transport)
    sessions = make_session_factory(settings)

    def require_config():
        if not settings.configured:
            raise HTTPException(503, "Заполните KEITARO_BASE_URL и KEITARO_API_KEY в .env")

    def log_action(action, campaign_id, detail, stream_id=None):
        try:
            with sessions.begin() as db:
                db.add(ActivityLog(action=action, campaign_id=campaign_id,
                                   stream_id=stream_id, detail=json.dumps(detail, ensure_ascii=False)))
        except SQLAlchemyError:
            # Keitaro may already have committed the change; never report a false failure.
            logging.getLogger(__name__).warning("Audit log unavailable. Run alembic upgrade head")

    @app.exception_handler(KeitaroError)
    async def keitaro_error_handler(_, error):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=error.status, content={"detail": error.message})

    @app.get("/")
    async def index():
        return FileResponse(static / "index.html")

    @app.get("/api/status")
    async def status():
        return {"configured": settings.configured, "prefix": settings.campaign_prefix}

    @app.get("/api/catalog")
    async def catalog():
        require_config()
        return await client.catalog()

    @app.get("/api/campaigns")
    async def campaigns():
        require_config()
        rows = await client.request("GET", "campaigns", params={"limit": 500})
        return [x for x in rows if x.get("state") == "active"]

    @app.post("/api/campaigns", status_code=201)
    async def create(data: CreateCampaignInput):
        require_config()
        campaign = await create_campaign(client, **data.model_dump(), prefix=settings.campaign_prefix)
        log_action("create_campaign", campaign["id"], {"name": campaign["name"], "country": data.country})
        return campaign

    @app.get("/api/campaigns/{campaign_id}")
    async def campaign_detail(campaign_id: int):
        require_config()
        return await get_campaign_detail(client, campaign_id)

    @app.put("/api/campaigns/{campaign_id}/streams/{stream_id}/offers")
    async def save_offers(campaign_id: int, stream_id: int, data: UpdateOffersInput):
        require_config()
        detail = await update_offers(client, campaign_id, stream_id,
                                    [x.model_dump() for x in data.offers], data.expected_version)
        log_action("update_offers", campaign_id, {"offers": [x.model_dump() for x in data.offers]}, stream_id)
        return detail

    @app.get("/api/history")
    async def history():
        with sessions() as db:
            try:
                rows = db.scalars(select(ActivityLog).order_by(ActivityLog.id.desc()).limit(20)).all()
            except SQLAlchemyError:
                return []
        return [{"action": x.action, "campaign_id": x.campaign_id,
                 "stream_id": x.stream_id, "created_at": x.created_at.isoformat()}
                for x in rows]

    return app


app = create_app()

