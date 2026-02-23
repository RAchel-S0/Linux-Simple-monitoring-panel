import psutil
import socket
from fastapi import APIRouter, Depends
from auth import get_current_user
import time

router = APIRouter(
    prefix="/api/network",
    tags=["network"],
    dependencies=[Depends(get_current_user)]
)

# Global variables to store the previous connection snapshot for calculating diffs
_last_connections_snapshot = set()
_last_snapshot_time = 0

@router.get("/interfaces")
def get_network_interfaces():
    """获取所有网卡的基本信息"""
    net_if_addrs = psutil.net_if_addrs()
    net_if_stats = psutil.net_if_stats()
    
    interfaces = []
    
    for nic_name, addrs in net_if_addrs.items():
        nic_info = {
            "name": nic_name,
            "mac": None,
            "ipv4": [],
            "ipv6": [],
            "is_up": net_if_stats[nic_name].isup if nic_name in net_if_stats else False,
            "speed": net_if_stats[nic_name].speed if nic_name in net_if_stats else 0
        }
        
        for snicaddr in addrs:
            if snicaddr.family == socket.AF_INET:
                nic_info["ipv4"].append(snicaddr.address)
            elif snicaddr.family == getattr(socket, 'AF_INET6', socket.AF_INET): 
                # AF_INET6 might not exist on all systems
                if snicaddr.family != socket.AF_INET and getattr(socket, 'AF_INET6', None) and snicaddr.family == socket.AF_INET6:
                    nic_info["ipv6"].append(snicaddr.address)
            elif snicaddr.family == getattr(psutil, 'AF_LINK', -1):
                nic_info["mac"] = snicaddr.address
                
        interfaces.append(nic_info)
        
    return interfaces

@router.get("/connections")
def get_network_connections():
    """获取并统计当前网络连接，并计算 3 秒动态连接速率"""
    global _last_connections_snapshot, _last_snapshot_time
    
    connections = []
    try:
        # Accessing all connections requires root/Admin on some OS.
        # using 'inet' gets all tcp and udp
        connections = psutil.net_connections(kind='inet')
    except psutil.AccessDenied:
        # On windows without admin, we might only get our own process connections
        pass

    # Current snapshot signatures. 
    # A connection signature could be (laddr.ip, laddr.port, raddr.ip, raddr.port, status)
    current_snapshot = set()
    status_counts = {}
    
    for c in connections:
        st = c.status
        status_counts[st] = status_counts.get(st, 0) + 1
        
        if st in ['ESTABLISHED', 'TIME_WAIT', 'CLOSE_WAIT', 'SYN_SENT', 'SYN_RECV']:
            sig = (
                c.laddr.ip if c.laddr else '',
                c.laddr.port if c.laddr else 0,
                c.raddr.ip if c.raddr else '',
                c.raddr.port if c.raddr else 0
            )
            current_snapshot.add(sig)

    # Calculate diff
    current_time = time.time()
    time_diff = current_time - _last_snapshot_time
    
    # Only calculate meaningful diff if within a reasonable refresh window (e.g., 2-5 seconds).
    # If the user just loaded the page, rates are 0.
    new_conns = 0
    closed_conns = 0
    
    if 1 < time_diff < 10 and _last_connections_snapshot:
        new_conns = len(current_snapshot - _last_connections_snapshot)
        closed_conns = len(_last_connections_snapshot - current_snapshot)
        # Normalize to per 3 seconds if client request timing varies slightly
        rate_multiplier = 3.0 / time_diff
        new_conns = int(new_conns * rate_multiplier)
        closed_conns = int(closed_conns * rate_multiplier)

    # Update global state
    _last_connections_snapshot = current_snapshot
    _last_snapshot_time = current_time
    
    return {
        "status_counts": status_counts,
        "total_connections": len(connections),
        "rate": {
            "new_per_3s": new_conns,
            "closed_per_3s": closed_conns
        }
    }
