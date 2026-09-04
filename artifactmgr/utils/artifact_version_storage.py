import json
import mimetypes
import os
from datetime import datetime, timezone
from urllib.parse import quote
from uuid import uuid4

from django.conf import settings
from django.core.files.storage import storages
from django.http import FileResponse, HttpResponse
from django.utils.http import content_disposition_header
from rest_framework.exceptions import NotFound

from artifactmgr.apps.apiuser.models import ApiUser
from artifactmgr.apps.artifacts.models import Artifact, ArtifactAuthor, ArtifactVersion

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
    except NotFound:
        # A missing or unresolvable artifact is a 404, not a teapot.
        raise
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
        fabric_artifact.active = True
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


# mimetypes reports a .tgz bundle as ('application/x-tar', 'gzip'). Advertising that encoding
# would invite browsers to silently decompress the download, so fold it into the content type
# instead - the same mapping Django's own FileResponse applies.
ENCODING_CONTENT_TYPES = {
    'bzip2': 'application/x-bzip',
    'gzip': 'application/gzip',
    'xz': 'application/x-xz',
}


def fabric_artifact_download_headers(version: ArtifactVersion) -> tuple[str, str]:
    """
    Content type and download filename for an artifact version, e.g.
    ('application/gzip', 'My_Artifact.tar.gz'). The file is named after the artifact title
    rather than its stored filename.
    """
    storage = storages['fabric_artifact_storage']
    content_type, encoding = mimetypes.guess_type(version.filename)
    extension = mimetypes.guess_extension(content_type) if content_type else None
    suffix = (extension or '') + '.gz' if encoding == 'gzip' else (extension or '')
    filename = storage.get_valid_name(version.artifact.title) + suffix
    return ENCODING_CONTENT_TYPES.get(encoding, content_type or 'application/octet-stream'), filename


def download_fabric_artifact_contents(urn: str) -> HttpResponse:
    """
    Download FABRIC artifact from local storage.

    Bundles run to hundreds of megabytes, so the response never materialises the file in
    memory. Two strategies, chosen by settings.USE_X_ACCEL_REDIRECT:

    - FileResponse (default) streams the file in fixed-size chunks, and lets uWSGI use
      sendfile() where the server supports wsgi.file_wrapper. Works in every run mode.
    - X-Accel-Redirect returns headers only, naming an internal Nginx location over the same
      storage directory. Nginx sends the bytes and the uWSGI worker is released immediately
      rather than being held for the whole transfer. Requires the bundled Nginx.
    """
    storage = storages['fabric_artifact_storage']
    version = ArtifactVersion.objects.filter(uuid=urn.split(':')[-1]).first()
    if not version:
        raise NotFound(detail="FileNotFound: urn '{0}' not found".format(urn))
    fabric_artifact_contents = version.artifact_id + '/' + version.storage_id + '/' + version.filename
    if not storage.exists(fabric_artifact_contents):
        raise NotFound(detail="FileNotFound: urn '{0}' not found".format(urn))
    content_type, filename = fabric_artifact_download_headers(version=version)

    if settings.USE_X_ACCEL_REDIRECT:
        response = HttpResponse(content_type=content_type)
        # Nginx URL-decodes the redirect target before matching it against the internal
        # location, so the path has to be encoded on the way out.
        response.headers['X-Accel-Redirect'] = settings.X_ACCEL_LOCATION + quote(fabric_artifact_contents)
        response.headers['Content-Disposition'] = content_disposition_header(
            as_attachment=True, filename=filename)
        return response

    return FileResponse(
        storage.open(fabric_artifact_contents, mode='rb'),
        content_type=content_type,
        as_attachment=True,
        filename=filename,
    )


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
