import json
import os

from rest_framework.exceptions import ValidationError

from artifactmgr.apps.apiuser.models import ApiUser
from artifactmgr.apps.artifacts.models import Artifact, ArtifactAuthor, ArtifactTag, ArtifactVersion
from artifactmgr.utils.api_logger import consoleLogger
from artifactmgr.utils.core_api import (
    PERSON_LOOKUP_FAILED,
    PERSON_NOT_FOUND,
    lookup_fabric_person,
    query_core_api_by_cookie,
    query_core_api_by_token,
)
from artifactmgr.utils.fabric_auth import is_valid_uuid
from artifactmgr.utils.github_api import GitHubError, validate_repository, validate_tag

# valid filename extensions for artifact contents (.tgz, .tar.gz); matched case-insensitively.
# Checked by extension rather than mimetypes.guess_type(), whose result depends on the host's
# mime database and is case-sensitive on the compound .tar.gz suffix.
valid_upload_extensions = ('.tgz', '.tar.gz')


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
        upload_file = request.FILES.get('file')
        if upload_file is None:
            message.append({'file': 'missing a \'file\' to create an artifact from'})
        elif not upload_file.name.lower().endswith(valid_upload_extensions):
            message.append({'mimetypes': 'Invalid file type for \'{0}\', must be .tgz or .tar.gz'.format(
                upload_file.name)})
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
                message.append({'data.storage_type': 'Import GitHub releases via POST /api/artifacts/{uuid}/repo/import'})
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
        consoleLogger.warning('validate_artifact_version_create: %s: %s', type(exc).__name__, exc)
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
                outcome, _ = lookup_fabric_person(request=request, api_user=api_user, uuid=author)
                if outcome == PERSON_NOT_FOUND:
                    message.append({'authors': 'unable to find user: \'{0}\''.format(author)})
                elif outcome == PERSON_LOOKUP_FAILED:
                    message.append(
                        {'authors': 'unable to verify user \'{0}\' with the Core API; please retry'.format(author)})
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
        consoleLogger.warning('validate_artifact_create: %s: %s', type(exc).__name__, exc)
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
                # authors already known to the artifact-manager were validated when first
                # added; skip the redundant live Core API lookup for them (also avoids a
                # transient Core API failure on an existing author blocking the edit).
                if ArtifactAuthor.objects.filter(uuid=author).exists():
                    continue
                outcome, _ = lookup_fabric_person(request=request, api_user=api_user, uuid=author)
                if outcome == PERSON_NOT_FOUND:
                    message.append({'authors': 'unable to find user: \'{0}\''.format(author)})
                elif outcome == PERSON_LOOKUP_FAILED:
                    message.append(
                        {'authors': 'unable to verify user \'{0}\' with the Core API; please retry'.format(author)})
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
        consoleLogger.warning('validate_artifact_update: %s: %s', type(exc).__name__, exc)
        message.append({'APIException': exc})
    if len(message) > 0:
        return False, message
    else:
        return True, None


def validate_artifact_version_update(request) -> tuple:
    """
    PUT/PATCH /api/contents/{uuid}
    - 'active': boolean - optional
    """
    message = []
    try:
        request_data = request.data
        # 'active': boolean - optional
        active = request_data.get('active', None)
        if active and str(active).casefold() not in ['true', 'false']:
            message.append({'active': 'must be boolean or None, not: \'{0}\''.format(active)})
    except Exception as exc:
        consoleLogger.warning('validate_artifact_version_update: %s: %s', type(exc).__name__, exc)
        message.append({'APIException': exc})
    if len(message) > 0:
        return False, message
    else:
        return True, None


def validate_github_repository(value):
    """DRF field validator for the shared GitHub owner/repo allowlist."""
    try:
        return validate_repository(value)
    except GitHubError as exc:
        raise ValidationError(str(exc)) from exc


def validate_github_tag(value):
    """DRF field validator for tags, including tags containing slashes."""
    try:
        return validate_tag(value)
    except GitHubError as exc:
        raise ValidationError(str(exc)) from exc
