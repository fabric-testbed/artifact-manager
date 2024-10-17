import os
from datetime import datetime, timezone
from uuid import uuid4

from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from artifactmgr.apps.apiuser.models import ApiUser
from artifactmgr.apps.artifacts.api.artifact_serializers import ArtifactCreateSerializer, ArtifactSerializer, \
    ArtifactUpdateSerializer
from artifactmgr.apps.artifacts.api.author_viewsets import create_author_from_uuid
from artifactmgr.apps.artifacts.api.validators import validate_artifact_create, validate_artifact_update
from artifactmgr.apps.artifacts.models import Artifact, ArtifactAuthor, ArtifactViews
from artifactmgr.utils.core_api import query_core_api_by_cookie, query_core_api_by_token
from artifactmgr.utils.fabric_auth import get_api_user


class DynamicSearchFilter(filters.SearchFilter):
    def get_search_fields(self, view, request):
        if request.parser_context.get('view').action == 'list':
            return ['title', 'project_name', 'tags__tag']
        else:
            return []


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
        api_user = get_api_user(request=self.request)
        if self.kwargs.get('author_uuid', None):
            qs1 = Artifact.objects.filter(
                authors__uuid__in=[self.kwargs.get('author_uuid')]
            ).distinct().order_by('-created')
            qs2 = Artifact.objects.filter(
                Q(visibility=Artifact.PUBLIC) |
                Q(project_uuid__in=api_user.projects) |
                Q(authors__uuid__in=[api_user.uuid])
            ).distinct().order_by('-created')
            return qs1.intersection(qs2).order_by('-modified')
        else:
            return Artifact.objects.filter(
                Q(visibility=Artifact.PUBLIC) |
                Q(project_uuid__in=api_user.projects) |
                Q(authors__uuid__contains=api_user.uuid)
            ).distinct().order_by('-modified')

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.default_serializer_class)

    def list(self, request, *args, **kwargs):
        """
        FABRIC Artifacts - list view
        - Search by 'title', 'project_name'
        """
        api_user = get_api_user(request=request)
        response_artifacts = super().list(request, *args, **kwargs)
        try:
            for i in range(len(response_artifacts.data.get('results'))):
                show_authors = response_artifacts.data.get('results')[i].get('show_authors')
                show_project = response_artifacts.data.get('results')[i].get('show_project')
                if not show_authors or not show_project:
                    artifact = Artifact.objects.get(uuid=response_artifacts.data.get('results')[i].get('uuid'))
                    if artifact:
                        if not show_authors and not artifact.is_author(api_user_uuid=api_user.uuid):
                            response_artifacts.data['results'][i]['authors'] = []
                        if not show_project and not artifact.is_author(api_user_uuid=api_user.uuid):
                            response_artifacts.data['results'][i]['project_name'] = None
                            response_artifacts.data['results'][i]['project_uuid'] = None
        except Exception as exc:
            print(exc)
        return response_artifacts

    def create(self, request, *args, **kwargs):
        """
        Create a FABRIC Artifact
        - Must be an active FABRIC user and be a member of a project
        """
        api_user = get_api_user(request=request)
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
                # TODO: check for attached version
                # return new artifact
                return Response(data=ArtifactSerializer(instance=artifact).data, status=201)
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
        api_user = get_api_user(request=request)
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
            print(exc)
        response_artifact = super().retrieve(request, *args, **kwargs)
        show_authors = response_artifact.data.get('show_authors')
        show_project = response_artifact.data.get('show_project')
        if artifact:
            if not show_authors and not artifact.is_author(api_user_uuid=api_user.uuid):
                response_artifact.data['authors'] = []
            if not show_project and not artifact.is_author(api_user_uuid=api_user.uuid):
                response_artifact.data['project_name'] = None
                response_artifact.data['project_uuid'] = None
        return response_artifact

    def update(self, request, *args, **kwargs):
        """
        FABRIC Artifacts - update
        - Must be an author of the Artifact to update it
        """
        artifact = get_object_or_404(Artifact, uuid=kwargs.get('uuid'))
        api_user = get_api_user(request=request)
        if api_user.uuid in [a.uuid for a in artifact.authors.all()]:
            is_valid, message = validate_artifact_update(request, api_user=api_user)
            if is_valid:
                now = datetime.now(timezone.utc)
                request_data = request.data
                # description_long
                if request_data.get('description_long', None):
                    artifact.description_long = request_data.get('description_long', None)
                # description_short
                if request_data.get('description_short', None):
                    artifact.description_short = request_data.get('description_short', '')
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
                        artifact.project_name = fab_project.get('results')[0].get('name', None)
                        artifact.project_uuid = project_uuid
                # show_authors
                show_authors = str(request_data.get('show_authors', None))
                if show_authors.casefold() == 'false':
                    artifact.show_authors = False
                else:
                    artifact.show_authors = True
                # show_project
                show_project = str(request_data.get('show_project', None))
                if show_project.casefold() == 'false':
                    artifact.show_project = False
                else:
                    artifact.show_project = True
                # title
                if request_data.get('title', ''):
                    artifact.title = request_data.get('title', '')
                # visibility
                if request_data.get('visibility', None):
                    artifact.visibility = request_data.get('visibility', None)
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
                    for author_uuid in authors_removed:
                        author = ArtifactAuthor.objects.filter(uuid=author_uuid).first()
                        if author:
                            artifact.authors.remove(author)
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
                for tag in tags_removed:
                    artifact.tags.remove(tag)
                # save artifact
                artifact.save()
                # return updated artifact
                return Response(data=ArtifactSerializer(instance=artifact).data, status=200)
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
        api_user = get_api_user(request=request)
        if api_user.uuid == artifact.created_by.uuid:
            artifact.delete()
            return Response(status=204)
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to delete /artifacts/{1}".format(api_user.uuid,
                                                                                                kwargs.get('uuid')))

    @action(detail=False, methods=['get'], url_path='by-author/(?P<uuid>[^/.]+)')
    def by_author(self, request, *args, **kwargs) -> HttpResponse | ValidationError:
        """
        FABRIC Artifacts - By Author
        - Retrieve artifacts by author where api_user can view them
        - get_queryset returns intersection of all artifacts by author x viewable artifacts by api_user
        """
        api_user = get_api_user(request=request)
        response_artifacts = super().list(request, *args, **kwargs)
        try:
            for i in range(len(response_artifacts.data.get('results'))):
                show_authors = response_artifacts.data.get('results')[i].get('show_authors')
                show_project = response_artifacts.data.get('results')[i].get('show_project')
                if not show_authors or not show_project:
                    artifact = Artifact.objects.get(uuid=response_artifacts.data.get('results')[i].get('uuid'))
                    if artifact:
                        if not show_authors and not artifact.is_author(api_user_uuid=api_user.uuid):
                            response_artifacts.data['results'][i]['authors'] = []
                        if not show_project and not artifact.is_author(api_user_uuid=api_user.uuid):
                            response_artifacts.data['results'][i]['project_name'] = None
                            response_artifacts.data['results'][i]['project_uuid'] = None
        except Exception as exc:
            print(exc)
        return response_artifacts
