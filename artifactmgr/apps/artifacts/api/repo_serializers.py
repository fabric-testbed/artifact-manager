"""JSON request and response schemas for GitHub links and release imports."""

from rest_framework import serializers

from artifactmgr.apps.artifacts.api.validators import validate_github_repository, validate_github_tag
from artifactmgr.apps.artifacts.models import ArtifactRepoLink


class RepoLinkRequestSerializer(serializers.Serializer):
    repository = serializers.CharField(max_length=255, trim_whitespace=False, validators=[validate_github_repository])


class ReleaseImportSerializer(serializers.Serializer):
    tag = serializers.CharField(max_length=128, trim_whitespace=False, validators=[validate_github_tag],
                                help_text='Git tag name (git check-ref-format rules), at most 128 characters.')


class RepoLinkSerializer(serializers.ModelSerializer):
    publishing_enabled = serializers.BooleanField(read_only=True)

    class Meta:
        model = ArtifactRepoLink
        fields = ['provider', 'repo_full_name', 'repo_id', 'repo_owner_id', 'html_url',
                  'linked_by', 'linked_at', 'publishing_enabled']
        read_only_fields = fields


class GitHubSourceSerializer(serializers.Serializer):
    repo = serializers.CharField()
    repo_id = serializers.CharField()
    tag = serializers.CharField()
    commit = serializers.CharField()
    url = serializers.URLField()
    release_name = serializers.CharField(allow_null=True)
    published_at = serializers.DateTimeField(allow_null=True)
    trigger = serializers.CharField()
    prerelease = serializers.BooleanField()


class GitHubReleaseSerializer(serializers.Serializer):
    """Published releases from the first 5 GitHub pages (at most 500 releases)."""

    tag_name = serializers.CharField()
    name = serializers.CharField(allow_null=True)
    html_url = serializers.URLField()
    published_at = serializers.DateTimeField(allow_null=True)
    prerelease = serializers.BooleanField()
    imported = serializers.BooleanField()
