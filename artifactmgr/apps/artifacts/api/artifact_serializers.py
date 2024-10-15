from rest_framework import serializers

from artifactmgr.apps.artifacts.api.author_serializers import AuthorSerializer
from artifactmgr.apps.artifacts.api.version_serializers import ArtifactVersionSerializer
from artifactmgr.apps.artifacts.models import Artifact, ArtifactVersion


class ArtifactSerializer(serializers.ModelSerializer):
    """
    Artifact Serializer
    - authors = models.ManyToManyField(ArtifactAuthor, related_name="artifact_authors")
    - created = models.DateTimeField(auto_now_add=True)
    - created_by = models.ForeignKey(ArtifactAuthor, ...)
    - deleted = models.BooleanField(default=False)
    - deleted_at = models.DateTimeField(blank=True, null=True)
    - description_long = models.TextField(max_length=5000, blank=False, null=False)
    - description_short = models.CharField(max_length=255, blank=True, null=True)
    - modified = models.DateTimeField(auto_now=True)
    - modified_by = models.ForeignKey(ArtifactAuthor, ...)
    - project_name = models.CharField(max_length=255, blank=True, null=True)
    - project_uuid = models.CharField(max_length=255, blank=True, null=True)
    - tags = models.ManyToManyField(ArtifactTag, related_name="artifact_tags", blank=True)
    - title = models.CharField(max_length=255, blank=False, null=False)
    - versions
    - visibility = models.CharField(max_length=24, choices=VISIBILITY_CHOICES, default=AUTHOR)
    - uuid = models.CharField(max_length=255, blank=False, null=False)
    """
    artifact_downloads_active = serializers.SerializerMethodField(method_name='get_artifact_downloads_active')
    artifact_downloads_retired = serializers.SerializerMethodField(method_name='get_artifact_downloads_retired')
    artifact_views = serializers.SerializerMethodField(method_name='get_artifact_views')
    authors = AuthorSerializer(many=True)
    created = serializers.SerializerMethodField(method_name='get_created')
    created_by = AuthorSerializer(instance='created_by')
    lookup_field = 'uuid'
    modified = serializers.SerializerMethodField(method_name='get_modified')
    modified_by = AuthorSerializer(instance='modified_by')
    number_of_versions = serializers.SerializerMethodField(method_name='get_number_of_versions')
    tags = serializers.SerializerMethodField(method_name='get_tags')
    versions = ArtifactVersionSerializer(source='artifact_version', many=True)

    class Meta:
        model = Artifact
        fields = ['artifact_downloads_active', 'artifact_downloads_retired', 'artifact_views', 'authors', 'created',
                  'created_by', 'deleted', 'deleted_at','description_long',
                  'description_short', 'modified', 'modified_by', 'number_of_versions', 'project_name',
                  'project_uuid', 'show_authors', 'show_project', 'tags', 'title', 'versions',
                  'visibility', 'uuid']

    @staticmethod
    def get_artifact_downloads_active(self) -> int:
        downloads = []
        versions = ArtifactVersion.objects.filter(
            artifact_id=self.uuid,
            active=True
        ).all()
        for version in versions:
            downloads.append(version.version_downloads.count())
        return sum(downloads)

    @staticmethod
    def get_artifact_downloads_retired(self) -> int:
        downloads = []
        versions = ArtifactVersion.objects.filter(
            artifact_id=self.uuid,
            active=False
        ).all()
        for version in versions:
            downloads.append(version.version_downloads.count())
        return sum(downloads)

    @staticmethod
    def get_artifact_views(self) -> int:
        return Artifact.objects.get(uuid=self.uuid).artifact_views.count()

    @staticmethod
    def get_created(self) -> str:
        return str(self.created.isoformat(' '))

    @staticmethod
    def get_modified(self) -> str:
        return str(self.modified.isoformat(' '))

    @staticmethod
    def get_number_of_versions(self) -> list:
        return ArtifactVersion.objects.filter(
            artifact_id=self.uuid,
            active=True
        ).count()

    @staticmethod
    def get_tags(self) -> list:
        return list(Artifact.objects.get(uuid=self.uuid).tags.values_list('tag', flat=True))


class ArtifactCreateSerializer(serializers.ModelSerializer):
    """
    Artifact Create Serializer
    - authors = models.ManyToManyField(ArtifactAuthor, related_name="artifact_authors")
    - description_long = models.TextField(max_length=5000, blank=False, null=False)
    - description_short = models.CharField(max_length=255, blank=True, null=True)
    - project_uuid = models.CharField(max_length=255, blank=True, null=True)
    - tags = models.ManyToManyField(ArtifactTag, related_name="artifact_tags", blank=True)
    - title = models.CharField(max_length=255, blank=False, null=False)
    - versions
    - visibility = models.CharField(max_length=24, choices=VISIBILITY_CHOICES, default=AUTHOR)
    """
    authors = AuthorSerializer(many=True)
    lookup_field = 'uuid'
    tags = serializers.SerializerMethodField(method_name='get_tags')

    class Meta:
        model = Artifact
        fields = ['authors', 'description_long', 'description_short', 'project_uuid', 'tags', 'title', 'visibility']

    @staticmethod
    def get_tags(self) -> list:
        return list(Artifact.objects.get(uuid=self.uuid).tags.values_list('tag', flat=True))


class ArtifactUpdateSerializer(serializers.ModelSerializer):
    """
    Artifact Create Serializer
    - authors = models.ManyToManyField(ArtifactAuthor, related_name="artifact_authors")
    - description_long = models.TextField(max_length=5000, blank=False, null=False)
    - description_short = models.CharField(max_length=255, blank=True, null=True)
    - project_uuid = models.CharField(max_length=255, blank=True, null=True)
    - tags = models.ManyToManyField(ArtifactTag, related_name="artifact_tags", blank=True)
    - title = models.CharField(max_length=255, blank=False, null=False)
    - visibility = models.CharField(max_length=24, choices=VISIBILITY_CHOICES, default=AUTHOR)
    """
    authors = AuthorSerializer(many=True)
    lookup_field = 'uuid'
    tags = serializers.SerializerMethodField(method_name='get_tags')

    class Meta:
        model = Artifact
        fields = ['authors', 'description_long', 'description_short', 'project_uuid', 'tags', 'title', 'visibility']

    @staticmethod
    def get_tags(self) -> list:
        return list(Artifact.objects.get(uuid=self.uuid).tags.values_list('tag', flat=True))
