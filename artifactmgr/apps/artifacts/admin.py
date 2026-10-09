"""Admin registration for artifact repository links."""

from django.contrib import admin

from artifactmgr.apps.artifacts.models import ArtifactRepoLink

admin.site.register(ArtifactRepoLink)
