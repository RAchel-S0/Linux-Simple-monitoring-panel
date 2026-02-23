from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class SystemMetricsHistory(Base):
    __tablename__ = "metrics_history"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    cpu_percent = Column(Float)
    memory_used_mb = Column(Float)
    memory_total_mb = Column(Float)
    net_bytes_sent = Column(Integer)  # Total bytes since boot
    net_bytes_recv = Column(Integer)  # Total bytes since boot

class ConfigStorage(Base):
    __tablename__ = "config"
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)
    value = Column(String)
