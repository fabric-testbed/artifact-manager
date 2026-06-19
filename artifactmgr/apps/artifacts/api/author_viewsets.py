import os
from datetime import datetime, timedelta, timezone

from rest_framework import filters, permissions, viewsets
from rest_framework.exceptions import APIException, MethodNotAllowed

from artifactmgr.apps.apiuser.models import ApiUser, TaskTimeoutTracker
from artifactmgr.apps.artifacts.api.author_serializers import AuthorSerializer
from artifactmgr.apps.artifacts.models import ArtifactAuthor
from artifactmgr.utils.core_api import PERSON_FOUND, PERSON_LOOKUP_FAILED, lookup_fabric_person
from artifactmgr.utils.fabric_auth import is_valid_uuid


class CoreApiUnavailable(APIException):
    """Raised when a required FABRIC Core API lookup fails (NOT when a user is simply absent)."""
    status_code = 503
    default_detail = 'Unable to reach the FABRIC Core API to verify an author; please retry.'
    default_code = 'core_api_unavailable'


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
        if not is_valid_uuid(author_uuid):
            return None
        author = ArtifactAuthor.objects.filter(uuid=author_uuid).first()
        arc = TaskTimeoutTracker.objects.get(name=os.getenv('ARC_NAME'))
        if author and author.updated + timedelta(seconds=int(arc.timeout_in_seconds)) > now:
            return author
        outcome, person = lookup_fabric_person(request=request, api_user=api_user, uuid=author_uuid)
        if outcome == PERSON_FOUND:
            if not author:
                author = ArtifactAuthor()
            author.affiliation = person.get('affiliation', None)
            author.email = person.get('email', None)
            author.name = person.get('name', None)
            author.updated = now
            author.uuid = person.get('uuid', None)
            author.save()
            return author
        if outcome == PERSON_LOOKUP_FAILED:
            # A failed/transient Core API call is not proof the user is missing. If we already
            # hold a (possibly stale) record, use it so a known author never blocks the save;
            # otherwise abort loudly rather than silently dropping the author.
            if author:
                return author
            raise CoreApiUnavailable(
                detail="unable to verify author '{0}' with the Core API; please retry".format(author_uuid))
        # PERSON_NOT_FOUND: genuinely no such user
        return None
    except CoreApiUnavailable:
        raise
    except Exception as exc:
        print(exc)
        return None
