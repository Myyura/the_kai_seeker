import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StudyTarget(Base):
    """A user-defined study target (school + program + exam info)."""

    __tablename__ = "study_targets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    school_id: Mapped[str] = mapped_column(String(128), nullable=False)
    program_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
