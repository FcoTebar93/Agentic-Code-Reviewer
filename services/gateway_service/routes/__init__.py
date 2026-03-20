from services.gateway_service.routes.approvals import router as approvals_router
from services.gateway_service.routes.health import router as health_router
from services.gateway_service.routes.proxy import router as proxy_router

__all__ = [
    "approvals_router",
    "health_router",
    "proxy_router",
]
