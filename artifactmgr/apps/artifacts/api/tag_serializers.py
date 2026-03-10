from rest_framework import serializers

from artifactmgr.apps.artifacts.models import ArtifactTag


class TagSerializer(serializers.ModelSerializer):
    """
    Tag
    - tag = models.CharField(max_length=255, blank=False, null=False)
    - restricted = models.BooleanField(default=False)
    """

    class Meta:
        model = ArtifactTag
        fields = ['tag', 'restricted']


class TagUpdateSerializer(serializers.ModelSerializer):
    """
    Tag
    - tag = models.CharField(max_length=255, blank=False, null=False)
    - restricted = models.BooleanField(default=False)
    """

    class Meta:
        model = ArtifactTag
        fields = ['restricted']
