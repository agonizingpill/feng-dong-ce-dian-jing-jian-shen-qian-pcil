from sqlalchemy import String,Float,ForeignKey,JSON,CheckConstraint
from sqlalchemy.orm import Mapped,mapped_column
from .db import Base
class BlindBatch(Base):
    __tablename__='blind_batches'
    __table_args__=(CheckConstraint("state in ('sealed','consumed')"),CheckConstraint('mae_limit > 0'))
    id:Mapped[int]=mapped_column(primary_key=True)
    code:Mapped[str]=mapped_column(String(60),unique=True)
    mae_limit:Mapped[float]=mapped_column(Float)
    state:Mapped[str]=mapped_column(String(20),default='sealed')
    created_by:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[str]=mapped_column(String(40))
class BlindBatchSweep(Base):
    __tablename__='blind_batch_sweeps'
    id:Mapped[int]=mapped_column(primary_key=True)
    batch_id:Mapped[int]=mapped_column(ForeignKey('blind_batches.id'))
    # A sweep may enter at most one blind batch in its lifetime: sealed samples
    # never rejoin ranking or training, even after the batch is consumed.
    sweep_id:Mapped[int]=mapped_column(ForeignKey('sweeps.id'),unique=True)
class BlindVerification(Base):
    __tablename__='blind_verifications'
    __table_args__=(CheckConstraint("verdict in ('passed','failed')"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    # One acceptance per batch, ever. Unique key is the backstop for the row lock.
    batch_id:Mapped[int]=mapped_column(ForeignKey('blind_batches.id'),unique=True)
    layout_id:Mapped[int]=mapped_column(ForeignKey('layouts.id'))
    probe_ids:Mapped[list]=mapped_column(JSON)
    source_checksum:Mapped[str]=mapped_column(String(64))
    mae:Mapped[float]=mapped_column(Float)
    mae_limit:Mapped[float]=mapped_column(Float)
    verdict:Mapped[str]=mapped_column(String(20))
    detail:Mapped[dict]=mapped_column(JSON)
    submitted_by:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[str]=mapped_column(String(40))
