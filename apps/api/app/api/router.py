from fastapi import APIRouter

from app.modules.organizations.router import router as organizations_router
from app.modules.products.router import router as products_router
from app.modules.warehouses.router import router as warehouses_router

api_router = APIRouter(
    prefix="/api/v1",
)

api_router.include_router(organizations_router)
api_router.include_router(products_router)
api_router.include_router(warehouses_router)
