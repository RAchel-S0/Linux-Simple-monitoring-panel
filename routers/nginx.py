import os
import re
import psutil
import time
import requests
from collections import Counter
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import ConfigStorage
from auth import get_current_user

router = APIRouter(
    prefix="/api/nginx",
    tags=["nginx"],
    dependencies=[Depends(get_current_user)]
)

class NginxConfigModel(BaseModel):
    log_path: str

def get_nginx_process():
    for p in psutil.process_iter(['pid', 'name', 'create_time']):
        if p.info['name'] == 'nginx' or p.info['name'] == 'nginx.exe':
            return p.info
    return None

@router.get("/status")
def get_nginx_status():
    proc = get_nginx_process()
    if proc:
        uptime = time.time() - proc['create_time']
        return {
            "running": True,
            "pid": proc['pid'],
            "uptime_seconds": uptime
        }
    return {
        "running": False,
        "pid": None,
        "uptime_seconds": 0
    }

@router.get("/config")
def get_nginx_config(db: Session = Depends(get_db)):
    record = db.query(ConfigStorage).filter(ConfigStorage.key == "nginx_log_path").first()
    return {"log_path": record.value if record else "/var/log/nginx/access.log"}

@router.post("/config")
def save_nginx_config(config: NginxConfigModel, db: Session = Depends(get_db)):
    record = db.query(ConfigStorage).filter(ConfigStorage.key == "nginx_log_path").first()
    if record:
        record.value = config.log_path
    else:
        new_record = ConfigStorage(key="nginx_log_path", value=config.log_path)
        db.add(new_record)
    db.commit()
    return {"status": "success"}

# Simple regex to extract IP from standard combined nginx log format
# Example: 127.0.0.1 - - [10/Oct/2000:13:55:36 -0700] "GET /foo.html HTTP/1.0" 200 2326
IP_REGEX = re.compile(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})')

@router.get("/analyze")
def analyze_nginx_logs(lines: int = 5000, db: Session = Depends(get_db)):
    """解析 Nginx 日志并获取 Top IPs 及地理位置映射"""
    config = db.query(ConfigStorage).filter(ConfigStorage.key == "nginx_log_path").first()
    log_path = config.value if config else "/var/log/nginx/access.log"
    
    if not os.path.exists(log_path):
        return {"error": f"Log file not found at {log_path}"}
        
    try:
        # Read the last N lines efficiently
        # Since standard python doesn't have a reliable tail without reading the whole file,
        # we will chunk read from the end or just read all if the file isn't massive.
        # For simplicity and robust parsing here, we'll read all lines but keep the last N.
        # Ideally, we should use a reverse reader for huge files.
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # simple tail approximation
            all_lines = f.readlines()
            target_lines = all_lines[-lines:]
            
        ip_counter = Counter()
        for line in target_lines:
            match = IP_REGEX.search(line)
            if match:
                ip_counter[match.group(1)] += 1
                
        top_ips = ip_counter.most_common(50)
        
        # Resolve GeoIP using free ip-api.com batch endpoint
        # The batch API takes a POST request with an array of IPs, up to 100 at a time.
        results = []
        if top_ips:
            ips_to_query = [ip[0] for ip in top_ips]
            
            # Simple caching or batching: Note ip-api batch allows 15 requests per minute maximum.
            try:
                # Need to be cautious of rate limits, but for manual panel trigger it's fine
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                geo_res = requests.post("http://ip-api.com/batch", json=ips_to_query, headers=headers, timeout=10)
                if geo_res.status_code == 200:
                    geo_data = geo_res.json()
                    # map IP to its geo info
                    geo_map = {item['query']: item for item in geo_data if item['status'] == 'success'}
                    
                    for ip, count in top_ips:
                        info = geo_map.get(ip, {})
                        results.append({
                            "ip": ip,
                            "count": count,
                            "country": info.get("country", "Unknown"),
                            "city": info.get("city", "Unknown"),
                            "isp": info.get("isp", "")
                        })
                else:
                    # Fallback if API fails
                    for ip, count in top_ips:
                        results.append({"ip": ip, "count": count, "country": "API Error", "city": ""})
            except Exception as e:
                for ip, count in top_ips:
                    results.append({"ip": ip, "count": count, "country": "Network Error", "city": str(e)[:20]})
        
        return {
            "total_analyzed_lines": len(target_lines),
            "top_ips": results
        }
    except Exception as e:
        return {"error": str(e)}
