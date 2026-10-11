import json

from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import filters, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from artifactmgr.apps.artifacts.api.context import is_crawler, request_api_user
from artifactmgr.apps.artifacts.api.validators import validate_artifact_version_create, \
    validate_artifact_version_update
from artifactmgr.apps.artifacts.api.version_serializers import ArtifactContentsUploadSerializer, \
    ArtifactVersionSerializer, ArtifactVersionUpdateSerializer
from artifactmgr.apps.artifacts.models import Artifact, ArtifactVersion, VersionDownloads
from artifactmgr.utils.api_logger import consoleLogger, metrics_event, VERSION
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
    serializer_classes = {
        'list': ArtifactVersionSerializer,
        'create': ArtifactContentsUploadSerializer,
        'retrieve': ArtifactVersionSerializer,
        'update': ArtifactVersionUpdateSerializer,
        'partial_update': ArtifactVersionUpdateSerializer,
        'destroy': ArtifactVersionSerializer,
    }
    default_serializer_class = ArtifactVersionSerializer
    parser_classes = [FormParser, MultiPartParser]
    search_fields = ['storage_repo', 'storage_type']
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    permission_classes = [permissions.AllowAny]
    lookup_field = 'uuid'

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return ArtifactVersion.objects.none()
        api_user = request_api_user(self.request, get_api_user)
        return ArtifactVersion.objects.filter(
            Q(artifact__visibility=Artifact.PUBLIC) |
            Q(artifact__project_uuid__in=api_user.projects) |
            Q(artifact__authors__uuid__contains=api_user.uuid)
        ).select_related('artifact').annotate(
            download_count=Count('version_downloads', distinct=True)
        ).distinct().order_by('-created')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        if not getattr(self, 'swagger_fake_view', False):
            context['api_user'] = request_api_user(self.request, get_api_user)
        return context

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
        api_user = request_api_user(self.request, get_api_user)
        data = request.data.getlist('data')
        request_data = data[0] if data else None
        try:
            request_data = json.loads(request_data)
        except (TypeError, ValueError):
            # the web UI posts 'data' as a dict inside the QueryDict rather than as a JSON string
            pass
        if not isinstance(request_data, dict):
            raise ValidationError(detail={'ValidationError': [{'data': 'must be a JSON object'}]})
        artifact = Artifact.objects.filter(uuid=request_data.get('artifact', None)).first()
        # ensure artifact exists and that api_user is an author of the artifact
        if artifact and api_user.uuid in [a.uuid for a in artifact.authors.all()]:
            is_valid, message = validate_artifact_version_create(request, api_user=api_user)
            if is_valid:
                artifact_version = create_fabric_artifact_contents(request=request, api_user=api_user)
                if artifact_version:
                    metrics_event(VERSION, artifact_version.uuid, 'create', for_artifact=artifact.uuid,
                                  by=api_user.uuid)
                return Response(data=ArtifactVersionSerializer(instance=artifact_version, context={'api_user': api_user}).data, status=201)
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
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        """
        update (PATCH {int:pk})
        - Must be an author of the Artifact to update Artifact contents
        """
        api_user = request_api_user(self.request, get_api_user)
        version = get_object_or_404(ArtifactVersion, uuid=kwargs.get('uuid'))
        artifact = version.artifact
        if api_user.uuid in [a.uuid for a in artifact.authors.all()]:
            is_valid, message = validate_artifact_version_update(request)
            if is_valid:
                request_data = request.data
                # active
                active_orig = version.active
                active = request_data.get('active', None)
                if str(active).casefold() == 'true':
                    version.active = True
                if str(active).casefold() == 'false':
                    version.active = False
                version.save()
                if version.active != active_orig:
                    metrics_event(VERSION, version.uuid, 'modify', 'active', version.active, by=api_user.uuid)
                # return updated artifact
                return Response(data=ArtifactVersionSerializer(instance=version, context={'api_user': api_user}).data, status=204)
            else:
                raise ValidationError(detail={'ValidationError': message})
        else:
            raise PermissionDenied(
                detail="PermissionDenied: user:'{0}' is unable to update /contents/{1}".format(api_user.uuid,
                                                                                               kwargs.get('uuid')))

    def partial_update(self, request, *args, **kwargs):
        """
        partial_update (PATCH {int:pk})
        """
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """
        destroy (DELETE {int:pk})
        """
        raise MethodNotAllowed(method='DELETE', detail='MethodNotAllowed: DELETE /api/contents/{uuid}')

    @extend_schema(
        parameters=[OpenApiParameter(name="urn", type=str, location=OpenApiParameter.PATH)]
    )
    @action(detail=False, methods=['get'], url_path='download/(?P<urn>[^/.]+)')
    def download(self, request, *args, **kwargs) -> HttpResponse:
        """
        Download FABRIC Artifact Contents by URN
        - Must have proper access permissions to download files
        """
        api_user = request_api_user(self.request, get_api_user)
        version_urn = str(kwargs.get('urn', None))
        # visibility-filtered lookup: a version that is missing, hidden from api_user, does not match the
        # requested urn, or is retired is a 404 so that the endpoint confirms nothing to the caller
        version = self.get_queryset().filter(uuid=version_urn.split(':')[-1]).first()
        if version is None or version.urn != version_urn or not version.active:
            raise NotFound(detail="No artifact contents match urn '{0}'.".format(version_urn))
        # increment version_downloads - crawler requests are served without being counted, but the
        # metrics event is always written so the audit stream stays complete
        try:
            if not is_crawler(request):
                version_download = VersionDownloads(downloaded_by=str(api_user.uuid))
                version_download.save()
                version.version_downloads.add(version_download)
            metrics_event(VERSION, version.uuid, 'download', by=api_user.uuid)
        except Exception:
            consoleLogger.exception('version download: unable to record a download of %s', version_urn)
        return download_contents_by_urn(urn=version_urn)
