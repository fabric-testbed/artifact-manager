# FABRIC Artifact Manager

**WORK IN PROGRESS**

Is a platform for sharing and reproducing FABRIC research artifacts. It provides a REST API for use by various clients.

**DISCLAIMER: The code herein may not be up to date nor compliant with the most recent package and/or security notices. The frequency at which this code is reviewed and updated is based solely on the lifecycle of the project for which it was written to support, and is not actively maintained outside of that scope. Use at your own risk.**

## Table of Contents

- [Configuration](#config)
- [Deploy](#deploy)
- [Usage](#usage)
- [Backup and Restore](#backup-restore)
- [References](#references)


## <a name="config"></a>Configuration

```
cp env.template .env
cp vouch/config.template vouch/config
cp compose/docker-compose.yml.prod-ssl docker-compose.yml
vim nginx/default.conf
```

### `.env`

```
# docker-compose environment file
#
# When you set the same environment variable in multiple files,
# here’s the priority used by Compose to choose which value to use:
#
#  1. Compose file
#  2. Shell environment variables
#  3. Environment file
#  4. Dockerfile
#  5. Variable is not defined

### Defaults
export MIN_DESCRIPTION_LENGTH=5
export MAX_DESCRIPTION_LONG_LENGTH=5000
export MAX_DESCRIPTION_SHORT_LENGTH=255

### Artifact Manager
export API_DEBUG=true
export CAN_CREATE_ARTIFACT_ROLE='Jupyterhub'
export CAN_CREATE_TAGS_ROLE='facility-operators'
export API_USER_REFRESH_CHECK_MINUTES=5
export AUTHOR_REFRESH_CHECK_DAYS=1
export API_USER_ANON_UUID='00000000-0000-0000-0000-000000000000'
export API_USER_ANON_NAME='AnonymousUser'
export FABRIC_ARTIFACT_STORAGE_DIR=./artifact_storage
export FABRIC_ARTIFACT_STORAGE_REPO='renci'

### Token Auth
export PUBLIC_SIGNING_KEY='-----BEGIN PUBLIC KEY-----
PUBLIC_SIGNING_KEY
CONTENTS
HERE
-----END PUBLIC KEY-----'

### FABRIC
export FABRIC_CORE_API=https://COREAPI
export FABRIC_CREDENTIAL_MANAGER=https://CREDENTIALMANAGER

### Vouch Proxy
export VOUCH_COOKIE_NAME=VOUCH_COOKIE_NAME
export VOUCH_JWT_SECRET="VOUCH_JWT_SECRET"

### Django settings - default values should not be used in production
export PYTHONPATH=./:./venv:./.venv
export DJANGO_ALLOWED_HOSTS='127.0.0.1'
export DJANGO_SECRET_KEY='django-insecure-=lnekk7th8j+qokv%%05cg%x!&%crul1ka579j04mq&s6(hl3h'
export DJANGO_DEBUG=false
export DJANGO_LOG_LEVEL='DEBUG'
export DJANGO_SESSION_COOKIE_AGE='14400'
export DJANGO_TIME_ZONE='America/New_York'

# PostgreSQL database - default values should not be used in production
export HOST_DB_DATA=./db_data
export PGDATA=/var/lib/postgresql/data
export POSTGRES_HOST=127.0.0.1
export POSTGRES_DB=postgres
export POSTGRES_PASSWORD=default123!
export POSTGRES_PORT=5432
export POSTGRES_USER=postgres

### Nginx configuration
export NGINX_DEFAULT_CONF=./nginx/default.conf
export NGINX_NGINX_CONF=./nginx/nginx.conf
export NGINX_SSL_CERTS_DIR=./ssl

### uWSGI services in Django
export UWSGI_GID=1000
export UWSGI_UID=1000
```

### `vouch/config`

```
# vouch config
# bare minimum to get vouch running with OpenID Connect (such as okta)

vouch:
    logLevel: debug
    # domains:
    # valid domains that the jwt cookies can be set into
    # the callback_urls will be to these domains
    # domains:
    # - yourdomain.com
    # - yourotherdomain.com

    # - OR -
    # instead of setting specific domains you may prefer to allow all users...
    # set allowAllUsers: true to use Vouch Proxy to just accept anyone who can authenticate at the configured provider
    # and set vouch.cookie.domain to the domain you wish to protect
    allowAllUsers: true

    # Setting publicAccess: true will accept all requests, even without a valid jwt/cookie.  - VOUCH_PUBLICACCESS
    # If the user is logged in, the cookie will be validated and the user header will be set.
    # You will need to direct people to the Vouch Proxy login page from your application.
    publicAccess: true

    # in order to prevent redirection attacks all redirected URLs to /logout must be specified
    # the URL must still be passed to Vouch Proxy as https://vouch.yourdomain.com/logout?url=${ONE OF THE URLS BELOW}
    post_logout_redirect_uris:
        # API UI endpoint
        - https://127.0.0.1:8443/api/schema/swagger-ui/#/

    jwt:
        # secret - VOUCH_JWT_SECRET
        # a random string used to cryptographically sign the jwt
        # Vouch Proxy complains if the string is less than 44 characters (256 bits as 32 base64 bytes)
        # if the secret is not set here then Vouch Proxy will..
        # - look for the secret in `./config/secret`
        # - if `./config/secret` doesn't exist then randomly generate a secret and store it there
        # in order to run multiple instances of vouch on multiple servers (perhaps purely for validating the jwt),
        # you'll want them all to have the same secret
        secret: kmDDgMLGThapDV1QnhWPJd0oARzjLa5Zy3bQ8WfOIYk=

    cookie:
        # allow the jwt/cookie to be set into http://yourdomain.com (defaults to true, requiring https://yourdomain.com)
        secure: false
        # vouch.cookie.domain must be set when enabling allowAllUsers
        domain: 127.0.0.1
        name: fabric-service

    headers:
        jwt: X-Vouch-Token                # VOUCH_HEADERS_JWT
        querystring: access_token         # VOUCH_HEADERS_QUERYSTRING
        redirect: X-Vouch-Requested-URI   # VOUCH_HEADERS_REDIRECT
        claims:
            - aud
            - email
            - family_name
            - given_name
            - iss
            - name
            - oidc
            - sub
            - token_id
        idtoken: X-Vouch-IdP-IdToken
        accesstoken: X-Vouch-IdP-AccessToken
        # refresh token added to OIDC RP Client response by request to CILogon
        refreshtoken: X-Vouch-IdP-RefreshToken

oauth:
    # Generic OpenID Connect
    # including okta
    provider: oidc
    client_id: CILOGON_CLIENT_ID
    client_secret: CILOGON_CLIENT_SECRET
    auth_url: https://cilogon.org/authorize
    token_url: https://cilogon.org/oauth2/token
    user_info_url: https://cilogon.org/oauth2/userinfo
    scopes:
        - openid
        - email
        - profile
    callback_url: https://127.0.0.1:8443/auth
```

### `docker-compose.yml`

```
# compose/docker-compose.yml.prod-ssl
# - nginx port 8080, 8443 exposed to host (http, https) - self signed certs by default

version: '3.9'
services:

  django:
    # default port 8000
    build:
      context: ./
      dockerfile: Dockerfile
    container_name: amgr-django
    networks:
      - amgr-network
#    ports:
#      - "8000:8000"
    depends_on:
      - database
    volumes:
      - ./:/code
#      - ./static:/code/static
#      - ./media:/code/media
    environment:
      - UWSGI_UID=${UWSGI_UID}
      - UWSGI_GID=${UWSGI_GID}
      - LOAD_FIXTURES=${LOAD_FIXTURES:-0}
      - MAKE_MIGRATIONS=${MAKE_MIGRATIONS:-0}
    restart: unless-stopped

  database:
    # default port 5432
    image: postgres:15
    container_name: amgr-database
    networks:
      - amgr-network
#    ports:
#      - "5432:5432"
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      PGDATA: ${PGDATA}
#    volumes:
#      - ${HOST_DB_DATA}:/var/lib/postgresql/data
    restart: unless-stopped

  nginx:
    # default port 8080, 8443
    image: nginx:1
    container_name: amgr-nginx
    networks:
      - amgr-network
    ports:
      - "8080:80"
      - "8443:443"
    volumes:
      - .:/code
      - ${NGINX_DEFAULT_CONF}:/etc/nginx/conf.d/default.conf
      - ${NGINX_NGINX_CONF}:/etc/nginx/nginx.conf
      - ${NGINX_SSL_CERTS_DIR}:/etc/ssl:ro
    restart: unless-stopped

  vouch-proxy:
    # default port 9090
    container_name: amgr-vouch-proxy
    image: fabrictestbed/vouch-proxy:0.27.1
    networks:
      - amgr-network
#    ports:
#      - "127.0.0.1:9090:9090"
    volumes:
      - ./vouch:/config
    restart: unless-stopped

networks:
  amgr-network:
    name: amgr-network
```

### `nginx/default.conf`

```
upstream django {
    # use for local-ssl deployment
    server host.docker.internal:8000; # TCP socket
    # use for docker deployment
    #server amgr-django:8000;
}

server {
    listen 80;
    return 301 https://$host:8443$request_uri;
}

server {
    listen   443 ssl default_server;
    # the domain name it will serve for
    server_name $host:8443; # substitute your machine's IP address or FQDN and port

    # Enable support for TLS 1.2 and/or 1.3
    ssl_protocols  TLSv1.2 TLSv1.3;

    # If they come here using HTTP, bounce them to the correct scheme
    error_page 497 https://$server_name$request_uri;
    # Or if you're on the default port 443, then this should work too
    # error_page 497 https://;

    # Let's Encrypt format (ref: )
    ssl_certificate           /etc/ssl/fullchain.pem;
    ssl_certificate_key       /etc/ssl/privkey.pem;
    ssl_trusted_certificate   /etc/ssl/chain.pem;

    charset     utf-8;

    # set max header size
    large_client_header_buffers 4 32k;

    # max upload size
    client_max_body_size 75M;   # adjust to taste

    # Cache configuration
    open_file_cache max=1000 inactive=20s;
    open_file_cache_valid 30s;
    open_file_cache_min_uses 5;
    open_file_cache_errors off;

    location = /validate {
        # forward the /validate request to Vouch Proxy
        proxy_pass http://vouch-proxy:9090/validate;

        # be sure to pass the original host header
        proxy_set_header Host $http_host;

        # Vouch Proxy only acts on the request headers
        proxy_pass_request_body off;
        proxy_set_header Content-Length "";

        ### AUTH REQUEST SET ###
        # optionally add X-Vouch-User as returned by Vouch Proxy along with the request
        auth_request_set $auth_resp_x_vouch_user $upstream_http_x_vouch_user;

        # optinally add X-Vouch-IdP-IdToken, X-Vouch-IdP-AccessToken or X-Vouch-IdP-RefreshToken
        auth_request_set $auth_resp_x_vouch_idp_idtoken $upstream_http_x_vouch_idp_idtoken;
        #auth_request_set $auth_resp_x_vouch_idp_accesstoken $upstream_http_x_vouch_idp_accesstoken;
        #auth_request_set $auth_resp_x_vouch_idp_refreshtoken $upstream_http_x_vouch_idp_refreshtoken;

        # these return values are used by the @error401 call
        auth_request_set $auth_resp_jwt $upstream_http_x_vouch_jwt;
        auth_request_set $auth_resp_err $upstream_http_x_vouch_err;
        auth_request_set $auth_resp_failcount $upstream_http_x_vouch_failcount;
    }

    # if validate returns `401 not authorized` then forward the request to the error401block
    error_page 401 = @error401;

    location @error401 {
        proxy_set_header Host $http_host;
        # redirect to Vouch Proxy for login
        return 302 http://$host:9090/login?url=$scheme://$http_host$request_uri&vouch-failcount=$auth_resp_failcount&X-Vouch-Token=$auth_resp_jwt&error=$auth_resp_err;
        # you usually *want* to redirect to Vouch running behind the same Nginx config proteced by https
        # but to get started you can just forward the end user to the port that vouch is running on
    }

    location /auth {
        # redirect to Vouch Proxy for authentication with OIDC client
        # Callback URL (relative to host) must be defined in both OIDC client and vouch/config
        proxy_pass http://vouch-proxy:9090/auth;
    }

    location /login {
        # these return values are used by the @error401 call
        auth_request_set $auth_resp_jwt $upstream_http_x_vouch_jwt;
        auth_request_set $auth_resp_err $upstream_http_x_vouch_err;
        auth_request_set $auth_resp_failcount $upstream_http_x_vouch_failcount;

        # redirect to Vouch Proxy for login
        proxy_pass http://vouch-proxy:9090/login?url=$scheme://$http_host/api/swagger;
    }

    location /logout {
        # redirect to Vouch Proxy for logout
        proxy_pass http://vouch-proxy:9090/logout?url=$scheme://$http_host/api/swagger;
    }

    # Django media
    location /media  {
        alias /code/media;  # your Django project's media files - amend as required
    }

    location /static {
        alias /code/static; # your Django project's static files - amend as required
    }

    # Finally, send all non-media requests to the Django server.
    location / {

        # send all requests to the `/validate` endpoint for authorization
        auth_request /validate;
        proxy_set_header X-Vouch-User $auth_resp_x_vouch_user;

        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header Host $http_host;
        proxy_redirect off;

        proxy_buffers 8 24k;
        proxy_buffer_size 2k;
        uwsgi_pass  django;
        include     /code/uwsgi_params; # the uwsgi_params file
    }
}
```

## <a name="deploy"></a>Deploy

```
UWSGI_UID=$(id -u) UWSGI_GID=$(id -g) ./run_server.sh --run-mode local-ssl --load-fixtures --make-migrations
```

## <a name="usage"></a>Usage

## <a name="backup-restore"></a>Backup and Restore

At present only the `artifacts` app needs to be backup up or restored. This may change as the project evolves.

### Backup

Run the `dumpdata.sh` script from the top level of the repository to generate JSON files for each Django app.

Local

```console
source .env
source venv/bin/activate
./dumpdata.sh
```

Docker

```console
docker exec amgr-django /bin/bash -c "source .env; source .venv/bin/activate; ./dumpdata.sh"
docker cp amgr-django:/code/dumpdata/artifacts.json dumpdata/artifacts.json
```

### Restore

Local

```console
cp dumpdata/artifacts.json artifactmgr/apps/artifacts/fixtures/
# first run, make migrations, load fixtures
UWSGI_UID=$(id -u) UWSGI_GID=$(id -g) ./run_server.sh --run-mode local-ssl --load-fixtures --make-migrations
# subsequent runs, no need to load fixures
UWSGI_UID=$(id -u) UWSGI_GID=$(id -g) ./run_server.sh --run-mode local-ssl --make-migrations
```

Docker

```console
cp dumpdata/artifacts.json artifactmgr/apps/artifacts/fixtures/
docker compose build
MAKE_MIGRATIONS=1 LOAD_FIXTURES=1 docker compose up -d

```


## <a name="references"></a>References
