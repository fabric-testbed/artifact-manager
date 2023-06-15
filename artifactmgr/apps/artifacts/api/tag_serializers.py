from rest_framework import serializers

from artifactmgr.apps.artifacts.models import ArtifactTag


class TagSerializer(serializers.ModelSerializer):
    """
    Tag
    - tag = models.CharField(max_length=255, blank=False, null=False)
    """

    class Meta:
        model = ArtifactTag
        fields = ['tag']
