from rest_framework import serializers

from artifactmgr.apps.artifacts.models import ArtifactAuthor


class AuthorSerializer(serializers.ModelSerializer):
    """
    ArtifactAuthor
    - affiliation = models.CharField(max_length=255, blank=False, null=False)
    - email = models.CharField(max_length=255, blank=True, null=True)
    - name = models.CharField(max_length=255, blank=False, null=False)
    - uuid = models.CharField(max_length=255, blank=False, null=False)
    """
    lookup_field = 'uuid'

    class Meta:
        model = ArtifactAuthor
        fields = ['affiliation', 'email', 'name', 'uuid']
