#!/usr/bin/env sh

if [ -z ${OTEL_SERVICE_NAME} ]; then
  flask run --port=${SERVICE_PORT} --host=0.0.0.0
else
  opentelemetry-instrument flask run --port=${SERVICE_PORT} --host=0.0.0.0
fi
