from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .routers import auth, runs, plans, goals, progress, onboarding, gamification, integrations, profile
import os

app = FastAPI(title="AI Running Coach", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(runs.router)
app.include_router(plans.router)
app.include_router(goals.router)
app.include_router(progress.router)
app.include_router(onboarding.router)
app.include_router(gamification.router)
app.include_router(integrations.router)
app.include_router(profile.router)

# Serve frontend static files at root
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
