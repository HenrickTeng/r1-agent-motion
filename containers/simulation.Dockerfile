FROM python:3.11-slim

WORKDIR /opt/r1-motion
COPY pyproject.toml README.md ./
COPY motion_core ./motion_core
COPY apps ./apps
COPY config ./config
RUN pip install --no-cache-dir .
ENV UNITREE_R1_MODEL_DIR=/models/r1
EXPOSE 8766
CMD ["uvicorn", "apps.simulation_service.api:app", "--host", "0.0.0.0", "--port", "8766"]
