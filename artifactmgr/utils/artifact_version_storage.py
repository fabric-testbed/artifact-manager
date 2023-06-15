import json
import mimetypes
import os
from datetime import datetime, timezone
from uuid import uuid4

from django.core.files.storage import storages
from django.http import HttpResponse
from rest_framework.exceptions import NotFound

from artifactmgr.apps.artifacts.models import ApiUser, Artifact, ArtifactAuthor, ArtifactVersion

"""
Artifact Version object
    - artifact - FK uuid              <-- request.data.artifact
    - created = UTC datetime          <-- datetime.now(timezone.utc)
    - created_by = FK uuid            <-- api_user
    - filename = uploaded file        <-- request.FILES.get
    - storage_id = path reference     <-- uuid/version
    - storage_repo = repository       <-- renci (git and zenodo at a later date)
    - storage_type = type of storage  <-- fabric (git and zenodo at a later date)
    - uuid = uuid4 string             <-- str(uuid4())
"""


def download_contents_by_urn(urn: str) -> HttpResponse:
    """
    urn:storage_type:contents:storage_repo:uuid
    - urn - static
    - storage_type - in [fabric, git, zenodo]
    - contents - static
    - storage_repo - in [renci, github, zenodo]
    - uuid - unique identifier of artifact version
    """
    try:
        storage_type = urn.split(':')[1]
        if storage_type in [ArtifactVersion.FABRIC]:
            return download_fabric_artifact_contents(urn=urn)
        elif storage_type in [ArtifactVersion.GIT]:
            return download_git_artifact_contents(urn=urn)
        elif storage_type in [ArtifactVersion.ZENODO]:
            return download_zenodo_artifact_contents(urn=urn)
        else:
            return HttpResponse(content="UrnNotFound: urn '{0}".format(urn), status=404)
    except Exception as exc:
        print(exc)
        return HttpResponse(content="IAmATeapot: I am a teapot", status=418)


def create_fabric_artifact_contents(request, api_user: ApiUser) -> ArtifactVersion | None:
    """
    Create FABRIC artifact on local storage
    """
    try:
        storage = storages['fabric_artifact_storage']
        artifact_file = request.FILES.get('file')
        request_data = request.data['data']
        if not isinstance(request_data, dict):
            request_data = json.loads(request_data)
        if not artifact_file:
            return None
        artifact = Artifact.objects.filter(uuid=request_data.get('artifact', None)).first()
        if not artifact:
            return None
        now = datetime.now(timezone.utc)
        storage_type = request_data.get('storage_type', None)
        version_uuid = str(uuid4())
        version_storage_id = now.strftime('%Y-%m-%d')
        storage_path = artifact.uuid + '/' + version_storage_id + '/'
        ver = 1
        while storage.exists(storage_path):
            version_storage_id = now.strftime('%Y-%m-%d') + '.{0}'.format(str(ver))
            storage_path = artifact.uuid + '/' + version_storage_id + '/'
            ver += 1
        artifact_file_path = storage.save(storage_path + artifact_file.name, artifact_file)
        fabric_artifact = ArtifactVersion()
        fabric_artifact.artifact = artifact
        fabric_artifact.created = now
        fabric_artifact.created_by = ArtifactAuthor.objects.filter(uuid=api_user.uuid).first()
        fabric_artifact.filename = artifact_file.name
        fabric_artifact.storage_id = version_storage_id
        fabric_artifact.storage_repo = os.getenv('FABRIC_ARTIFACT_STORAGE_REPO')
        fabric_artifact.storage_type = storage_type
        fabric_artifact.uuid = version_uuid
        fabric_artifact.save()
        print('saved to path: ', artifact_file_path)
        return fabric_artifact
    except Exception as exc:
        print(exc)
        return None


def download_fabric_artifact_contents(urn: str) -> HttpResponse:
    """
    Download FABRIC artifact from local storage
    """
    try:
        storage = storages['fabric_artifact_storage']
        fabric_artifact_contents = ArtifactVersion.objects.filter(uuid=urn.split(':')[-1]).first()
        if storage.exists(fabric_artifact_contents.filename):
            mime_type, _ = mimetypes.guess_type(storage.path(fabric_artifact_contents.filename))
            with storage.open(fabric_artifact_contents.filename, mode='rb') as fh:
                data = fh.read()
            response = HttpResponse(data, content_type=mime_type)
            response.headers['Content-Disposition'] = "attachment; filename=%s" % storage.get_valid_name(
                fabric_artifact_contents.filename)
            return response
    except Exception as exc:
        print(exc)
        raise NotFound(detail="FileNotFound: urn '{0}' not found".format(urn))


def remove_fabric_artifact_contents() -> bool:
    """
    Remove FABRIC artifact from local storage
    """
    return True


def create_git_artifact_contents() -> ArtifactVersion | None:
    """
    Create Git artifact
    """
    git_artifact = ArtifactVersion()
    return None


def download_git_artifact_contents(urn: str) -> HttpResponse:
    """
    Download Git artifact
    """
    response = HttpResponse()
    return response


def remove_git_artifact_contents() -> bool:
    """
    Remove Git artifact
    """
    return True


def create_zenodo_artifact_contents() -> ArtifactVersion | None:
    """
    Create Zenodo artifact
    """
    zenodo_artifact = ArtifactVersion()
    return None


def download_zenodo_artifact_contents(urn: str) -> HttpResponse:
    """
    Download Zenodo artifact
    """
    response = HttpResponse()
    return response


def remove_zenodo_artifact_contents() -> bool:
    """
    Remove Zenodo artifact
    """
    return True
