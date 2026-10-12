import json
import os

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render

from artifactmgr.apps.artifacts.models import ArtifactAuthor
from artifactmgr.apps.artifacts.views import GITHUB_PUBLISH_WORKFLOW, list_object_paginator, ListObjectType
from artifactmgr.server.settings import API_DEBUG
from artifactmgr.utils.api_logger import consoleLogger
from artifactmgr.utils.fabric_auth import get_api_user

# Served by Django rather than nginx so every run mode answers /robots.txt the same way. The
# artifact listing and detail pages stay crawlable; the API, admin and authentication paths and
# the create/update forms do not.
ROBOTS_TXT = '\n'.join([
    'User-agent: *',
    'Disallow: /api/',
    'Disallow: /admin/',
    'Disallow: /auth',
    'Disallow: /login',
    'Disallow: /logout',
    'Disallow: /artifacts/create/',
    'Disallow: /*/update',
]) + '\n'


def robots_txt(request):
    return HttpResponse(ROBOTS_TXT, content_type='text/plain')


def help_page(request):
    """Usage guide. Public: nothing on it depends on who is asking beyond the navbar."""
    api_user = get_api_user(request=request)
    site_url = settings.GITHUB_OIDC_AUDIENCE or request.build_absolute_uri('/')
    # The same template the artifact page fills in, so the guide cannot drift from what authors copy.
    workflow = GITHUB_PUBLISH_WORKFLOW.replace('__AMGR_URL__', json.dumps(site_url)).replace(
        '__ARTIFACT_UUID__', json.dumps('replace-with-your-artifact-uuid'))
    return render(request, 'help.html', {
        # None only when the anonymous ApiUser row is missing; the guide must render regardless.
        'api_user': api_user.as_dict() if api_user else {},
        'actions_enabled': bool(settings.GITHUB_OIDC_AUDIENCE),
        'api_root': site_url.rstrip('/') + '/api',
        'fabric_portal': os.getenv('FABRIC_PORTAL') or 'https://portal.fabric-testbed.net',
        'import_max_mib': settings.GITHUB_IMPORT_MAX_BYTES // (1024 * 1024),
        'imports_per_day': settings.GITHUB_IMPORTS_PER_DAY,
        'workflow': workflow,
    })


def landing_page(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    message = None
    try:
        if api_user.is_authenticated:
            author = ArtifactAuthor.objects.filter(uuid=api_user.uuid).first()
            if author:
                kwargs.update({'uuid': author.uuid, 'author_uuid': author.uuid})
        artifacts = list_object_paginator(request=request, object_type=ListObjectType.AUTHOR_BY_UUID, *args, **kwargs)
        if not message:
            message = artifacts.get('message', None)
    except Http404:
        raise
    except Exception:
        consoleLogger.exception('landing_page: unable to render the landing page for user %s', api_user.uuid)
        message = 'Unable to load this page; please retry.'
        artifacts = {}
    return render(request,
                  'home.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifacts': artifacts.get('list_objects', {}),
                      'item_range': artifacts.get('item_range', None),
                      'message': message,
                      'next_page': artifacts.get('next_page', None),
                      'prev_page': artifacts.get('prev_page', None),
                      'search': artifacts.get('search', None),
                      'count': artifacts.get('count', None),
                      'debug': API_DEBUG
                  })
