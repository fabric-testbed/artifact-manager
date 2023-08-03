import json
import os

from artifactmgr.apps.artifacts.models import ApiUser, Artifact, ArtifactAuthor, ArtifactTag, ArtifactVersion
from artifactmgr.utils.core_api import query_core_api_by_cookie, query_core_api_by_token
from artifactmgr.utils.fabric_auth import is_valid_uuid


def validate_contents_download(urn: str, api_user: ApiUser) -> tuple:
    """
    GET api/contents/download/{urn}
    - api_user - user making the request
    urn:storage_type:contents:storage_repo:uuid
    - urn - static
    - storage_type - in [fabric, git, zenodo]
    - contents - static
    - storage_repo - in [renci, github, zenodo]
    - uuid - unique identifier of artifact version
    """
    message = []
    try:
        # artifact version check
        artifact_version = ArtifactVersion.objects.filter(uuid=urn.split(':')[-1]).first()
        if not artifact_version:
            message.append({'NotFound': 'artifact with urn = \'{0}\' not found'.format(urn)})
        else:
            if artifact_version.urn != urn:
                message.append({'DoesNotMatch': 'artifact urn does not match urn = \'{0}\' not found'.format(urn)})
            artifact = artifact_version.artifact
            # artifact permissions check
            author = ArtifactAuthor.objects.filter(uuid=api_user.uuid).first()
            # author - api_user must be an author of artifact
            if artifact.visibility == Artifact.AUTHOR and (not author or author not in artifact.authors.all()):
                message.append({'PermissionsAuthor': 'api_user does not have permission to download this resource'})
            # project - api_user must be an author of artifact or project member linked to the artifact
            if artifact.visibility == Artifact.PROJECT and (
                    not author or author not in artifact.authors.all() or artifact.project_uuid not in api_user.projects):
                message.append({'PermissionsProject': 'api_user does not have permission to download this resource'})
            # public - download available to any user
    except Exception as exc:
        message.append({'APIException': exc})

    if len(message) > 0:
        return False, message
    else:
        return True, None


def validate_artifact_version_create(request, api_user: ApiUser) -> tuple:
    """
    POST /api/contents
    - artifact - FK uuid              <-- request.data.artifact
    - file = uploaded file            <-- request.FILES.get
    - storage_repo = repository       <-- request.data.storage_repo
    - storage_type = type of storage  <-- request.data.storage_type
    """
    message = []
    try:
        request_keys = request.data.keys()
        if 'file' not in request_keys:
            message.append({'file': 'missing a \'file\' to create an artifact from'})
        if 'data' not in request_keys:
            message.append({'data': 'missing the \'data\' attributes to create an artifact from'})
        request_data = request.data['data']
        if not isinstance(request_data, dict):
            request_data = json.loads(request_data)
        artifact_uuid = request_data.get('artifact', None)
        artifact = Artifact.objects.filter(uuid=artifact_uuid).first()
        if not artifact_uuid or not artifact:
            message.append({'data.artifact': 'invalid artifact uuid reference'})
        else:
            if api_user.uuid not in [a.uuid for a in artifact.authors.all()]:
                message.append(
                    {'InvalidPermissions': 'api_user \'{0}\' is not an author of this artifact'.format(api_user.uuid)})
        storage_repo = request_data.get('storage_repo', None)
        if not storage_repo:
            message.append({'data.storage_repo': 'invalid storage_repo'})
        storage_type = request_data.get('storage_type', None)
        if not storage_type or storage_type not in [t[0] for t in ArtifactVersion.STORAGE_TYPE_CHOICES]:
            message.append({'data.storage_type': 'invalid storage_type'})
        else:
            if storage_type == ArtifactVersion.FABRIC and storage_repo:
                if storage_repo not in [os.getenv('FABRIC_ARTIFACT_STORAGE_REPO')]:
                    message.append(
                        {'data.storage_repo': 'invalid storage_repo for storage_type: \'{0}\''.format(storage_type)})
            elif storage_type == ArtifactVersion.GIT and storage_repo:
                # TODO: update once Git support is available
                message.append({'data.storage_repo': 'Git is not supported at this time'})
                if storage_repo not in ['github']:
                    message.append(
                        {'data.storage_repo': 'invalid storage_repo for storage_type: \'{0}\''.format(storage_type)})
            elif storage_type == ArtifactVersion.ZENODO and storage_repo:
                # TODO: update once Zenodo support is available
                message.append({'data.storage_repo': 'Zenodo is not supported at this time'})
                if storage_repo not in ['zenodo']:
                    message.append(
                        {'data.storage_repo': 'invalid storage_repo for storage_type: \'{0}\''.format(storage_type)})
            else:
                message.append({'data.storage_repo': 'invalid storage_repo'})
    except Exception as exc:
        message.append({'APIException': exc})

    if len(message) > 0:
        return False, message
    else:
        return True, None


