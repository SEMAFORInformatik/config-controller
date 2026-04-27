#!/usr/bin/env sh

if [ -z ${OTEL_SERVICE_NAME} ]; then
  uvicorn controller:app --port ${SERVICE_PORT} --host 0.0.0.0 --log-config log_conf.yaml
else
  opentelemetry-instrument uvicorn controller:app --port ${SERVICE_PORT} --host 0.0.0.0 --log-config log_conf.yaml
fi
