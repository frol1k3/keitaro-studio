from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import Settings


class Base(DeclarativeBase):
    pass


class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    campaign_id: Mapped[int] = mapped_column(Integer, nullable=False)
    stream_id: Mapped[Optional[int]] = mapped_column(Integer)
    detail: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


def make_session_factory(settings: Settings):
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    engine = create_engine(settings.database_url, connect_args=connect_args)
    return sessionmaker(engine, expire_on_commit=False)

