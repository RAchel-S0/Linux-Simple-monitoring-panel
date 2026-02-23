import os
import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from auth import get_current_user

router = APIRouter(
    prefix="/api/process",
    tags=["process"],
    dependencies=[Depends(get_current_user)]
)

SERVICE_DICT = {
    "sshd": "SSH服务",
    "mysqld": "MySQL数据库",
    "nginx": "Nginx服务器",
    "python": "Python应用",
    "python3": "Python应用",
    "node": "Node.js应用",
    "docker": "Docker",
    "dockerd": "Docker守护进程",
    "redis-server": "Redis数据库",
    "java": "Java应用",
    "php-fpm": "PHP运行环境",
    "systemd": "系统核心守护进程"
}

@router.get("/list")
def list_processes():
    """获取运行中的进程列表，附加端口映射和中文注释。按内存消耗排序。"""
    
    # 1. First map PID -> List of listening ports
    pid_to_ports = {}
    try:
        # Require Admin/Root to see all.
        connections = psutil.net_connections(kind='inet')
        for c in connections:
            if c.status == 'LISTEN' and c.pid:
                if c.pid not in pid_to_ports:
                    pid_to_ports[c.pid] = []
                port = c.laddr.port
                if port not in pid_to_ports[c.pid]:
                    pid_to_ports[c.pid].append(port)
    except psutil.AccessDenied:
        pass # Handle gracefully if no root, though some might be missing

    # 2. Collect Processes
    processes = []
    
    # Just iterate all processes
    for p in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'memory_info']):
        try:
            info = p.info
            name = info['name'] or ""
            
            # Simple match for service description
            desc = ""
            for key, val in SERVICE_DICT.items():
                if name.lower().startswith(key.lower()):
                    desc = val
                    break
                    
            processes.append({
                "pid": info['pid'],
                "name": name,
                "user": info['username'] or "Unknown",
                "cpu_percent": info['cpu_percent'] or 0.0,
                # Convert bytes to MB
                "memory_mb": round((info['memory_info'].rss if info['memory_info'] else 0) / (1024 * 1024), 2),
                "ports": pid_to_ports.get(info['pid'], []),
                "description": desc
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
            
    # Sort by memory usage descending and return top 100 to avoid freezing the front-end
    processes.sort(key=lambda x: x['memory_mb'], reverse=True)
    return processes[:100]

@router.post("/kill/{pid}")
def kill_process(pid: int):
    """安全查杀指定进程"""
    # Self-protection logic
    if pid == os.getpid():
        raise HTTPException(status_code=400, detail="不能结束监控面板自身的进程")
        
    try:
        p = psutil.Process(pid)
        name = p.name()
        
        # Don't let users casually kill vital system processes
        if name in ['systemd', 'init']:
            raise HTTPException(status_code=400, detail=f"禁止结束核心系统进程: {name}")
            
        p.terminate() # or p.kill() 
        p.wait(timeout=3)
        return {"status": "success", "message": f"进程 {pid} ({name}) 已被结束"}
    except psutil.NoSuchProcess:
        raise HTTPException(status_code=404, detail="进程不存在")
    except psutil.AccessDenied:
        raise HTTPException(status_code=403, detail="权限拒绝: 无法结束该进程")
    except psutil.TimeoutExpired:
        raise HTTPException(status_code=500, detail="进程未能及时终止")
