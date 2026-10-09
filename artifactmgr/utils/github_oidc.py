"""Verification of GitHub Actions OIDC tokens for trusted publishing."""

import os
from functools import lru_cache

import jwt
from django.conf import settings

from artifactmgr.utils.api_logger import consoleLogger

ISSUER = 'https://token.actions.githubusercontent.com'
REQUIRED_CLAIMS = (
    'exp', 'iat', 'iss', 'aud', 'sub', 'repository_id',
    'repository_owner_id', 'repository_visibility',
)


class InvalidActionsToken(Exception):
    """The caller did not present a valid public-repository Actions identity."""


class ActionsUnavailable(Exception):
    """The signing-key service cannot currently be reached."""


@lru_cache(maxsize=1)
def _jwks_client(pid):
    """One lazy client per worker PID; no cached network state crosses prefork."""
    return jwt.PyJWKClient(ISSUER + '/.well-known/jwks', timeout=5, lifespan=3600)


def verify_actions_token(token) -> dict:
    """Validate cryptography and claims before looking up any artifact."""
    if not settings.GITHUB_OIDC_AUDIENCE or not token:
        raise InvalidActionsToken('Invalid GitHub Actions token.')
    try:
        key = _jwks_client(os.getpid()).get_signing_key_from_jwt(token).key
        claims = jwt.decode(
            token, key, algorithms=['RS256'], issuer=ISSUER,
            audience=settings.GITHUB_OIDC_AUDIENCE, leeway=30,
            options={'require': list(REQUIRED_CLAIMS)},
        )
    except (jwt.PyJWKClientConnectionError, ValueError) as exc:
        consoleLogger.exception('github_oidc: signing keys unavailable')
        raise ActionsUnavailable('GitHub signing keys are unavailable; please retry.') from exc
    except jwt.PyJWTError as exc:
        # An invalid token is an expected outcome on an unauthenticated route, not a server fault:
        # one WARNING line with PyJWT's reason (never the token) is what an operator needs.
        consoleLogger.warning('github_oidc: token rejected (%s: %s)', type(exc).__name__, exc)
        raise InvalidActionsToken('Invalid GitHub Actions token.') from exc
    if (claims['repository_visibility'] != 'public'
            or any(not isinstance(claims[name], str) or not claims[name].isascii()
                   or not claims[name].isdigit()
                   for name in ('repository_id', 'repository_owner_id'))):
        raise InvalidActionsToken('Invalid GitHub Actions token.')
    return claims
