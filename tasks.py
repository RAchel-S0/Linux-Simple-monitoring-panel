import psutil
from database import SessionLocal
from models import SystemMetricsHistory
from datetime import datetime, timezone

def collect_system_metrics():
    # Use context manager to ensure DB session is closed
    with SessionLocal() as db:
        try:
            # CPU
            cpu_percent = psutil.cpu_percent(interval=None) # Non-blocking in background
            
            # Memory
            mem = psutil.virtual_memory()
            memory_used_mb = mem.used / (1024 * 1024)
            memory_total_mb = mem.total / (1024 * 1024)
            
            # Network (Total across all interfaces)
            net_io = psutil.net_io_counters()
            
            new_record = SystemMetricsHistory(
                timestamp=datetime.now(timezone.utc),
                cpu_percent=cpu_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
                net_bytes_sent=net_io.bytes_sent,
                net_bytes_recv=net_io.bytes_recv
            )
            
            db.add(new_record)
            
            # Optional: Housekeeping, delete records older than X days to keep DB small
            # (Can implement later if needed, for now just append)
            
            db.commit()
        except Exception as e:
            print(f"Error collecting metrics: {e}")
            db.rollback()
