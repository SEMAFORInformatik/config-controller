#!/usr/bin/env sh

if [ -z ${OTEL_SERVICE_NAME} ]; then
  uvicorn controller:app --port ${SERVICE_PORT} --host 0.0.0.0 --log-config log_conf.yaml
else
  opentelemetry-instrument fastapi run --port ${SERVICE_PORT} controller --log-config log_conf.yaml
fi
