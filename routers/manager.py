import os
import shutil
import stat
import subprocess
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from auth import get_current_user

router = APIRouter(
    prefix="/api/manager",
    tags=["manager"],
    dependencies=[Depends(get_current_user)]
)

class FileActionModel(BaseModel):
    action: str  # 'delete', 'move', 'copy', 'hardlink'
    src: str
    dest: str = ""

# ================= Docker API =================
@router.get("/docker/containers")
def list_docker_containers():
    """获取 Docker 容器列表 (检测并调用 docker cli)"""
    try:
        # Check if docker exists
        res = subprocess.run(["docker", "ps", "-a", "--format", "{{json .}}"], capture_output=True, text=True)
        if res.returncode != 0:
            return {"installed": False, "containers": [], "error": res.stderr}
            
        containers = []
        for line in res.stdout.strip().split('\n'):
            if line:
                containers.append(json.loads(line))
                
        return {"installed": True, "containers": containers}
    except FileNotFoundError:
        return {"installed": False, "containers": [], "error": "Docker not found on system."}
    except Exception as e:
        return {"installed": False, "containers": [], "error": str(e)}

# ================= File Manager API =================
@router.get("/fs/list")
def list_directory(path: str = "/"):
    """浏览目标目录"""
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="目录不存在")
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="所选路径非目录")
        
    items = []
    try:
        for entry in os.scandir(path):
            stat_info = entry.stat()
            items.append({
                "name": entry.name,
                "is_dir": entry.is_dir(),
                "size": stat_info.st_size,
                "mtime": stat_info.st_mtime,
                "permissions": stat.filemode(stat_info.st_mode),
                "absolute_path": entry.path
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="无权访问该目录")
        
    # Sort: Directories first, then alphabetically
    items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    
    # Secure parent directory parsing
    parent = os.path.dirname(os.path.normpath(path))
    if os.name == 'nt' and len(path) <= 3 and path.endswith(':\\'):
         parent = path # Root doesn't have parent
         
    return {
        "current_path": os.path.abspath(path),
        "parent_path": parent,
        "items": items
    }

@router.post("/fs/upload")
async def upload_file(path: str, file: UploadFile = File(...)):
    """向指定目录上传文件"""
    if not os.path.exists(path) or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="目标目录不存在")
        
    dest_path = os.path.join(path, file.filename)
    try:
        with open(dest_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "message": f"文件已上传至 {dest_path}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"上传失败: {str(e)}")

@router.get("/fs/download")
def download_file(path: str):
    """下载指定文件"""
    if not os.path.exists(path) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(path, filename=os.path.basename(path))

@router.post("/fs/action")
def execute_file_action(data: FileActionModel):
    """处理增删改查动作：复制、移动、删除，创建硬链接"""
    src = data.src
    dest = data.dest
    
    if not os.path.exists(src):
        raise HTTPException(status_code=404, detail="源文件/目录不存在")
        
    try:
        if data.action == "delete":
            if os.path.isdir(src):
                shutil.rmtree(src)
            else:
                os.remove(src)
            return {"status": "success", "message": f"已彻底删除 {src}"}
            
        elif data.action == "copy":
            if not dest: raise HTTPException(status_code=400, detail="未提供目标路径")
            if os.path.isdir(src):
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
            return {"status": "success", "message": f"已复制到 {dest}"}
            
        elif data.action == "move":
            if not dest: raise HTTPException(status_code=400, detail="未提供目标路径")
            shutil.move(src, dest)
            return {"status": "success", "message": f"已移动到 {dest}"}
            
        elif data.action == "hardlink":
            if not dest: raise HTTPException(status_code=400, detail="未提供目标路径")
            if os.path.isdir(src):
                raise HTTPException(status_code=400, detail="不能对目录创建物理硬链接")
            os.link(src, dest)
            return {"status": "success", "message": f"硬链接已创建: {dest}"}
            
        else:
            raise HTTPException(status_code=400, detail="未知的操作类型")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"操作失败: {str(e)}")
