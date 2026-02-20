# ---- Stage 1: Dependencies ----
FROM python:3.12-slim AS deps

WORKDIR /app

COPY services/security_service/requirements.txt ./service-requirements.txt
COPY shared/requirements.txt ./shared-requirements.txt

RUN pip install --no-cache-dir \
    -r shared-requirements.txt \
    -r service-requirements.txt

# ---- Stage 2: Runtime ----
FROM python:3.12-slim AS runtime

WORKDIR /app

COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

COPY shared/ ./shared/
COPY services/__init__.py ./services/__init__.py
COPY services/security_service/ ./services/security_service/

ENV PYTHONPATH=/app
EXPOSE 8000

CMD ["uvicorn", "services.security_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
