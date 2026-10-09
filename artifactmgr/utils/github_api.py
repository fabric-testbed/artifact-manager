"""Bounded, authenticated GitHub API reads and credential-free source downloads."""

import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import quote, urlsplit

import requests
from django.conf import settings
from urllib3.exceptions import HTTPError
from urllib3.util import Timeout

from artifactmgr.utils.api_logger import consoleLogger

API_ROOT = 'https://api.github.com'
TIMEOUT = (5, 15)
REQUEST_SECONDS = 50
REPOSITORY_RE = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})/[A-Za-z0-9_.-]{1,100}')
INVALID_TAG_CHAR = re.compile(r'[\x00-\x20\x7f\s~^:?*\[\\]')
COMMIT_RE = re.compile(r'[0-9a-fA-F]{40}')
_deadline = ContextVar('github_request_deadline', default=None)


class GitHubError(Exception):
    """A safe public error, independent of either DRF or the web UI."""

    def __init__(self, message, status_code=502):
        super().__init__(message)
        self.status_code = status_code


def validate_repository(repository: str) -> str:
    """Accept only an owner/repo, never a URL or a path with extra components."""
    if not isinstance(repository, str) or not REPOSITORY_RE.fullmatch(repository):
        raise GitHubError('Repository must be an owner/repo name.', 400)
    if repository.split('/')[1] in ('.', '..'):
        raise GitHubError('Invalid repository name.', 400)
    return repository


def validate_tag(tag: str) -> str:
    """Apply git ref rules to a tag of at most 128 characters; URLs quote it later."""
    if (not isinstance(tag, str) or not 1 <= len(tag) <= 128
            or tag == '@'
            or INVALID_TAG_CHAR.search(tag) or tag.startswith(('-', '/'))
            or tag.endswith(('/', '.')) or any(part.startswith('.') or part.endswith('.lock')
                                             for part in tag.split('/'))
            or any(part in tag for part in ('..', '@{', '//'))):
        raise GitHubError('Invalid release tag.', 400)
    return tag


@contextmanager
def request_deadline():
    """Share a time budget across an import's metadata and archive requests."""
    token = _deadline.set(_deadline.get() or time.monotonic() + REQUEST_SECONDS)
    try:
        yield
    finally:
        _deadline.reset(token)


def _remaining_seconds():
    deadline = _deadline.get()
    remaining = deadline - time.monotonic() if deadline is not None else REQUEST_SECONDS
    if remaining <= 0:
        raise GitHubError('GitHub import timed out; please retry.', 504)
    return remaining


def _check_deadline():
    _remaining_seconds()


def _request_timeout():
    remaining = _remaining_seconds()
    return Timeout(total=remaining, connect=min(TIMEOUT[0], remaining), read=min(TIMEOUT[1], remaining))


def _set_read_timeout(response):
    """Bound the next stalled read by the remaining whole-request budget.

    urllib3 has no public per-read timeout setter. Its connection usually owns the
    socket; for a Connection: close response http.client retains it in the file.
    At EOF both may already have been released, and read1 simply returns empty.
    """
    timeout = min(TIMEOUT[1], _remaining_seconds())
    connection = response.raw.connection
    sock = connection.sock if connection else None
    if sock is None:
        fp = getattr(response.raw._fp, 'fp', None)
        sock = getattr(getattr(fp, 'raw', None), '_sock', None)
    if sock is not None:
        sock.settimeout(timeout)


def _safe_url(url, host):
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        consoleLogger.exception('github_api: invalid redirect URL')
        raise GitHubError('GitHub returned an unsafe redirect.') from exc
    if (parsed.scheme != 'https' or parsed.netloc != host or parsed.hostname != host
            or parsed.username or parsed.password or parsed.fragment):
        raise GitHubError('GitHub returned an unsafe redirect.')
    return url


def _headers(accept='application/vnd.github+json'):
    headers = {'Accept': accept, 'X-GitHub-Api-Version': '2022-11-28'}
    if settings.GITHUB_API_TOKEN:
        headers['Authorization'] = 'Bearer ' + settings.GITHUB_API_TOKEN
    return headers


def _check_status(response):
    if response.status_code == 404:
        raise GitHubError('GitHub repository or release was not found.', 404)
    if response.status_code in (403, 429):
        raise GitHubError('GitHub is refusing requests; please retry later.', 503)
    if response.status_code != 200:
        # Read only one chunk, including when the response is a streamed archive error.
        body = next(response.iter_content(1024), b'').decode('utf-8', errors='replace')
        consoleLogger.error('github_api: unexpected status %s: %.512s', response.status_code, body)
        if response.status_code == 401:
            raise GitHubError('GitHub rejected the configured API token.')
        raise GitHubError('GitHub returned an unexpected response.')


