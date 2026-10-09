"""Artifact API, including JSON-only GitHub repository and release actions."""

import os
from datetime import datetime, timezone
from uuid import uuid4

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view, OpenApiParameter
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.parsers import JSONParser

from artifactmgr.apps.apiuser.models import ApiUser
from artifactmgr.apps.artifacts.api.context import request_api_user
from artifactmgr.apps.artifacts.api.artifact_serializers import ArtifactCreateSerializer, ArtifactSerializer, \
    ArtifactUpdateSerializer
from artifactmgr.apps.artifacts.api.author_viewsets import create_author_from_uuid
from artifactmgr.apps.artifacts.api.repo_serializers import (
    GitHubReleaseSerializer, ReleaseImportSerializer, RepoLinkRequestSerializer, RepoLinkSerializer,
)
from artifactmgr.apps.artifacts.api.version_serializers import ArtifactVersionSerializer
from artifactmgr.apps.artifacts.api.validators import validate_artifact_create, validate_artifact_update
from artifactmgr.apps.artifacts.models import Artifact, ArtifactAuthor, ArtifactViews
from artifactmgr.utils.api_logger import ARTIFACT, consoleLogger, metrics_event, usr
from artifactmgr.utils.core_api import query_core_api_by_cookie, query_core_api_by_token
from artifactmgr.utils.fabric_auth import get_api_user
from artifactmgr.utils import github_api, github_oidc, repo_link


class DynamicSearchFilter(filters.SearchFilter):
    def get_search_fields(self, view, request):
        if request.parser_context.get('view').action in ('list', 'by_author', 'by_project'):
            return ['title', 'project_name', 'tags__tag']
        else:
            return []


