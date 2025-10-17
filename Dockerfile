FROM alpine:3.17.3

ARG REVISION

RUN adduser --disabled-password --gecos '' app
RUN apk --no-cache add python3 py-pip

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /app
COPY requirements.txt .
# install the library dependencies for this application
RUN pip3 install --no-cache-dir  -r requirements.txt && opentelemetry-bootstrap -a install && \
  [ -z "$REVISION" ] ||echo "$REVISION" > vcs.info

COPY . .
ENV FLASK_APP="controller"
ENV SERVICE_PORT=3333
USER app

EXPOSE ${SERVICE_PORT}
#
CMD [ "/app/entrypoint.sh" ]
