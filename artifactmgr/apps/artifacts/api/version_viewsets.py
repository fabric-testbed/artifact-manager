from django.db.models import Q
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from artifactmgr.apps.artifacts.api.validators import validate_artifact_version_create, validate_contents_download
from artifactmgr.apps.artifacts.api.version_serializers import ArtifactContentsUploadSerializer, \
    ArtifactVersionSerializer
from artifactmgr.apps.artifacts.models import Artifact, ArtifactVersion
from artifactmgr.utils.artifact_version_storage import create_fabric_artifact_contents, download_contents_by_urn
from artifactmgr.utils.fabric_auth import get_api_user


class ArtifactVersionViewSet(viewsets.ModelViewSet, viewsets.ViewSet):
    """
    API endpoint that allows users to be viewed or edited.
    - list (GET)
    - create (POST)
    - retrieve (GET id)
    - update (PUT id)
    - partial update (PATCH id)
    - destroy (DELETE id)
    """
    # queryset = ArtifactVersion.objects.all().order_by('-created')
    parser_classes = [FormParser, MultiPartParser]
    serializer_classes = {
        'list': ArtifactVersionSerializer,
        'create': ArtifactContentsUploadSerializer,
        'retrieve': ArtifactVersionSerializer,
        'update': ArtifactVersionSerializer,
        'partial-update': ArtifactVersionSerializer,
        'destroy': ArtifactVersionSerializer,
    }
    default_serializer_class = ArtifactVersionSerializer
    search_fields = ['storage_repo', 'storage_type']
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    permission_classes = [permissions.AllowAny]
    lookup_field = 'uuid'

    def get_queryset(self):
        api_user = get_api_user(request=self.request)
        return ArtifactVersion.objects.filter(
            Q(artifact__visibility=Artifact.PUBLIC) |
            Q(artifact__project_uuid__in=api_user.projects) |
            Q(artifact__authors__uuid__contains=api_user.uuid)
        ).distinct().order_by('-created')

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.default_serializer_class)

    def list(self, request, *args, **kwargs):
        """
        FABRIC Artifact Contents - list view
        - Search by 'storage_repo', 'storage_type'
        """
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        """
        Create FABRIC Artifact Contents
        - Must be an active FABRIC user and be a member of a project
        - Contents must be associated to an existing Artifact
        - Once created the Contents cannot be altered
        """
        api_user = get_api_user(request=request)
        artifact = Artifact.objects.filter(uuid=request.data['data'].get('artifact', None)).first()
        # ensure artifact exists and that api_user is an author of the artifact
        if artifact and api_user.uuid in [a.uuid for a in artifact.authors.all()]:
            is_valid, message = validate_artifact_version_create(request, api_user=api_user)
            if is_valid:
                artifact_version = create_fabric_artifact_contents(request=request, api_user=api_user)

                return Response(data=ArtifactVersionSerializer(instance=artifact_version).data, status=201)
            else:
                raise ValidationError(detail={'ValidationError': message})
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to create /contents or artifact does not exist".format(
                    api_user.uuid))

    def retrieve(self, request, *args, **kwargs):
        """
        retrieve (GET {int:pk})
        """
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        update (PUT {int:pk})
        """
        raise MethodNotAllowed(method='PUT', detail='MethodNotAllowed: PUT /api/contents/{uuid}')

    def partial_update(self, request, *args, **kwargs):
        """
        partial_update (PATCH {int:pk})
        """
        raise MethodNotAllowed(method='PATCH', detail='MethodNotAllowed: PATCH /api/contents/{uuid}')

    def destroy(self, request, *args, **kwargs):
        """
        destroy (DELETE {int:pk})
        """
        raise MethodNotAllowed(method='DELETE', detail='MethodNotAllowed: DELETE /api/contents/{uuid}')

    @action(detail=False, methods=['get'], url_path='download/(?P<urn>[^/.]+)')
    def download(self, request, *args, **kwargs) -> HttpResponse | ValidationError:
        """
        Download FABRIC Artifact Contents by URN
        - Must have proper access permissions to download files
        """
        api_user = get_api_user(request=request)
        is_valid, message = validate_contents_download(urn=kwargs.get('urn', None), api_user=api_user)
        if is_valid:
            return download_contents_by_urn(urn=kwargs.get('urn'))
        else:
            raise ValidationError(detail={'ValidationError': message})
