import os
from datetime import datetime, timedelta, timezone

from rest_framework import filters, permissions, viewsets
from rest_framework.exceptions import MethodNotAllowed

from artifactmgr.apps.artifacts.api.author_serializers import AuthorSerializer
from artifactmgr.apps.artifacts.models import ApiUser, ArtifactAuthor, TaskTimeoutTracker
from artifactmgr.utils.core_api import query_core_api_by_cookie, query_core_api_by_token
from artifactmgr.utils.fabric_auth import is_valid_uuid


class DynamicSearchFilter(filters.SearchFilter):
    def get_search_fields(self, view, request):
        if request.parser_context.get('view').action == 'list':
            return ['name', 'email', 'affiliation']
        else:
            return []


class AuthorViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    - list (GET)
    - create (POST)
    - retrieve (GET id)
    - update (PUT id)
    - partial update (PATCH id)
    - destroy (DELETE id)
    """
    serializer_class = AuthorSerializer
    filter_backends = [DynamicSearchFilter]
    permission_classes = [permissions.AllowAny]
    lookup_field = 'uuid'

    def get_queryset(self):
        return ArtifactAuthor.objects.all().order_by('name')

    def list(self, request, *args, **kwargs):
        """
        FABRIC Artifact Authors
        - Search by 'name', 'email', 'affiliation'
        """
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        create (POST)
        """
        raise MethodNotAllowed(method='POST', detail='MethodNotAllowed: POST /api/authors')

    def retrieve(self, request, *args, **kwargs):
        """
        retrieve (GET {int:pk})
        """
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        update (PUT {int:pk})
        """
        raise MethodNotAllowed(method='PUT', detail='MethodNotAllowed: PUT /api/authors/{uuid}')

    def partial_update(self, request, *args, **kwargs):
        """
        partial_update (PATCH {int:pk})
        """
        raise MethodNotAllowed(method='PATCH', detail='MethodNotAllowed: PATCH /api/authors/{uuid}')

    def destroy(self, request, *args, **kwargs):
        """
        destroy (DELETE {int:pk})
        """
        raise MethodNotAllowed(method='DELETE', detail='MethodNotAllowed: DELETE /api/authors/{uuid}')


def create_author_from_uuid(request, api_user: ApiUser, author_uuid: str) -> ArtifactAuthor | None:
    try:
        now = datetime.now(timezone.utc)
        if is_valid_uuid(author_uuid):
            author = ArtifactAuthor.objects.filter(uuid=author_uuid).first()
            arc = TaskTimeoutTracker.objects.get(name=os.getenv('ARC_NAME'))
            if author and author.updated + timedelta(seconds=int(arc.timeout_in_seconds)) > now:
                return author
            else:
                if api_user.access_type == ApiUser.COOKIE:
                    fab_user = query_core_api_by_cookie(
                        query='/people/{0}?as_self=false'.format(author_uuid),
                        cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None))
                else:
                    fab_user = query_core_api_by_token(
                        query='/people/{0}?as_self=false'.format(author_uuid),
                        token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', ''))
                if fab_user.get('size') == 1 and fab_user.get('status') == 200:
                    if not author:
                        author = ArtifactAuthor()
                    author.affiliation = fab_user.get('results')[0].get('affiliation', None)
                    author.email = fab_user.get('results')[0].get('email', None)
                    author.name = fab_user.get('results')[0].get('name', None)
                    author.updated = now
                    author.uuid = fab_user.get('results')[0].get('uuid', None)
                    author.save()
                    return author
                else:
                    return None
        else:
            return None
    except Exception as exc:
        print(exc)
        return None
