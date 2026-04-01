from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .database import engine
from .models import Base
from .routers import auth, runs, plans, goals, progress
import os

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI Running Coach", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers (must be registered before static file mount)
app.include_router(auth.router)
app.include_router(runs.router)
app.include_router(plans.router)
app.include_router(goals.router)
app.include_router(progress.router)

# Serve frontend static files at root
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
