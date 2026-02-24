import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordRequestForm
from auth import create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user
from datetime import timedelta
from database import engine, get_db
import models
from apscheduler.schedulers.background import BackgroundScheduler
import tasks

# Ensure static directories exist
os.makedirs("static", exist_ok=True)
for subdir in ["css", "js", "img"]:
    os.makedirs(f"static/{subdir}", exist_ok=True)

scheduler = BackgroundScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    models.Base.metadata.create_all(bind=engine)
    scheduler.add_job(tasks.collect_system_metrics, 'interval', seconds=3)
    scheduler.start()
    yield
    # Shutdown
    scheduler.shutdown()

app = FastAPI(title="Linux Server Monitor", lifespan=lifespan)

from routers import system, network, nginx, process, manager

app.include_router(system.router)
app.include_router(network.router)
app.include_router(nginx.router)
app.include_router(process.router)
app.include_router(manager.router)

from sqlalchemy.orm import Session
from pydantic import BaseModel

class PasswordChangeRequest(BaseModel):
    old_password: str
    new_username: str
    new_password: str

@app.post("/api/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    from auth import ADMIN_USERNAME_FALLBACK, verify_password, get_password_hash
    from models import ConfigStorage
    
    # Init or fetch username
    config_user = db.query(ConfigStorage).filter(ConfigStorage.key == "admin_username").first()
    if not config_user:
        config_user = ConfigStorage(key="admin_username", value=ADMIN_USERNAME_FALLBACK)
        db.add(config_user)
        db.commit()
        db.refresh(config_user)
        
    if form_data.username != config_user.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    config = db.query(ConfigStorage).filter(ConfigStorage.key == "admin_password").first()
    if not config:
        config = ConfigStorage(key="admin_password", value=get_password_hash("admin123"))
        db.add(config)
        db.commit()
        db.refresh(config)
        
    if not verify_password(form_data.password, config.value):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": config_user.value}, expires_delta=access_token_expires
    )
    is_default = verify_password("admin123", config.value) and config_user.value == "admin"
    return {"access_token": access_token, "token_type": "bearer", "is_default_password": is_default, "username": config_user.value}

@app.post("/api/user/password")
async def change_password(data: PasswordChangeRequest, db: Session = Depends(get_db), current_user: str = Depends(get_current_user)):
    from auth import verify_password, get_password_hash
    from models import ConfigStorage
    
    config = db.query(ConfigStorage).filter(ConfigStorage.key == "admin_password").first()
    if not config or not verify_password(data.old_password, config.value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原登录密码效验失败，验证无效")
        
    # Update password
    config.value = get_password_hash(data.new_password)
    
    # Update username
    config_user = db.query(ConfigStorage).filter(ConfigStorage.key == "admin_username").first()
    if not config_user:
        config_user = ConfigStorage(key="admin_username", value=data.new_username)
        db.add(config_user)
    else:
        config_user.value = data.new_username
        
    db.commit()
    return {"status": "success", "message": "账户口令修改成功，请使用新身份重新登录"}

@app.get("/api/verify_token")
async def verify_token(current_user: str = Depends(get_current_user), db: Session = Depends(get_db)):
    from auth import verify_password
    from models import ConfigStorage
    
    config = db.query(ConfigStorage).filter(ConfigStorage.key == "admin_password").first()
    config_user = db.query(ConfigStorage).filter(ConfigStorage.key == "admin_username").first()
    
    is_default = False
    if config and verify_password("admin123", config.value):
        if config_user and config_user.value == "admin":
            is_default = True
        
    return {"message": "Valid Token", "user": current_user, "is_default_password": is_default, "username": config_user.value if config_user else "admin"}

# Mount static files at the end to avoid routing conflicts
app.mount("/", StaticFiles(directory="static", html=True), name="static")
