FROM tiangolo/uwsgi-nginx-flask:python3.8

# install goofys
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    fuse \
    && rm -rf /var/lib/apt/lists/* \
    && curl -o /usr/local/bin/goofys -J -L -H "Accept: application/octet-stream" https://github.com/kahing/goofys/releases/download/v0.24.0/goofys \
    && curl -o /usr/local/bin/catfs -J -L -H "Accept: application/octet-stream" https://github.com/kahing/catfs/releases/download/v0.8.0/catfs \
    && chmod +x /usr/local/bin/goofys \
    && chmod +x /usr/local/bin/catfs \
    && apt-get purge -y --auto-remove \
    curl

COPY ./app /app

RUN pip install -r /app/requirements.txt
