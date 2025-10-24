FROM alpine:3.17.3

LABEL org.label-schema.name=config-controller

ARG REVISION

RUN apk add python3 py-pip

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app
COPY . .
# install the library dependencies for this application
RUN pip3 install --no-cache-dir  -r requirements.txt && opentelemetry-bootstrap -a install && \
  [ -z "$REVISION" ] ||echo "$REVISION" > vcs.info

ENV FLASK_APP="controller"
ENV SERVICE_PORT=3333
ENV LABEL_KEY="app"
ENV CONFIG_DIR="/etc/config-controller"
ENV MIN_NUM_IDLING_CONTAINERS=1

EXPOSE ${SERVICE_PORT}
#
CMD [ "/app/entrypoint.sh" ]