@extend_schema_view(list=extend_schema(
    description="FABRIC Artifacts - list view\n- Search by 'title', 'project_name'",
))
class ArtifactViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    - list (GET)
    - create (POST)
    - retrieve (GET id)
    - update (PUT id)
    - partial-update (PATCH id)
    - destroy (DELETE id)
    """
    serializer_classes = {
        'list': ArtifactSerializer,
        'create': ArtifactCreateSerializer,
        'retrieve': ArtifactSerializer,
        'update': ArtifactUpdateSerializer,
        'partial_update': ArtifactUpdateSerializer,
        'destroy': ArtifactSerializer,
    }
    default_serializer_class = ArtifactSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DynamicSearchFilter]
    lookup_field = 'uuid'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Artifact.objects.none()
        api_user = request_api_user(self.request, get_api_user)
        queryset = Artifact.objects.select_related('repo_link')
        if self.kwargs.get('author_uuid', None):
            return queryset.filter(
                authors__uuid__in=[self.kwargs.get('author_uuid')]
            ).filter(
                Q(visibility=Artifact.PUBLIC) |
                Q(project_uuid__in=api_user.projects) |
                Q(authors__uuid__in=[api_user.uuid])
            ).distinct().order_by('-modified')
        elif self.kwargs.get('filter_project_uuid', None):
            return queryset.filter(
                project_uuid=self.kwargs.get('filter_project_uuid')
            ).filter(
                Q(visibility=Artifact.PUBLIC) |
                Q(project_uuid__in=api_user.projects) |
                Q(authors__uuid__in=[api_user.uuid])
            ).distinct().order_by('-modified')
        else:
            return queryset.filter(
                Q(visibility=Artifact.PUBLIC) |
                Q(project_uuid__in=api_user.projects) |
                Q(authors__uuid__contains=api_user.uuid)
            ).distinct().order_by('-modified')

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.default_serializer_class)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, 'swagger_fake_view', False) and self.action != 'repo_publish':
            context['api_user'] = request_api_user(self.request, get_api_user)
        return context

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Create a FABRIC Artifact
        - Must be an active FABRIC user and be a member of a project
        """
        api_user = request_api_user(self.request, get_api_user)
        if api_user.can_create_artifact:
            is_valid, message = validate_artifact_create(request, api_user=api_user)
            if is_valid:
                now = datetime.now(timezone.utc)
                request_data = request.data
                artifact = Artifact()
                # created
                artifact.created = now
                # created_by
                created_by = create_author_from_uuid(request=request, api_user=api_user, author_uuid=api_user.uuid)
                if created_by:
                    artifact.created_by = created_by
                # deleted
                artifact.deleted = False
                # deleted_at
                # description_long
                artifact.description_long = request_data.get('description_long', '')
                # description_short
                artifact.description_short = request_data.get('description_short', '')
                # modified
                artifact.modified = now
                # modified_by
                if created_by:
                    artifact.modified_by = created_by
                # project_name
                # project_uuid
                project_uuid = request_data.get('project_uuid', None)
                if project_uuid:
                    # verify project exists and that api_user is member
                    if api_user.access_type == ApiUser.COOKIE:
                        fab_project = query_core_api_by_cookie(
                            query='/projects/{0}'.format(project_uuid),
                            cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None))
                    else:
                        fab_project = query_core_api_by_token(
                            query='/projects/{0}'.format(project_uuid),
                            token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', ''))
                    artifact.project_name = fab_project.get('results')[0].get('name', None)
                    artifact.project_uuid = project_uuid
                # show_authors
                if request_data.get('show_authors', None):
                    show_authors = str(request_data.get('show_authors', None))
                    if show_authors.casefold() == 'false':
                        artifact.show_authors = False
                    else:
                        artifact.show_authors = True
                # show_project
                if request_data.get('show_project', None):
                    show_project = str(request_data.get('show_project', None))
                    if show_project.casefold() == 'false':
                        artifact.show_project = False
                    else:
                        artifact.show_project = True
                # title
                artifact.title = request_data.get('title', '')
                # visibility
                artifact.visibility = request_data.get('visibility', None)
                # uuid
                artifact.uuid = str(uuid4())
                artifact.save()
                # authors
                authors = request_data.get('authors', [])
                authors.append(api_user.uuid)
                authors = list(set(authors))
                for author_uuid in authors:
                    author = create_author_from_uuid(request=request, api_user=api_user, author_uuid=author_uuid)
                    if author:
                        artifact.authors.add(author)
                # tags
                tags = request_data.get('tags', [])
                for tag in tags:
                    artifact.tags.add(tag)
                artifact.save()
                metrics_event(ARTIFACT, artifact.uuid, 'create', by=api_user.uuid)
                # TODO: check for attached version
                # return new artifact
                return Response(data=ArtifactSerializer(instance=artifact, context={'api_user': api_user}).data, status=201)
            else:
                raise ValidationError(detail={'ValidationError': message})
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to create /artifacts".format(api_user.uuid))

    def retrieve(self, request, *args, **kwargs):
        """
        FABRIC Artifacts - detailed view
        """
        # increment artifact_views
        api_user = request_api_user(self.request, get_api_user)
        try:
            artifact = get_object_or_404(Artifact, uuid=self.kwargs.get('uuid'))
            # view count can only be incremented by non-authors of the artifact
            if api_user.uuid not in [a.uuid for a in artifact.authors.all()]:
                artifact_view = ArtifactViews(viewed_by=str(api_user.uuid))
                artifact_view.save()
                artifact.artifact_views.add(artifact_view)
                artifact.save()
        except Exception as exc:
            artifact = None
            consoleLogger.exception('artifact retrieve: unable to record a view of art:%s', self.kwargs.get('uuid'))
        return super().retrieve(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """
        FABRIC Artifacts - update
        - Must be an author of the Artifact to update it
        """
        artifact = get_object_or_404(Artifact, uuid=kwargs.get('uuid'))
        api_user = request_api_user(self.request, get_api_user)
        if api_user.uuid in [a.uuid for a in artifact.authors.all()]:
            is_valid, message = validate_artifact_update(request, api_user=api_user)
            if is_valid:
                now = datetime.now(timezone.utc)
                request_data = request.data
                # description_long
                if request_data.get('description_long', None):
                    description_long_orig = artifact.description_long
                    artifact.description_long = request_data.get('description_long', None)
                    if artifact.description_long != description_long_orig:
                        metrics_event(ARTIFACT, artifact.uuid, 'modify', 'description_long',
                                      artifact.description_long, by=api_user.uuid)
                # description_short
                if request_data.get('description_short', None):
                    description_short_orig = artifact.description_short
                    artifact.description_short = request_data.get('description_short', '')
                    if artifact.description_short != description_short_orig:
                        metrics_event(ARTIFACT, artifact.uuid, 'modify', 'description_short',
                                      artifact.description_short, by=api_user.uuid)
                # modified
                artifact.modified = now
                modified_by = create_author_from_uuid(request=request, api_user=api_user, author_uuid=api_user.uuid)
                # modified_by
                if modified_by:
                    artifact.modified_by = modified_by
                # project_name
                # project_uuid
                if request_data.get('project_uuid', None):
                    project_uuid = request_data.get('project_uuid', None)
                    if project_uuid:
                        # verify project exists and that api_user is member
                        if api_user.access_type == ApiUser.COOKIE:
                            fab_project = query_core_api_by_cookie(
                                query='/projects/{0}'.format(project_uuid),
                                cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None))
                        else:
                            fab_project = query_core_api_by_token(
                                query='/projects/{0}'.format(project_uuid),
                                token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', ''))
                        project_uuid_orig = artifact.project_uuid
                        artifact.project_name = fab_project.get('results')[0].get('name', None)
                        artifact.project_uuid = project_uuid
                        if artifact.project_uuid != project_uuid_orig:
                            metrics_event(ARTIFACT, artifact.uuid, 'modify', 'project_uuid',
                                          artifact.project_uuid, by=api_user.uuid)
                # show_authors
                show_authors_orig = artifact.show_authors
                show_authors = str(request_data.get('show_authors', None))
                if show_authors.casefold() == 'false':
                    artifact.show_authors = False
                else:
                    artifact.show_authors = True
                if artifact.show_authors != show_authors_orig:
                    metrics_event(ARTIFACT, artifact.uuid, 'modify', 'show_authors', artifact.show_authors,
                                  by=api_user.uuid)
                # show_project
                show_project_orig = artifact.show_project
                show_project = str(request_data.get('show_project', None))
                if show_project.casefold() == 'false':
                    artifact.show_project = False
                else:
                    artifact.show_project = True
                if artifact.show_project != show_project_orig:
                    metrics_event(ARTIFACT, artifact.uuid, 'modify', 'show_project', artifact.show_project,
                                  by=api_user.uuid)
                # title
                if request_data.get('title', ''):
                    title_orig = artifact.title
                    artifact.title = request_data.get('title', '')
                    if artifact.title != title_orig:
                        metrics_event(ARTIFACT, artifact.uuid, 'modify', 'title', artifact.title,
                                      by=api_user.uuid)
                # visibility
                if request_data.get('visibility', None):
                    visibility_orig = artifact.visibility
                    artifact.visibility = request_data.get('visibility', None)
                    if artifact.visibility != visibility_orig:
                        metrics_event(ARTIFACT, artifact.uuid, 'modify', 'visibility', artifact.visibility,
                                      by=api_user.uuid)
                # authors
                if request_data.get('authors', None):
                    authors = request_data.get('authors', None)
                    authors = list(set(authors))
                    authors_orig = [a.uuid for a in artifact.authors.all()]
                    authors_added = list(set(authors).difference(set(authors_orig)))
                    authors_removed = list(set(authors_orig).difference(set(authors)))
                    for author_uuid in authors_added:
                        author = create_author_from_uuid(request=request, api_user=api_user, author_uuid=author_uuid)
                        if author:
                            artifact.authors.add(author)
                            metrics_event(ARTIFACT, artifact.uuid, 'modify-add', 'author', usr(author.uuid),
                                          by=api_user.uuid)
                    for author_uuid in authors_removed:
                        author = ArtifactAuthor.objects.filter(uuid=author_uuid).first()
                        if author:
                            artifact.authors.remove(author)
                            metrics_event(ARTIFACT, artifact.uuid, 'modify-remove', 'author', usr(author.uuid),
                                          by=api_user.uuid)
                # tags
                tags = request_data.get('tags', [])
                tags_orig = [t.tag for t in artifact.tags.all()]
                # check for restricted tags and add if needed
                for t in artifact.tags.all():
                    if t.restricted and not api_user.is_artifact_manager_admin and t.tag not in tags:
                        tags.append(t.tag)
                tags_added = list(set(tags).difference(set(tags_orig)))
                tags_removed = list(set(tags_orig).difference(set(tags)))
                for tag in tags_added:
                    artifact.tags.add(tag)
                    metrics_event(ARTIFACT, artifact.uuid, 'modify-add', 'tag', tag, by=api_user.uuid)
                for tag in tags_removed:
                    artifact.tags.remove(tag)
                    metrics_event(ARTIFACT, artifact.uuid, 'modify-remove', 'tag', tag, by=api_user.uuid)
                # save artifact
                artifact.save()
                # return updated artifact
                return Response(data=ArtifactSerializer(instance=artifact, context={'api_user': api_user}).data, status=200)
            else:
                raise ValidationError(detail={'ValidationError': message})
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to update /artifacts/{1}".format(api_user.uuid,
                                                                                                kwargs.get('uuid')))

    def partial_update(self, request, *args, **kwargs):
        """
        FABRIC Artifacts - update
        - Must be an author of the Artifact to update it
        """
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        FABRIC Artifacts - Remove
        - Must be the Artifact creator to remove it
        TODO: remove stored object files - fail gracefully if files do not exist
        """
        artifact_uuid = request.data.get('uuid', None)
        if not artifact_uuid:
            artifact_uuid = kwargs.get('uuid')
        artifact = get_object_or_404(Artifact, uuid=artifact_uuid)
        api_user = request_api_user(self.request, get_api_user)
        if api_user.uuid == artifact.created_by.uuid:
            artifact.delete()
            metrics_event(ARTIFACT, artifact_uuid, 'delete', by=api_user.uuid)
            return Response(status=204)
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to delete /artifacts/{1}".format(api_user.uuid,
                                                                                                kwargs.get('uuid')))

    @extend_schema(
        parameters=[
            OpenApiParameter(name='search', type=str, location=OpenApiParameter.QUERY,
                             description='Search artifacts by title, tag, or project name'),
            OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY,
                             description='Page number for paginated results'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='by-author/(?P<uuid>[^/.]+)')
    def by_author(self, request, *args, **kwargs) -> HttpResponse | ValidationError:
        """
        FABRIC Artifacts - By Author
        - Retrieve artifacts by author where api_user can view them
        - get_queryset returns intersection of all artifacts by author x viewable artifacts by api_user
        """
        author = ArtifactAuthor.objects.filter(uuid=kwargs.get('uuid')).first()
        if author:
            self.kwargs.update({'author_uuid': author.uuid})
        else:
            self.kwargs.update({'author_uuid': os.getenv('API_USER_ANON_UUID')})
        return super().list(request, *args, **kwargs)

    @extend_schema(
        parameters=[
            OpenApiParameter(name='search', type=str, location=OpenApiParameter.QUERY,
                             description='Search artifacts by title, tag, or project name'),
            OpenApiParameter(name='page', type=int, location=OpenApiParameter.QUERY,
                             description='Page number for paginated results'),
        ]
    )
    @action(detail=False, methods=['get'], url_path='by-project/(?P<uuid>[^/.]+)')
    def by_project(self, request, *args, **kwargs) -> HttpResponse | ValidationError:
        """
        FABRIC Artifacts - By Project
        - Retrieve artifacts by project_uuid where api_user can view them
        - get_queryset returns intersection of all artifacts in the project x viewable artifacts by api_user
        """
        self.kwargs.update({'filter_project_uuid': kwargs.get('uuid')})
        return super().list(request, *args, **kwargs)

    @staticmethod
    def _repo_error(exc):
        return Response({'detail': str(exc)}, status=exc.status_code)

    @extend_schema(responses=RepoLinkSerializer)
    @action(detail=True, methods=['get'], url_path='repo', parser_classes=[JSONParser])
    def repo(self, request, *args, **kwargs):
        """Show the repository to viewers permitted to see author details."""
        artifact = self.get_object()
        serializer = ArtifactSerializer(context=self.get_serializer_context())
        return Response(serializer.get_repository(artifact))

    @extend_schema(request=RepoLinkRequestSerializer, responses=RepoLinkSerializer)
    @repo.mapping.put
    def repo_put(self, request, *args, **kwargs):
        """Link or re-confirm a public repository as a current author."""
        artifact = self.get_object()
        api_user = request_api_user(self.request, get_api_user)
        serializer = RepoLinkRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            link = repo_link.link_repo(artifact, serializer.validated_data['repository'], api_user)
        except (repo_link.RepoLinkError, github_api.GitHubError) as exc:
            return self._repo_error(exc)
        return Response(RepoLinkSerializer(link).data)

    @extend_schema(request=None, responses={204: None})
    @repo.mapping.delete
    def repo_delete(self, request, *args, **kwargs):
        """Unlink without altering previously imported versions."""
        artifact = self.get_object()
        api_user = request_api_user(self.request, get_api_user)
        # Force parser validation even though DELETE does not need a body.
        request.data
        try:
            repo_link.unlink_repo(artifact, api_user)
        except repo_link.RepoLinkError as exc:
            return self._repo_error(exc)
        return Response(status=204)

    @extend_schema(responses=GitHubReleaseSerializer(many=True))
    @action(detail=True, methods=['get'], url_path='repo/releases', parser_classes=[JSONParser],
            pagination_class=None, filter_backends=[])
    def repo_releases(self, request, *args, **kwargs):
        """List up to 5 GitHub pages (500 releases), marking already imported tags."""
        artifact = self.get_object()
        api_user = request_api_user(self.request, get_api_user)
        try:
            releases = repo_link.list_releases(artifact, api_user)
        except (repo_link.RepoLinkError, github_api.GitHubError) as exc:
            return self._repo_error(exc)
        return Response(GitHubReleaseSerializer(releases, many=True).data)

    @extend_schema(request=ReleaseImportSerializer,
                   responses={200: ArtifactVersionSerializer, 201: ArtifactVersionSerializer})
    @action(detail=True, methods=['post'], url_path='repo/import', parser_classes=[JSONParser])
    def repo_import(self, request, *args, **kwargs):
        """Import a published release using the caller's FABRIC identity."""
        artifact = self.get_object()
        api_user = request_api_user(self.request, get_api_user)
        serializer = ReleaseImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            version, created = repo_link.import_release(artifact, serializer.validated_data['tag'], api_user, 'api')
        except (repo_link.RepoLinkError, github_api.GitHubError) as exc:
            return self._repo_error(exc)
        return Response(ArtifactVersionSerializer(version, context={'api_user': api_user}).data, status=201 if created else 200)

    @extend_schema(request=ReleaseImportSerializer, auth=[{'GitHubActionsOIDC': []}],
                   responses={200: ArtifactVersionSerializer, 201: ArtifactVersionSerializer},
                   description='Publish with a GitHub Actions OIDC bearer token for this site audience.')
    @action(detail=True, methods=['post'], url_path='repo/publish', parser_classes=[JSONParser])
    def repo_publish(self, request, *args, **kwargs):
        """Authenticate Actions before any artifact lookup; never invoke FABRIC auth."""
        authorization = request.headers.get('Authorization', '').split()
        token = authorization[1] if len(authorization) == 2 and authorization[0].lower() == 'bearer' else ''
        try:
            claims = github_oidc.verify_actions_token(token)
        except github_oidc.InvalidActionsToken:
            return Response({'detail': 'Invalid GitHub Actions token.'}, status=401,
                            headers={'WWW-Authenticate': 'Bearer'})
        except github_oidc.ActionsUnavailable as exc:
            return Response({'detail': str(exc)}, status=503)
        artifact = Artifact.objects.filter(uuid=kwargs.get('uuid')).first()
        try:
            link = repo_link.validate_publisher(artifact, claims)
            serializer = ReleaseImportSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            consoleLogger.info('github publish: artifact %s workflow_ref=%s run_id=%s actor=%s',
                               artifact.uuid, claims.get('workflow_ref'), claims.get('run_id'), claims.get('actor'))
            version, created = repo_link.import_release(
                artifact, serializer.validated_data['tag'], link.linked_by, 'action', claims=claims)
        except (repo_link.RepoLinkError, github_api.GitHubError) as exc:
            return self._repo_error(exc)
        return Response(ArtifactVersionSerializer(version, context={'api_user': link.linked_by}).data, status=201 if created else 200)
