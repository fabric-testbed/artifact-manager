"""Serializers for uploaded and GitHub-sourced artifact versions."""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from artifactmgr.apps.artifacts.api.repo_serializers import GitHubSourceSerializer
from artifactmgr.apps.artifacts.api.context import artifact_visibility

from artifactmgr.apps.artifacts.models import ArtifactVersion


class ArtifactContentsUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    data = serializers.JSONField(
        default={"artifact": "uuid-as-string", "storage_type": "fabric", "storage_repo": "renci"})

    class Meta:
        fields = ['file', 'data']


class ArtifactVersionSerializer(serializers.ModelSerializer):
    """
    Artifact Version Serializer
    - artifact = models.ForeignKey(Artifact, on_delete=models.CASCADE, related_name="artifact_version")
    - created = models.DateTimeField(auto_now_add=True)
    - filename = models.CharField(max_length=255, blank=False, null=False)
    - storage_id = models.CharField(max_length=255, blank=False, null=False)
    - storage_repo = models.CharField(max_length=255, blank=False, null=False)
    - storage_type = models.CharField(max_length=24, choices=STORAGE_TYPE_CHOICES, default=FABRIC)
    - uuid = models.CharField(primary_key=True, max_length=255, blank=False, null=False)
    """
    version_downloads = serializers.SerializerMethodField(method_name='get_version_downloads')
    created = serializers.SerializerMethodField(method_name='get_created')
    version = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    lookup_field = 'urn'

    class Meta:
        model = ArtifactVersion
        fields = ['active', 'created', 'urn', 'uuid', 'version', 'version_downloads', 'storage_type', 'source']

    def get_version(self, version) -> str:
        if version.storage_type == ArtifactVersion.GIT and artifact_visibility(version.artifact, self.context)[0]:
            return version.source_tag or version.storage_id
        return version.storage_id

    @extend_schema_field(GitHubSourceSerializer(allow_null=True))
    def get_source(self, version):
        if version.storage_type != ArtifactVersion.GIT or not artifact_visibility(version.artifact, self.context)[0]:
            return None
        return GitHubSourceSerializer({
            name: getattr(version, 'source_' + name)
            for name in ('repo', 'repo_id', 'tag', 'commit', 'url', 'release_name',
                         'published_at', 'trigger', 'prerelease')
        }).data

    @staticmethod
    def get_version_downloads(self) -> int:
        if hasattr(self, 'download_count'):
            return self.download_count
        return self.version_downloads.count()

    @staticmethod
    def get_created(self) -> str:
        return str(self.created.isoformat(' '))


class ArtifactVersionUpdateSerializer(serializers.ModelSerializer):
    """
    Artifact Version Update Serializer
    - artifact = models.ForeignKey(Artifact, on_delete=models.CASCADE, related_name="artifact_version")
    - created = models.DateTimeField(auto_now_add=True)
    - filename = models.CharField(max_length=255, blank=False, null=False)
    - storage_id = models.CharField(max_length=255, blank=False, null=False)
    - storage_repo = models.CharField(max_length=255, blank=False, null=False)
    - storage_type = models.CharField(max_length=24, choices=STORAGE_TYPE_CHOICES, default=FABRIC)
    - uuid = models.CharField(primary_key=True, max_length=255, blank=False, null=False)
    """
    lookup_field = 'uuid'

    class Meta:
        model = ArtifactVersion
        fields = ['active']
