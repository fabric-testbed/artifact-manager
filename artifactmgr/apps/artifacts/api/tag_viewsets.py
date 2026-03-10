from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, viewsets
from rest_framework.exceptions import APIException, MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.response import Response

from artifactmgr.apps.artifacts.api.tag_serializers import TagSerializer, TagUpdateSerializer
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
    serializer_classes = {
        'list': TagSerializer,
        'create': TagSerializer,
        'retrieve': TagSerializer,
        'update': TagUpdateSerializer,
        'partial_update': TagUpdateSerializer,
        'destroy': TagSerializer,
    }
    default_serializer_class = TagSerializer
    search_fields = ['tag']
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    permission_classes = [permissions.AllowAny]
    lookup_field = 'tag'

    def get_queryset(self):
        api_user = get_api_user(request=self.request)
        if api_user.is_artifact_manager_admin:
            return ArtifactTag.objects.all().order_by('tag')
        else:
            return ArtifactTag.objects.filter(
                restricted=False
            ).order_by('tag')

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.default_serializer_class)

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
        if api_user.is_artifact_manager_admin:
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
        artifact_tag = get_object_or_404(ArtifactTag, tag=str(kwargs.get('tag')).casefold())
        api_user = get_api_user(request=request)
        if api_user and api_user.is_artifact_manager_admin:
            try:
                artifact_tag.restricted = True if str(request.data.get('restricted')).casefold() == 'true' else False
                artifact_tag.save()
                # return updated tag
                return Response(data=TagSerializer(instance=artifact_tag).data, status=200)
            except Exception as exc:
                raise APIException(detail=exc)
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to update /meta/tags".format(api_user.uuid))

    def partial_update(self, request, *args, **kwargs):
        """
        partial_update (PATCH {int:pk})
        """
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        Remove FABRIC Artifact Tag
        - User must have "artifact-manager-admins" role
        - NOTE: Does not remove Tag from previously created Artifacts that already make use of the Tag
        """
        api_user = get_api_user(request=request)
        if api_user.is_artifact_manager_admin:
            try:
                return super().destroy(request, *args, **kwargs)
            except Exception as exc:
                raise APIException(detail=exc)
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to delete /meta/tags/{1}".format(api_user.uuid,
                                                                                                kwargs.get('pk')))
