"""Repository linking and release imports shared by API and web entry points."""

import hashlib
from contextlib import contextmanager

from django.conf import settings
from django.db import IntegrityError, connection
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from artifactmgr.apps.artifacts.models import ArtifactRepoLink, ArtifactVersion
from artifactmgr.utils import github_api
from artifactmgr.utils.api_logger import ARTIFACT, VERSION, consoleLogger, metrics_event
from artifactmgr.utils.artifact_version_storage import create_git_artifact_contents


class RepoLinkError(Exception):
    """A domain error whose status can be mapped by an HTTP entry point."""

    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def _require_author(artifact, author):
    if author is None or not artifact.authors.filter(uuid=author.uuid).exists():
        raise RepoLinkError('Only an artifact author may perform this operation.', 403)
    return artifact.authors.get(uuid=author.uuid)


def get_link(artifact):
    """Read fresh state rather than a possibly cached reverse OneToOne relation."""
    link = ArtifactRepoLink.objects.filter(artifact=artifact).select_related('linked_by').first()
    if link is None:
        raise RepoLinkError('This artifact has no linked GitHub repository.', 400)
    return link


def validate_publisher(artifact, claims):
    """Use one generic denial for every artifact/link authorization failure."""
    link = ArtifactRepoLink.objects.filter(artifact=artifact).select_related('linked_by').first() if artifact else None
    if (not link or not link.publishing_enabled or link.provider != 'github'
            or claims.get('repository_id') != link.repo_id
            or claims.get('repository_owner_id') != link.repo_owner_id
            or claims.get('event_name') in ('pull_request', 'pull_request_target')
            or claims.get('repository_visibility') != 'public'):
        raise RepoLinkError('GitHub publishing is not permitted.', 403)
    return link


@contextmanager
def artifact_lock(artifact):
    """Serialize link changes and imports across PostgreSQL worker connections."""
    key = int.from_bytes(hashlib.blake2b(
        ('github-import:' + artifact.uuid).encode(), digest_size=8).digest(), 'big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_try_advisory_lock(%s)', [key])
        acquired = cursor.fetchone()[0]
    if not acquired:
        raise RepoLinkError('An operation on this artifact is in progress; please retry.', 409)
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s)', [key])


@contextmanager
def _import_slot():
    """Two global slots, in the separate two-integer advisory-lock namespace."""
    slot = None
    with connection.cursor() as cursor:
        for candidate in range(2):
            cursor.execute('SELECT pg_try_advisory_lock(%s, %s)', [0x47485442, candidate])
            if cursor.fetchone()[0]:
                slot = candidate
                break
    if slot is None:
        raise RepoLinkError('GitHub imports are busy; please retry.', 503)
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_unlock(%s, %s)', [0x47485442, slot])


def _public_repo(repository):
    repo = github_api.get_repo(repository)
    if repo.get('private') is not False:
        raise RepoLinkError('Only public GitHub repositories may be linked or imported.', 400)
    github_api.validate_repository(repo.get('full_name'))
    if (not isinstance(repo.get('id'), int) or not isinstance(repo.get('owner', {}).get('id'), int)
            or not isinstance(repo.get('html_url'), str)):
        raise github_api.GitHubError('GitHub returned incomplete repository metadata.')
    return repo


def _refresh_repo(link):
    repo = _public_repo(link.repo_full_name)
    if str(repo['id']) != link.repo_id or str(repo['owner']['id']) != link.repo_owner_id:
        raise RepoLinkError('The GitHub repository identity changed; an author must re-confirm the link.', 409)
    if repo['full_name'] != link.repo_full_name or repo['html_url'] != link.html_url:
        link.repo_full_name = repo['full_name']
        link.html_url = repo['html_url']
        # A rename is not an author re-confirmation: preserve linked_at and linked_by.
        link.save(update_fields=['repo_full_name', 'html_url'])
    return repo