def _api_get(path, accept='application/vnd.github+json'):
    """Follow at most one API-host redirect, including repository renames."""
    url = API_ROOT + path
    try:
        response = requests.get(url, headers=_headers(accept), timeout=_request_timeout(), allow_redirects=False)
        if response.status_code in (301, 302, 307, 308):
            location = response.headers.get('Location', '')
            response.close()
            url = _safe_url(location, 'api.github.com')
            response = requests.get(url, headers=_headers(accept), timeout=_request_timeout(), allow_redirects=False)
        return response
    except requests.RequestException as exc:
        consoleLogger.exception('github_api: API request failed')
        raise GitHubError('GitHub is unavailable; please retry.', 503) from exc


def _json(path, expected_type):
    with _api_get(path) as response:
        _check_status(response)
        try:
            data = response.json()
        except ValueError as exc:
            consoleLogger.exception('github_api: invalid JSON response')
            raise GitHubError('GitHub returned invalid JSON.') from exc
        _check_deadline()
        if not isinstance(data, expected_type):
            raise GitHubError('GitHub returned an unexpected response.')
        return data


def get_repo(repository):
    return _json('/repos/' + validate_repository(repository), dict)


def list_releases(repository):
    """Return published releases from at most 5 pages (500 releases), within the time budget."""
    repository = validate_repository(repository)
    releases = []
    with request_deadline():
        for page in range(1, 6):
            batch = _json('/repos/%s/releases?per_page=100&page=%s' % (repository, page), list)
            releases.extend(release for release in batch if release.get('draft') is False)
            if len(batch) < 100:
                break
    return releases


def get_release_by_tag(repository, tag):
    return _json('/repos/%s/releases/tags/%s' % (
        validate_repository(repository), quote(validate_tag(tag), safe='')), dict)


def resolve_tag_commit(repository, tag):
    with _api_get('/repos/%s/commits/tags/%s' % (
            validate_repository(repository), quote(validate_tag(tag), safe='')),
            accept='application/vnd.github.sha') as response:
        _check_status(response)
        commit = response.text.strip()
        _check_deadline()
        if not COMMIT_RE.fullmatch(commit):
            raise GitHubError('GitHub returned an invalid commit SHA.')
        return commit


def download_tarball(repository, commit, destination):
    """Stream a commit archive to an open binary file, without extracting it.

    read1 yields currently available bytes, so a slow trickle cannot hide inside a
    large iter_content chunk indefinitely. Socket timeouts bound stalled reads,
    clamped to the remaining budget; progressing downloads can use that entire budget.
    """
    repository = validate_repository(repository)
    if not isinstance(commit, str) or not COMMIT_RE.fullmatch(commit):
        raise GitHubError('Invalid commit SHA.', 400)
    with request_deadline():
        try:
            with requests.get(
                    API_ROOT + '/repos/%s/tarball/%s' % (repository, commit),
                    headers=_headers(), timeout=_request_timeout(), allow_redirects=False, stream=True) as response:
                if response.status_code != 302:
                    _check_status(response)
                    raise GitHubError('GitHub did not redirect to a source archive.')
                location = _safe_url(response.headers.get('Location', ''), 'codeload.github.com')
            # Deliberately a separate request with no Authorization or session cookies.
            with requests.get(location, headers={'Accept-Encoding': 'identity'}, timeout=_request_timeout(),
                              allow_redirects=False, stream=True) as response:
                _check_status(response)
                length = response.headers.get('Content-Length')
                if length and int(length) > settings.GITHUB_IMPORT_MAX_BYTES:
                    raise GitHubError('GitHub archive exceeds the import size limit.', 413)
                total = 0
                magic = b''
                while True:
                    _set_read_timeout(response)
                    chunk = response.raw.read1(64 * 1024, decode_content=False)
                    _check_deadline()
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > settings.GITHUB_IMPORT_MAX_BYTES:
                        raise GitHubError('GitHub archive exceeds the import size limit.', 413)
                    magic = (magic + chunk)[:2]
                    destination.write(chunk)
                if magic != b'\x1f\x8b':
                    raise GitHubError('GitHub archive is not gzip data.')
        except (requests.RequestException, HTTPError, OSError, ValueError) as exc:
            consoleLogger.exception('github_api: source archive download failed')
            raise GitHubError('GitHub archive download failed; please retry.', 503) from exc
