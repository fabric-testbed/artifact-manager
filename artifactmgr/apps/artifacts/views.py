import json
import os
from urllib.parse import parse_qs, urlparse

from django.db import models
from django.http import QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from rest_framework import status

from artifactmgr.apps.apiuser.models import ApiUser
from artifactmgr.apps.artifacts.api.artifact_viewsets import ArtifactViewSet
from artifactmgr.apps.artifacts.api.author_viewsets import AuthorViewSet
from artifactmgr.apps.artifacts.api.validators import validate_artifact_version_create
from artifactmgr.apps.artifacts.api.version_viewsets import ArtifactVersionViewSet
from artifactmgr.apps.artifacts.forms import ArtifactForm
from artifactmgr.apps.artifacts.models import Artifact
from artifactmgr.server.settings import API_DEBUG, REST_FRAMEWORK
from artifactmgr.utils.core_api import query_core_api_by_cookie, query_core_api_by_token
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
                      'debug': API_DEBUG
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
                      'authors': authors.get('list_objects', {}),
                      'item_range': authors.get('item_range', None),
                      'message': message,
                      'next_page': authors.get('next_page', None),
                      'prev_page': authors.get('prev_page', None),
                      'search': authors.get('search', None),
                      'count': authors.get('count', None),
                      'debug': API_DEBUG
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
                      'debug': API_DEBUG
                  })


def artifact_detail(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    message = kwargs.get('message', None)

    if request.method == 'POST':
        try:
            artifact_detail_button = request.POST.get('artifact_detail_button', None)
            v_api_request = request.POST.copy()
            v_api_request.COOKIES = request.COOKIES
            v_api_request.headers = request.headers
            v_api_request.data = QueryDict('', mutable=True)
            if artifact_detail_button == 'add_version':
                v_api_request.method = 'POST'
                v_api_request.FILES = request.FILES
                v_api_request.data.update(
                    {
                        'file': request.FILES,
                        'data': {
                            'artifact': kwargs.get('uuid'),
                            'storage_type': 'fabric',
                            'storage_repo': 'renci'
                        }
                    }
                )
                is_valid, message = validate_artifact_version_create(request=v_api_request, api_user=api_user)
                if is_valid:
                    v = ArtifactVersionViewSet(request=v_api_request)
                    version = v.create(request=v_api_request)
                    if version.status_code == status.HTTP_201_CREATED:
                        version = json.loads(json.dumps(version.data))
                        return redirect('artifact_detail', uuid=kwargs.get('uuid'))
                else:
                    try:
                        request.method = 'GET'
                        artifact = ArtifactViewSet.as_view({'get': 'retrieve'})(request=request, *args, **kwargs)
                        if artifact.data and artifact.status_code == status.HTTP_200_OK:
                            artifact = json.loads(json.dumps(artifact.data))
                            is_author = api_user.uuid in [a.get('uuid') for a in artifact.get('authors', [])]
                        else:
                            message = {'status_code': artifact.status_code, 'detail': artifact.data.get('detail')}
                            is_author = False
                        if not message:
                            message = artifact.get('message', None)
                    except Exception as exc:
                        message = exc
                        artifact = {}
                        is_author = False
                    return render(request,
                                  'artifact_detail.html',
                                  {
                                      'api_user': api_user.as_dict(),
                                      'artifact': artifact,
                                      'is_author': is_author,
                                      'message': message,
                                      'debug': API_DEBUG
                                  })
            elif artifact_detail_button == "hide_version":
                v_api_request.method = 'PATCH'
                v_api_request.data.update(
                    {
                        'active': 'false'
                    }
                )
                v = ArtifactVersionViewSet(request=v_api_request)
                version = v.partial_update(request=v_api_request, uuid=request.POST.get('version_uuid', None))
                return redirect('artifact_detail', uuid=kwargs.get('uuid'))
            elif artifact_detail_button == "show_version":
                v_api_request.method = 'PATCH'
                v_api_request.data.update(
                    {
                        'active': 'true'
                    }
                )
                v = ArtifactVersionViewSet(request=v_api_request)
                version = v.partial_update(request=v_api_request, uuid=request.POST.get('version_uuid', None))
                return redirect('artifact_detail', uuid=kwargs.get('uuid'))
            elif artifact_detail_button == "delete_artifact":
                artifact_uuid = request.POST.get('artifact_uuid', None)
                v_api_request.method = 'DELETE'
                v_api_request.data.update(
                    {
                        'uuid': artifact_uuid
                    }
                )
                a = ArtifactViewSet(request=v_api_request)
                artifact = a.destroy(request=v_api_request)
                return redirect('artifact_list')
            else:
                return redirect('artifact_detail', uuid=kwargs.get('uuid'))

        except Exception as exc:
            message = exc
            print(message)
            return redirect('artifact_detail', uuid=kwargs.get('uuid'))
    # get artifact detail page when not method: POST
    try:
        artifact = ArtifactViewSet.as_view({'get': 'retrieve'})(request=request, *args, **kwargs)
        if artifact.status_code != status.HTTP_200_OK:
            return redirect('artifact_list')
        if artifact.data and artifact.status_code == status.HTTP_200_OK:
            artifact = json.loads(json.dumps(artifact.data))
            artifact_obj = Artifact.objects.get(uuid=kwargs.get('uuid'))
            is_author = artifact_obj.is_author(api_user_uuid=api_user.uuid)
        else:
            message = {'status_code': artifact.status_code, 'detail': artifact.data.get('detail')}
            is_author = False
        if not message:
            message = artifact.get('message', None)
    except Exception as exc:
        message = exc
        artifact = {}
        is_author = False
    return render(request,
                  'artifact_detail.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifact': artifact,
                      'is_author': is_author,
                      'message': message,
                      'debug': API_DEBUG
                  })


