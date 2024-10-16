FROM python:3.12
#MAINTAINER Michael J. Stealey <mjstealey@gmail.com>
LABEL org.opencontainers.image.authors="Michael J. Stealey <mjstealey@gmail.com>"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update --yes \
    && apt-get install --yes --no-install-recommends \
    postgresql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/* \
    && pip install virtualenv \
    && mkdir /code/ \
    && useradd -r -u 20049 appuser

WORKDIR /code
VOLUME ["/code"]
ENTRYPOINT ["/code/docker-entrypoint.sh"]