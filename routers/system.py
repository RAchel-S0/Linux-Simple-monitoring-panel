from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import psutil

from database import get_db
from models import SystemMetricsHistory
from auth import get_current_user

router = APIRouter(
    prefix="/api/system",
    tags=["system"],
    dependencies=[Depends(get_current_user)]
)

@router.get("/metrics/history")
def get_metrics_history(
    minutes: int = 60,
    start_time: str = None,
    end_time: str = None,
    db: Session = Depends(get_db)
):
    """获取历史监控数据（支持过去X分钟或特定时间段）"""
    query = db.query(SystemMetricsHistory)
    
    if start_time and end_time:
        try:
            # Parse ISO 8601 strings from frontend
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            query = query.filter(
                SystemMetricsHistory.timestamp >= start_dt,
                SystemMetricsHistory.timestamp <= end_dt
            )
        except ValueError:
            pass
    elif not (start_time and end_time):
        time_threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        query = query.filter(SystemMetricsHistory.timestamp >= time_threshold)
        
    records = query.order_by(SystemMetricsHistory.timestamp.asc()).all()
    
    # Calculate network speed based on diffs (this is simplistic, per 3 seconds)
    # ECharts needs arrays of arrays or parallel arrays
    timestamps = []
    cpu = []
    mem_mb = []
    net_sent_speed = [] # bytes per second
    net_recv_speed = [] # bytes per second
    
    for i in range(len(records)):
        r = records[i]
        # Store timestamp string formats for ECharts usually like ISO
        # Echarts handles ISO "2024-01-01T12:00:00Z" fine if formatted or timestamp
        # Let's send local ISO time
        # convert naive/utc to local (since frontend parses timezone)
        
        timestamps.append(r.timestamp.isoformat())
        cpu.append(r.cpu_percent)
        mem_mb.append(round(r.memory_used_mb, 2))
        
        if i == 0:
            net_sent_speed.append(0)
            net_recv_speed.append(0)
        else:
            prev_r = records[i-1]
            time_diff = (r.timestamp - prev_r.timestamp).total_seconds()
            if time_diff > 0:
                # Handle possible counter wrap-around (very rare but happens, psutil reset)
                s_diff = max(0, r.net_bytes_sent - prev_r.net_bytes_sent)
                r_diff = max(0, r.net_bytes_recv - prev_r.net_bytes_recv)
                net_sent_speed.append(round(s_diff / time_diff, 2))
                net_recv_speed.append(round(r_diff / time_diff, 2))
            else:
                net_sent_speed.append(0)
                net_recv_speed.append(0)

    return {
        "timestamps": timestamps,
        "cpu": cpu,
        "memory_used_mb": mem_mb,
        "net_sent_speed_bps": net_sent_speed,
        "net_recv_speed_bps": net_recv_speed,
        "memory_total_mb": records[0].memory_total_mb if records else 0,
    }

@router.delete("/metrics/history")
def clear_metrics_history(db: Session = Depends(get_db)):
    """清空所有历史监控数据"""
    try:
        db.query(SystemMetricsHistory).delete()
        db.commit()
        return {"status": "success", "message": "已成功清空所有历史系统指标数据"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}
@router.get("/metrics/realtime")
def get_realtime_metrics():
    """获取实时概览（独立于调度器，直接读取psutil）"""
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "memory": {
            "total_mb": round(mem.total / (1024*1024), 2),
            "used_mb": round(mem.used / (1024*1024), 2),
            "percent": mem.percent
        },
        "disk": {
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent": disk.percent
        },
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat()
    }
