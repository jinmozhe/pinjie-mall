from fastapi import APIRouter

from app.api.commerce_router import router as commerce_router
from app.domains.admin.auth_router import router as admin_auth_router
from app.domains.admin.management_router import router as admin_management_router
from app.domains.assets.router import router as assets_router
from app.domains.auth.router import router as auth_router
from app.domains.settings.router import admin_router as admin_settings_router
from app.domains.settings.router import public_router as public_settings_router
from app.domains.system.router import router as system_router
from app.domains.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(commerce_router)
api_router.include_router(auth_router)
api_router.include_router(assets_router)
api_router.include_router(users_router)
api_router.include_router(admin_auth_router)
api_router.include_router(admin_management_router)
api_router.include_router(admin_settings_router)
api_router.include_router(public_settings_router)
api_router.include_router(system_router)