def link_repo(artifact, repository, linked_by):
    """Any current author can link or re-confirm a public repository."""
    author = _require_author(artifact, linked_by)
    github_api.validate_repository(repository)
    with artifact_lock(artifact), github_api.request_deadline():
        repo = _public_repo(repository)
        link, _ = ArtifactRepoLink.objects.update_or_create(artifact=artifact, defaults={
            'provider': 'github', 'repo_full_name': repo['full_name'], 'repo_id': str(repo['id']),
            'repo_owner_id': str(repo['owner']['id']), 'html_url': repo['html_url'], 'linked_by': author,
        })
        metrics_event(ARTIFACT, artifact.uuid, 'modify', 'repository', link.repo_full_name, by=author.uuid)
        return link


def unlink_repo(artifact, author):
    _require_author(artifact, author)
    with artifact_lock(artifact):
        ArtifactRepoLink.objects.filter(artifact=artifact).delete()
        metrics_event(ARTIFACT, artifact.uuid, 'modify', 'repository', None, by=author.uuid)


def list_releases(artifact, author):
    _require_author(artifact, author)
    with github_api.request_deadline():
        link = get_link(artifact)
        _refresh_repo(link)
        imported = set(ArtifactVersion.objects.filter(
            artifact=artifact, source_repo_id=link.repo_id).values_list('source_tag', flat=True))
        return [dict(release, imported=release['tag_name'] in imported)
                for release in github_api.list_releases(link.repo_full_name)]


def import_release(artifact, tag, created_by, trigger, *, claims=None):
    """Return (version, created), with fresh authorization under the import lock.

    Actions claims are checked again here so a concurrent relink cannot change the
    repository trusted between the view's initial authorization and the download.
    Duplicate retries do not consume another daily import, even at the daily cap.
    """
    github_api.validate_tag(tag)
    if trigger not in ('action', 'web', 'api'):
        raise RepoLinkError('Invalid import trigger.')
    if trigger in ('web', 'api'):
        created_by = _require_author(artifact, created_by)
        get_link(artifact)
    with artifact_lock(artifact), github_api.request_deadline():
        if trigger == 'action':
            link = validate_publisher(artifact, claims or {})
            created_by = link.linked_by
        else:
            created_by = _require_author(artifact, created_by)
            link = get_link(artifact)
        imports_today = ArtifactVersion.objects.filter(
            artifact=artifact, storage_type=ArtifactVersion.GIT, created__date=timezone.now().date()).count()
        identity = {'artifact': artifact, 'source_repo_id': link.repo_id, 'source_tag': tag}
        existing = ArtifactVersion.objects.filter(**identity).first()
        if existing:
            return existing, False
        if imports_today >= settings.GITHUB_IMPORTS_PER_DAY:
            raise RepoLinkError('This artifact has reached its daily GitHub import limit.', 429)
        with _import_slot():
            _refresh_repo(link)
            release = github_api.get_release_by_tag(link.repo_full_name, tag)
            if release.get('draft') is not False or not release.get('published_at'):
                raise RepoLinkError('Only published GitHub Releases may be imported.')
            if (not isinstance(release.get('html_url'), str) or not release['html_url']
                    or (release.get('name') is not None and not isinstance(release['name'], str))
                    or not isinstance(release.get('prerelease'), bool)
                    or not isinstance(release['published_at'], str)):
                raise github_api.GitHubError('GitHub returned incomplete release metadata.')
            try:
                published_at = parse_datetime(release['published_at'])
            except ValueError:
                published_at = None
            if published_at is None:
                raise github_api.GitHubError('GitHub returned an invalid release publication date.')
            if release.get('tag_name') != tag:
                raise RepoLinkError('GitHub returned a different release tag.', 409)
            commit = github_api.resolve_tag_commit(link.repo_full_name, tag)
            try:
                version = create_git_artifact_contents(artifact, link, release, commit, created_by, trigger)
            except IntegrityError:
                # Storage has rolled back its own atomic insert and removed its file.
                consoleLogger.exception('repo_link: concurrent insert for artifact %s tag %s', artifact.uuid, tag)
                existing = ArtifactVersion.objects.filter(**identity).first()
                if existing is None:
                    raise
                return existing, False
            metrics_event(VERSION, version.uuid, 'create', for_artifact=artifact.uuid, by=created_by.uuid)
            return version, True
