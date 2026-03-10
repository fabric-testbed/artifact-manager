from django.db import models

from artifactmgr.apps.apiuser.models import ApiUser


class LowerCaseField(models.CharField):

    def get_prep_value(self, value):
        return str(value).lower()


class ArtifactAuthor(models.Model):
    """
    ArtifactAuthor
    - Author data is retrieved from core-api FabricPeople model by uuid
    """
    affiliation = models.CharField(max_length=255, blank=False, null=False)
    email = models.CharField(max_length=255, blank=True, null=True)
    name = models.CharField(max_length=255, blank=False, null=False)
    updated = models.DateTimeField(auto_now_add=True)
    uuid = models.CharField(primary_key=True, max_length=255, blank=False, null=False)

    # Order by name
    class Meta:
        ordering = ("name",)

    def __str__(self):
        display = self.name
        if self.affiliation:
            display += " ({0})".format(self.affiliation)
        return display


class ArtifactTag(models.Model):
    """
    Represents artifact tags
    - tag - arbitrary string
    - restricted - tag can only be applied by amgr-admins
    """
    tag = LowerCaseField(primary_key=True, max_length=255, blank=False, null=False)
    restricted = models.BooleanField(default=False)

    class Meta:
        ordering = ("tag",)

    def __str__(self):
        return self.tag


class ArtifactViews(models.Model):
    """
    ArtifactViews
    - viewed_at - datetime in UTC
    - viewed_by - APIUser UUID reference
    """
    viewed_at = models.DateTimeField(auto_now_add=True)
    viewed_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ("viewed_at",)


class Artifact(models.Model):
    """
    FABRIC Artifact
    - Arbitrary collection of files related to a FABRIC project
    """
    AUTHOR = "author"
    PROJECT = "project"
    PUBLIC = "public"
    VISIBILITY_CHOICES = (
        (AUTHOR, "Author"),
        (PROJECT, "Project"),
        (PUBLIC, "Public"),
    )
    artifact_views = models.ManyToManyField(ArtifactViews, related_name="artifact_views")
    authors = models.ManyToManyField(ArtifactAuthor, related_name='artifact_author')
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        ArtifactAuthor,
        related_name='artifact_created_by',
        null=True,
        on_delete=models.CASCADE,
    )
    deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(blank=True, null=True)
    description_long = models.TextField(max_length=5000, blank=False, null=False)
    description_short = models.CharField(max_length=255, blank=True, null=True)
    modified = models.DateTimeField()
    modified_by = models.ForeignKey(
        ArtifactAuthor,
        related_name='artifact_modified_by',
        null=True,
        on_delete=models.CASCADE
    )
    project_name = models.CharField(max_length=255, blank=True, null=True)
    project_uuid = models.CharField(max_length=255, blank=True, null=True)
    show_authors = models.BooleanField(default=True)
    show_project = models.BooleanField(default=True)
    tags = models.ManyToManyField(ArtifactTag, related_name="artifact_tags", blank=True)
    title = models.CharField(max_length=255, blank=False, null=False)
    visibility = models.CharField(
        max_length=24, choices=VISIBILITY_CHOICES, default=AUTHOR
    )
    uuid = models.CharField(primary_key=True, max_length=255, blank=False, null=False)

    class Meta:
        ordering = ("title",)

    def __str__(self):
        return self.title

    def is_author(self, api_user_uuid: str) -> bool:
        return api_user_uuid in [a.uuid for a in self.authors.all()]


class VersionDownloads(models.Model):
    """
    ArtifactDownloads
    - downloaded_at - datetime in UTC
    - downloaded_by - APIUser UUID reference
    """
    downloaded_at = models.DateTimeField(auto_now_add=True)
    downloaded_by = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ("downloaded_at",)


class ArtifactVersion(models.Model):
    """
    ArtifactVersion
    - contents and metadata for a particular collection of artifact files
    """
    FABRIC = "fabric"
    GIT = "git"
    ZENODO = "zenodo"
    STORAGE_TYPE_CHOICES = (
        (FABRIC, "FABRIC"),
        (GIT, "Git"),
        (ZENODO, "Zenodo"),
    )
    active = models.BooleanField(default=True)
    artifact = models.ForeignKey(
        Artifact, on_delete=models.CASCADE, related_name="artifact_version"
    )
    created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        ArtifactAuthor,
        related_name='version_created_by',
        null=True,
        on_delete=models.CASCADE,
    )
    filename = models.CharField(max_length=255, blank=False, null=False)
    storage_id = models.CharField(max_length=255, blank=False, null=False)
    storage_repo = models.CharField(max_length=255, blank=False, null=False)
    storage_type = models.CharField(
        max_length=24, choices=STORAGE_TYPE_CHOICES, default=FABRIC
    )
    uuid = models.CharField(primary_key=True, max_length=255, blank=False, null=False)
    version_downloads = models.ManyToManyField(VersionDownloads, related_name="version_downloads")

    def __str__(self):
        return f"{self.artifact.title} ({self.created})"

    @property
    def urn(self) -> str:
        return 'urn:{0}:contents:{1}:{2}'.format(self.storage_type, self.storage_repo, self.uuid)

    class Meta:
        ordering = ('-created',)
