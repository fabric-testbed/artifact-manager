from rest_framework import serializers

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
    created = serializers.SerializerMethodField(method_name='get_created')
    version = serializers.CharField(source='storage_id')
    lookup_field = 'urn'

    class Meta:
        model = ArtifactVersion
        fields = ['active', 'created', 'urn', 'uuid', 'version']

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
