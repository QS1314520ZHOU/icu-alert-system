from __future__ import annotations

from fastapi import APIRouter

from app.routers.ai_modules.digital_twin import router as digital_twin_router
from app.routers.ai_modules.ops import router as ops_router
from app.routers.ai_modules.reasoning import router as reasoning_router
from app.routers.ai_modules.workspace import router as workspace_router

router = APIRouter()
router.include_router(ops_router)
router.include_router(reasoning_router)
router.include_router(digital_twin_router)
router.include_router(workspace_router)
