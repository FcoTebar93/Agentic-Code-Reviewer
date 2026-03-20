import os

SERVICE_NAME = "gateway_service"
PLAN_IDEM_TTL_SECONDS = int(os.environ.get("GATEWAY_PLAN_IDEM_TTL_SECONDS", "45"))
