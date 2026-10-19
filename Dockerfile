# Overridable so the CI smoke test can build from a base image it already fetched
# (tests/smoke/pull.sh); the default is what every deployment builds.
ARG BASE_IMAGE=python:3.13
FROM ${BASE_IMAGE}
#MAINTAINER Michael J. Stealey <mjstealey@gmail.com>
LABEL org.opencontainers.image.authors="Michael J. Stealey <mjstealey@gmail.com>"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update --yes \
  && apt-get install --yes --no-install-recommends \
  postgresql-client \
  && apt-get clean && rm -rf /var/lib/apt/lists/* \
  && mkdir /code/

# specifies nrig-service UID
RUN useradd -r -u 20049 appuser

WORKDIR /code
VOLUME ["/code"]
ENTRYPOINT ["/code/docker-entrypoint.sh"]