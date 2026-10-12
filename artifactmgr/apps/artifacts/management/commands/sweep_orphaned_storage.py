"""
Report, and optionally remove, artifact storage directories that no Artifact row owns.

Before 1.13.0 an artifact delete removed only database rows, so every deleted artifact left
<storage>/<artifact_uuid>/ behind (issue #50). 1.13.0 cleans up on delete but does not sweep
what earlier deletes orphaned; this command does, as a one-off operator task.

Dry run by default. Only top-level directories whose name is a UUID are candidates; anything
else (dot-prefixed GitHub import temp files, stray names) is left alone. A directory modified
within --min-age-minutes is skipped so an upload whose row has not committed yet is never
mistaken for an orphan.
"""
import os
import time
from uuid import UUID

from django.core.files.storage import storages
from django.core.management.base import BaseCommand

from artifactmgr.apps.artifacts.models import Artifact
from artifactmgr.utils.artifact_version_storage import remove_artifact_contents


def _is_uuid(name: str) -> bool:
    try:
        return str(UUID(name)) == name.lower()
    except ValueError:
        return False


def _tree_size(path: str) -> int:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def find_orphaned_storage(min_age_minutes: int = 60) -> list[tuple[str, int]]:
    """Return (artifact_uuid, bytes) for each orphaned top-level storage directory."""
    location = storages['fabric_artifact_storage'].location
    if not os.path.isdir(location):
        return []
    known = {uuid.lower() for uuid in Artifact.objects.values_list('uuid', flat=True)}
    cutoff = time.time() - min_age_minutes * 60
    orphans = []
    with os.scandir(location) as entries:
        for entry in entries:
            if not entry.is_dir(follow_symlinks=False) or not _is_uuid(entry.name):
                continue
            if entry.name.lower() in known or entry.stat(follow_symlinks=False).st_mtime > cutoff:
                continue
            orphans.append((entry.name, _tree_size(entry.path)))
    return sorted(orphans)


class Command(BaseCommand):
    help = 'Report (default) or --delete artifact storage directories with no Artifact row'

    def add_arguments(self, parser):
        parser.add_argument('--delete', action='store_true',
                            help='remove the orphaned directories instead of only listing them')
        parser.add_argument('--min-age-minutes', type=int, default=60,
                            help='skip directories modified more recently than this (default 60)')

    def handle(self, *args, **options):
        orphans = find_orphaned_storage(options['min_age_minutes'])
        total = sum(size for _, size in orphans)
        for uuid, size in orphans:
            self.stdout.write('{0}\t{1}'.format(uuid, size))
        if not options['delete']:
            self.stdout.write('{0} orphaned directories, {1} bytes; dry run, nothing removed'.format(
                len(orphans), total))
            return
        failed = [uuid for uuid, _ in orphans if not remove_artifact_contents(uuid)]
        self.stdout.write('{0} orphaned directories, {1} bytes; removed {2}, failed {3}'.format(
            len(orphans), total, len(orphans) - len(failed), len(failed)))