def artifact_create(request):
    api_user = get_api_user(request=request)
    message = None
    search = None
    fabric_users = []
    if request.method == "POST" and isinstance(request.POST.get('save'), str):
        form = ArtifactForm(request.POST, api_user=api_user)
        if form.is_valid():
            try:
                request.data = QueryDict('', mutable=True)
                data_dict = form.cleaned_data
                request.data.update(data_dict)
                a = ArtifactViewSet(request=request)
                artifact = a.create(request=request)
                if artifact.status_code == status.HTTP_201_CREATED:
                    artifact = json.loads(json.dumps(artifact.data))
                    return redirect('artifact_detail', uuid=artifact.get('uuid'))
                else:
                    message = artifact.data
            except Exception as exc:
                message = exc
        else:
            message = form.errors
    elif request.method == "POST" and isinstance(request.POST.get('search'), str):
        form = ArtifactForm(request.POST, api_user=api_user)
        search = request.POST.get('search')
        if len(search) < 3:
            message = 'SearchError: Search for FABRIC authors requires 3 or more characters'
        else:
            if api_user.access_type == ApiUser.COOKIE:
                fabric_users = query_core_api_by_cookie(
                    query='/people?search={0}'.format(search),
                    cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None)).get('results')
            else:
                fabric_users = query_core_api_by_token(
                    query='/people?search={0}'.format(search),
                    token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', '')).get('results')
        if not message and len(fabric_users) == 0:
            fabric_users = [{'name': 'No results found for search = "{0}"'.format(search)}]
    else:
        form = ArtifactForm(api_user=api_user)
    return render(request,
                  'artifact_create.html',
                  {
                      'api_user': api_user.as_dict(),
                      'debug': API_DEBUG,
                      'fabric_users': fabric_users,
                      'form': form,
                      'message': message,
                      'search': search
                  })


def artifact_update(request, *args, **kwargs):
    api_user = get_api_user(request=request)
    artifact_title = None
    artifact_uuid = kwargs.get('uuid')
    message = None
    search = None
    fabric_users = []
    if request.method == "POST" and isinstance(request.POST.get('save'), str):
        form = ArtifactForm(request.POST, api_user=api_user)
        if form.is_valid():
            try:
                request.data = QueryDict('', mutable=True)
                data_dict = form.cleaned_data
                request.data.update(data_dict)
                a = ArtifactViewSet(request=request)
                artifact = a.update(request=request, uuid=artifact_uuid)
                if artifact.status_code == 200:
                    return redirect('artifact_detail', uuid=artifact_uuid)
                else:
                    message = artifact.data
            except Exception as exc:
                message = exc
        else:
            message = form.errors
    elif request.method == "POST" and isinstance(request.POST.get('search'), str):
        form = ArtifactForm(request.POST, api_user=api_user)
        search = request.POST.get('search')
        if len(search) < 3:
            message = 'SearchError: Search for FABRIC authors requires 3 or more characters'
        else:
            if api_user.access_type == ApiUser.COOKIE:
                fabric_users = query_core_api_by_cookie(
                    query='/people?search={0}'.format(search),
                    cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None)).get('results')
            else:
                fabric_users = query_core_api_by_token(
                    query='/people?search={0}'.format(search),
                    token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', '')).get('results')
        if not message and len(fabric_users) == 0:
            fabric_users = [{'name': 'No results found for search = "{0}"'.format(search)}]
    else:
        artifact = get_object_or_404(Artifact, uuid=artifact_uuid)
        artifact_title = artifact.title
        form = ArtifactForm(instance=artifact, authors=[a.uuid for a in artifact.authors.all()] if artifact else [],
                            api_user=api_user)
    return render(request,
                  'artifact_update.html',
                  {
                      'api_user': api_user.as_dict(),
                      'artifact_title': artifact_title,
                      'artifact_uuid': artifact_uuid,
                      'debug': API_DEBUG,
                      'fabric_users': fabric_users,
                      'form': form,
                      'message': message,
                      'search': search,
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
        'count': count,
        'debug': API_DEBUG
    }
