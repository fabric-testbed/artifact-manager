import os

import requests

from artifactmgr.apps.apiuser.models import ApiUser

# Outcomes for lookup_fabric_person(); distinguishes a genuinely missing user from a failed call.
PERSON_FOUND = 'found'
PERSON_NOT_FOUND = 'not_found'
PERSON_LOOKUP_FAILED = 'lookup_failed'


class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        r.headers["authorization"] = "Bearer " + self.token
        return r


def query_core_api_by_cookie(query: str, cookie: str):
    """
    Issue a simple GET query against core-api using cookie auth
    """
    s = requests.Session()
    response = None
    try:
        s.cookies.set(os.getenv('VOUCH_COOKIE_NAME'), cookie)
        api_call = s.get(url=os.getenv('FABRIC_CORE_API') + query)
        response = api_call.json()
    except Exception as exc:
        print(exc)
    s.close()
    return response


def query_core_api_by_token(query: str, token: str):
    """
    Issue a simple GET query against core-api using token auth
    """
    s = requests.Session()
    response = None
    try:
        s.auth = BearerAuth(token=token)
        api_call = s.get(url=os.getenv('FABRIC_CORE_API') + query)
        response = api_call.json()
    except Exception as exc:
        print(exc)
    s.close()
    return response


def lookup_fabric_person(request, api_user: ApiUser, uuid: str) -> tuple:
    """
    Resolve a FABRIC person by uuid via the Core API using the request's credential.

    Returns (outcome, person | None) where outcome is one of:
      - PERSON_FOUND         : the person exists (person is the results[0] dict)
      - PERSON_NOT_FOUND     : no such person (HTTP 200 + size 0, or 404)
      - PERSON_LOOKUP_FAILED : the call itself failed (no response, or a non-200/404
                               status such as 401/403/5xx) -- a transient/credential
                               problem, NOT evidence that the user is missing

    Callers must not treat PERSON_LOOKUP_FAILED as "user not found": per the Core API,
    GET /people/{uuid} returns any existing person (200, size 1) regardless of their
    profile-visibility settings, so an empty/failed result means the call failed, not
    that the person does not exist.
    """
    query = '/people/{0}?as_self=false'.format(uuid)
    if api_user.access_type == ApiUser.COOKIE:
        response = query_core_api_by_cookie(
            query=query, cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None))
    else:
        response = query_core_api_by_token(
            query=query, token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', ''))
    if not isinstance(response, dict):
        return PERSON_LOOKUP_FAILED, None
    status = response.get('status')
    if status == 200:
        results = response.get('results') or []
        if response.get('size') == 1 and results:
            return PERSON_FOUND, results[0]
        return PERSON_NOT_FOUND, None
    if status == 404:
        return PERSON_NOT_FOUND, None
    return PERSON_LOOKUP_FAILED, None
