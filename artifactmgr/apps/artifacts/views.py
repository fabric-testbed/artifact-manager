import json
import os
from urllib.parse import parse_qs, urlparse
from rest_framework import status
from django.db import models
from django.http import QueryDict
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from artifactmgr.apps.artifacts.api.artifact_viewsets import ArtifactViewSet
from artifactmgr.apps.artifacts.api.version_viewsets import ArtifactVersionViewSet
from artifactmgr.apps.artifacts.api.author_viewsets import AuthorViewSet
from artifactmgr.server.settings import REST_FRAMEWORK
from artifactmgr.utils.fabric_auth import get_api_user


class ListObjectType(models.TextChoices):
    ARTIFACTS = 'artifacts', _('Artifacts')
    AUTHORS = 'authors', _('Authors')
    AUTHOR_BY_UUID = 'author_by_uuid', _('Author by UUID')


def artifact_list(request):
    api_user = get_api_user(request=request)
    try:
        artifacts = list_object_paginator(request=request, object_type=ListObjectType.ARTIFACTS)
        message = artifacts.get('message', None)
    except Exception as exc:
        message = exc
        artifacts = {}
    return render(request,
                  'artifact_list.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifacts': artifacts.get('list_objects', {}),
                      'item_range': artifacts.get('item_range', None),
                      'message': message,
                      'next_page': artifacts.get('next_page', None),
                      'prev_page': artifacts.get('prev_page', None),
                      'search': artifacts.get('search', None),
                      'count': artifacts.get('count', None),
                      'debug': os.getenv('API_DEBUG')
                  })


def author_list(request):
    api_user = get_api_user(request=request)
    try:
        authors = list_object_paginator(request=request, object_type=ListObjectType.AUTHORS)
        message = authors.get('message', None)
    except Exception as exc:
        message = exc
        authors = {}
    return render(request,
                  'author_list.html',
                  {
                      'api_user': api_user.as_dict(),
                      'people': authors.get('list_objects', {}),
                      'item_range': authors.get('item_range', None),
                      'message': message,
                      'next_page': authors.get('next_page', None),
                      'prev_page': authors.get('prev_page', None),
                      'search': authors.get('search', None),
                      'count': authors.get('count', None),
                      'debug': os.getenv('API_DEBUG')
                  })


def author_detail(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    message = None
    try:
        author = AuthorViewSet.as_view({'get': 'retrieve'})(request=request, *args, **kwargs)
        if author.data and author.status_code == status.HTTP_200_OK:
            author = json.loads(json.dumps(author.data))
            kwargs.update({'author_uuid': kwargs.get('uuid')})
        else:
            message = {'status_code': author.status_code, 'detail': author.data.get('detail')}
            author = {}
            kwargs.update({'author_uuid': os.getenv('API_USER_ANON_UUID')})
        artifacts = list_object_paginator(request=request, object_type=ListObjectType.AUTHOR_BY_UUID, *args, **kwargs)
        if not message:
            message = artifacts.get('message', None)
    except Exception as exc:
        message = exc
        author = {}
        artifacts = {}
    return render(request,
                  'author_detail.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifacts': artifacts.get('list_objects', {}),
                      'author': author,
                      'item_range': artifacts.get('item_range', None),
                      'message': message,
                      'next_page': artifacts.get('next_page', None),
                      'prev_page': artifacts.get('prev_page', None),
                      'search': artifacts.get('search', None),
                      'count': artifacts.get('count', None),
                      'debug': os.getenv('API_DEBUG')
                  })


def artifact_detail(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    message = None
    try:
        # print(request.GET.get('urn'))
        # if request.GET.get('urn'):
        #     ArtifactVersionViewSet.download(request=request, *args, **kwargs)
        artifact = ArtifactViewSet.as_view({'get': 'retrieve'})(request=request, *args, **kwargs)
        if artifact.data and artifact.status_code == status.HTTP_200_OK:
            artifact = json.loads(json.dumps(artifact.data))
        else:
            message = {'status_code': artifact.status_code, 'detail': artifact.data.get('detail')}
        if not message:
            message = artifact.get('message', None)
    except Exception as exc:
        message = exc
        artifact = {}
    return render(request,
                  'artifact_detail.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifact': artifact,
                      'message': message,
                      'debug': os.getenv('API_DEBUG')
                  })


def artifact_create(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    message = None
    try:
        print(request.GET.get('urn'))
        artifact = ArtifactViewSet.as_view({'get': 'retrieve'})(request=request, *args, **kwargs)
        if artifact.data and artifact.status_code == status.HTTP_200_OK:
            artifact = json.loads(json.dumps(artifact.data))
        else:
            message = {'status_code': artifact.status_code, 'detail': artifact.data.get('detail')}
        if not message:
            message = artifact.get('message', None)
    except Exception as exc:
        message = exc
        artifact = {}
    return render(request,
                  'artifact_detail.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifact': artifact,
                      'message': message,
                      'debug': os.getenv('API_DEBUG')
                  })


def list_object_paginator(request, object_type: str, *args, **kwargs):
    message = None
    try:
        # check for query parameters
        current_page = 1
        search_term = None
        data_dict = {}
        if request.GET.get('search'):
            data_dict['search'] = request.GET.get('search')
            search_term = request.GET.get('search')
        if request.GET.get('page'):
            data_dict['page'] = request.GET.get('page')
            current_page = int(request.GET.get('page'))
        request.query_params = QueryDict('', mutable=True)
        request.query_params.update(data_dict)
        if object_type == ListObjectType.ARTIFACTS:
            list_objects = ArtifactViewSet.as_view({'get': 'list'})(request=request)
        elif object_type == ListObjectType.AUTHORS:
            list_objects = AuthorViewSet.as_view({'get': 'list'})(request=request)
        elif object_type == ListObjectType.AUTHOR_BY_UUID:
            list_objects = ArtifactViewSet.as_view({'get': 'by_author'})(request=request, *args, **kwargs)
        else:
            list_objects = {}
        # get prev, next and item range
        next_page = None
        prev_page = None
        count = 0
        min_range = 0
        max_range = 0
        if list_objects.data:
            list_objects = json.loads(json.dumps(list_objects.data))
            prev_url = list_objects.get('previous', None)
            if prev_url:
                prev_dict = parse_qs(urlparse(prev_url).query)
                try:
                    prev_page = prev_dict['page'][0]
                except Exception as exc:
                    print(exc)
                    prev_page = 1
            next_url = list_objects.get('next', None)
            if next_url:
                next_dict = parse_qs(urlparse(next_url).query)
                try:
                    next_page = next_dict['page'][0]
                except Exception as exc:
                    print(exc)
                    next_page = 1
            count = int(list_objects.get('count'))
            min_range = int(current_page - 1) * int(REST_FRAMEWORK['PAGE_SIZE']) + 1
            max_range = int(current_page - 1) * int(REST_FRAMEWORK['PAGE_SIZE']) + int(REST_FRAMEWORK['PAGE_SIZE'])
            if max_range > count:
                max_range = count
        else:
            list_objects = {}
        item_range = '{0} - {1}'.format(str(min_range), str(max_range))
    except Exception as exc:
        message = exc
        list_objects = {}
        item_range = None
        next_page = None
        prev_page = None
        search_term = None
        count = 0
    return {
        'list_objects': list_objects,
        'item_range': item_range,
        'message': message,
        'next_page': next_page,
        'prev_page': prev_page,
        'search': search_term,
        'count': count
    }
