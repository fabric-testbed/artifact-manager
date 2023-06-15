from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, viewsets
from rest_framework.exceptions import APIException, MethodNotAllowed, PermissionDenied, ValidationError

from artifactmgr.apps.artifacts.api.tag_serializers import TagSerializer
from artifactmgr.apps.artifacts.models import ArtifactTag
from artifactmgr.utils.fabric_auth import get_api_user


class TagViewSet(viewsets.ModelViewSet):
    """
    FABRIC Artifact Tags
    - list (GET) - paginated list of all tags
    - create (POST) - create a new tag
    - retrieve (GET id) - MethodNotAllowed
    - update (PUT id) - MethodNotAllowed
    - partial update (PATCH id) - MethodNotAllowed
    - destroy (DELETE id) - delete an existing tag
    """
    queryset = ArtifactTag.objects.all().order_by('tag')
    serializer_class = TagSerializer
    search_fields = ['tag']
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    permission_classes = [permissions.AllowAny]

    def list(self, request, *args, **kwargs):
        """
        FABRIC Artifact Tags
        - Used to Tag or label artifacts
        - Search by 'tag'
        - Tags may only be added or removed by FABRIC facility operators
        """
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Create FABRIC Artifact Tag
        - User must have "facility-operators" role
        """
        api_user = get_api_user(request=request)
        if api_user.can_create_tag:
            if ArtifactTag.objects.filter(tag=str(request.data.get('tag')).casefold()).first():
                raise ValidationError(detail="DuplicateEntry: tag '{0}' already exists".format(request.data.get('tag')))
            else:
                try:
                    return super().create(request, *args, **kwargs)
                except Exception as exc:
                    raise APIException(detail=exc)
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to create /meta/tags".format(api_user.uuid))

    def retrieve(self, request, *args, **kwargs):
        """
        retrieve (GET {int:pk})
        """
        raise MethodNotAllowed(method='GET', detail='MethodNotAllowed: GET /api/meta/tags/{tag}')

    def update(self, request, *args, **kwargs):
        """
        update (PUT {int:pk})
        """
        raise MethodNotAllowed(method='PUT', detail='MethodNotAllowed: PUT /api/meta/tags/{tag}')

    def partial_update(self, request, *args, **kwargs):
        """
        partial_update (PATCH {int:pk})
        """
        raise MethodNotAllowed(method='PATCH', detail='MethodNotAllowed: PATCH /api/meta/tags/{tag}')

    def destroy(self, request, *args, **kwargs):
        """
        Remove FABRIC Artifact Tag
        - User must have "facility-operators" role
        - NOTE: Does not remove Tag from previously created Artifacts that already make use of the Tag
        """
        api_user = get_api_user(request=request)
        if api_user.can_create_tag:
            try:
                return super().destroy(request, *args, **kwargs)
            except Exception as exc:
                raise APIException(detail=exc)
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to delete /meta/tags/{1}".format(api_user.uuid,
                                                                                                kwargs.get('pk')))