def validate_artifact_create(request, api_user: ApiUser) -> tuple:
    """
    POST /api/artifacts
    - 'authors': ['string'] - optional
    - 'description_long': 'string' - required
    - 'description_short': 'string' - optional
    - 'project_uuid': 'string' - optional (required if visibility = project)
    - 'tags': ['string', ...] - optional
    - 'title': 'string' - required
    - 'visibility': 'author' - required, one of author, project, public
    """
    message = []
    try:
        request_data = request.data
        # 'authors': ['string'] - optional
        authors = request_data.get('authors', [])
        for author in authors:
            if is_valid_uuid(author):
                if api_user.access_type == ApiUser.COOKIE:
                    fab_user = query_core_api_by_cookie(
                        query='/people/{0}?as_self=false'.format(author),
                        cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None))
                else:
                    fab_user = query_core_api_by_token(
                        query='/people/{0}?as_self=false'.format(author),
                        token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', ''))
                if fab_user.get('size') != 1 or fab_user.get('status') != 200:
                    message.append({'authors': 'unable to find user: \'{0}\''.format(author)})
            else:
                message.append({'authors': 'invalid uuid format: \'{0}\''.format(author)})
        # 'description_long': 'string' - optional
        description_long = request_data.get('description_long', None)
        if description_long and (
                len(description_long) < int(os.getenv('MIN_DESCRIPTION_LENGTH')) or len(description_long) > int(
            os.getenv('MAX_DESCRIPTION_LONG_LENGTH'))):
            message.append(
                {'description_long': 'invalid length: \'{0}\', must be between {1} and {2} characters'.format(
                    len(description_long), os.getenv('MIN_DESCRIPTION_LENGTH'),
                    os.getenv('MAX_DESCRIPTION_LONG_LENGTH'))})
        # 'description_short': 'string' - required
        description_short = request_data.get('description_short', '')
        if not description_short or len(description_short) < int(os.getenv('MIN_DESCRIPTION_LENGTH')) or len(
                description_short) > int(os.getenv('MAX_DESCRIPTION_SHORT_LENGTH')):
            message.append(
                {'description_short': 'invalid length: \'{0}\', must be between {1} and {2} characters'.format(
                    len(description_short), os.getenv('MIN_DESCRIPTION_LENGTH'),
                    os.getenv('MAX_DESCRIPTION_SHORT_LENGTH'))})
        # 'project_uuid': 'string' - optional (required if visibility = project)
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
            if fab_project.get('size') != 1 or fab_project.get('status') != 200:
                message.append({'project_uuid': 'unable to find project: \'{0}\''.format(project_uuid)})
            if project_uuid not in api_user.projects:
                message.append({'project_uuid': 'user is not member of project: \'{0}\''.format(project_uuid)})
        # 'tags': ['string', ...] - optional
        tags = request_data.get('tags', [])
        for tag in tags:
            if not ArtifactTag.objects.filter(tag=tag).exists():
                message.append({'tags': 'invalid tag: \'{0}\''.format(tag)})
        # 'title': 'string' - required
        title = request_data.get('title', '')
        if title and (
                len(title) < int(os.getenv('MIN_DESCRIPTION_LENGTH')) or len(title) > int(
            os.getenv('MAX_DESCRIPTION_SHORT_LENGTH'))):
            message.append({'title': 'invalid length: \'{0}\', must be between {1} and {2} characters'.format(
                len(title), os.getenv('MIN_DESCRIPTION_LENGTH'), os.getenv('MAX_DESCRIPTION_SHORT_LENGTH'))})
        # 'visibility': 'author' - required, one of author, project, public
        visibility = request_data.get('visibility', None)
        if visibility and visibility in [a[0] for a in Artifact.VISIBILITY_CHOICES]:
            # if project level verify project_uuid
            if visibility == 'project' and not project_uuid:
                message.append({'visibility': 'corresponding project_uuid required: \'{0}\''.format(visibility)})
        else:
            message.append({'visibility': 'invalid option: \'{0}\''.format(visibility)})
    except Exception as exc:
        message.append({'APIException': exc})
    if len(message) > 0:
        return False, message
    else:
        return True, None


def validate_artifact_update(request, api_user: ApiUser) -> tuple:
    """
    PUT/PATCH /api/artifacts/{uuid}
    - 'authors': ['string'] - optional
    - 'description_long': 'string' - required
    - 'description_short': 'string' - optional
    - 'project_uuid': 'string' - optional (required if visibility = project)
    - 'tags': ['string', ...] - optional
    - 'title': 'string' - required
    - 'visibility': 'author' - required, one of author, project, public
    """
    message = []
    try:
        request_data = request.data
        # 'authors': ['string'] - optional
        authors = request_data.get('authors', [])
        for author in authors:
            if is_valid_uuid(author):
                if api_user.access_type == ApiUser.COOKIE:
                    fab_user = query_core_api_by_cookie(
                        query='/people/{0}?as_self=false'.format(author),
                        cookie=request.COOKIES.get(os.getenv('VOUCH_COOKIE_NAME'), None))
                else:
                    fab_user = query_core_api_by_token(
                        query='/people/{0}?as_self=false'.format(author),
                        token=request.headers.get('authorization', 'Bearer ').replace('Bearer ', ''))
                if fab_user.get('size') != 1 or fab_user.get('status') != 200:
                    message.append({'authors': 'unable to find user: \'{0}\''.format(author)})
            else:
                message.append({'authors': 'invalid uuid format: \'{0}\''.format(author)})
        # 'description_long': 'string' - required
        description_long = request_data.get('description_long', None)
        if description_long and (len(description_long) < int(os.getenv('MIN_DESCRIPTION_LENGTH')) or len(
                description_long) > int(os.getenv('MAX_DESCRIPTION_LONG_LENGTH'))):
            message.append(
                {'description_long': 'invalid length: \'{0}\', must be between {1} and {2} characters'.format(
                    len(description_long), os.getenv('MIN_DESCRIPTION_LENGTH'),
                    os.getenv('MAX_DESCRIPTION_LONG_LENGTH'))})
        # 'description_short': 'string' - optional
        description_short = request_data.get('description_short', None)
        if description_short and (
                len(description_short) < int(os.getenv('MIN_DESCRIPTION_LENGTH')) or len(description_short) > int(
            os.getenv('MAX_DESCRIPTION_SHORT_LENGTH'))):
            message.append(
                {'description_short': 'invalid length: \'{0}\', must be between {1} and {2} characters'.format(
                    len(description_short), os.getenv('MIN_DESCRIPTION_LENGTH'),
                    os.getenv('MAX_DESCRIPTION_SHORT_LENGTH'))})
        # 'project_uuid': 'string' - optional (required if visibility = project)
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
            if fab_project.get('size') != 1 or fab_project.get('status') != 200:
                message.append({'project_uuid': 'unable to find project: \'{0}\''.format(project_uuid)})
            if project_uuid not in api_user.projects:
                message.append({'project_uuid': 'user is not member of project: \'{0}\''.format(project_uuid)})
        # 'tags': ['string', ...] - optional
        tags = request_data.get('tags', [])
        for tag in tags:
            if not ArtifactTag.objects.filter(tag=tag).exists():
                message.append({'tags': 'invalid tag: \'{0}\''.format(tag)})
        # 'title': 'string' - required
        title = request_data.get('title', None)
        if title and (
                len(title) < int(os.getenv('MIN_DESCRIPTION_LENGTH')) or len(title) > int(
            os.getenv('MAX_DESCRIPTION_SHORT_LENGTH'))):
            message.append({'title': 'invalid length: \'{0}\', must be between {1} and {2} characters'.format(
                len(title), os.getenv('MIN_DESCRIPTION_LENGTH'), os.getenv('MAX_DESCRIPTION_SHORT_LENGTH'))})
        # 'visibility': 'author' - required, one of author, project, public
        visibility = request_data.get('visibility', None)
        if visibility:
            if visibility not in [a[0] for a in Artifact.VISIBILITY_CHOICES]:
                message.append({'visibility': 'invalid option: \'{0}\''.format(visibility)})
            # if project level verify project_uuid
            if visibility == 'project' and not project_uuid:
                message.append({'visibility': 'corresponding project_uuid required: \'{0}\''.format(visibility)})

    except Exception as exc:
        message.append({'APIException': exc})
    if len(message) > 0:
        return False, message
    else:
        return True, None
