import os
from datetime import datetime, timedelta, timezone

from django.contrib.postgres.fields import ArrayField
from django.db import models


class LowerCaseField(models.CharField):

    def get_prep_value(self, value):
        return str(value).lower()


class ApiUser(models.Model):
    """
    ApiUser
    - FABRIC user or Anonymous user as set by fabric cookie or token
    """
    COOKIE = "cookie"
    TOKEN = "token"
    ACCESS_TYPE_CHOICES = (
        (COOKIE, "Cookie"),
        (TOKEN, "Token"),
    )
    access_expires = models.DateTimeField(blank=True, null=True)
    access_type = models.CharField(
        max_length=24, choices=ACCESS_TYPE_CHOICES, default=COOKIE
    )
    affiliation = models.CharField(max_length=255, blank=True, null=True)
    cilogon_id = models.CharField(max_length=255, blank=False, null=False)
    email = models.CharField(max_length=255, blank=True, null=True)
    fabric_roles = ArrayField(models.CharField(max_length=255, blank=True))
    name = models.CharField(max_length=255, blank=True, null=True)
    projects = ArrayField(models.CharField(max_length=255, blank=True))
    uuid = models.CharField(primary_key=True, max_length=255, blank=False, null=False)

    @property
    def can_create_artifact(self):
        return os.getenv('CAN_CREATE_ARTIFACT_ROLE') in self.fabric_roles

    @property
    def can_create_tag(self):
        return os.getenv('CAN_CREATE_TAGS_ROLE') in self.fabric_roles

    @property
    def is_authenticated(self):
        return self.uuid != os.getenv('API_USER_ANON_UUID')

    def is_project_member(self, project_uuid: str) -> bool:
        return project_uuid in self.projects

    def as_dict(self):
        return {
            'access_expires': str(self.access_expires),
            'access_type': self.access_type,
            'affiliation': self.affiliation,
            'can_create_artifact': self.can_create_artifact,
            'can_create_tag': self.can_create_tag,
            'cilogon_id': self.cilogon_id,
            'email': self.email,
            'fabric_roles': self.fabric_roles,
            'is_authenticated': self.is_authenticated,
            'name': self.name,
            'projects': self.projects,
            'uuid': self.uuid
        }

    def __str__(self):
        return self.uuid


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
    """
    tag = LowerCaseField(primary_key=True, max_length=255, blank=False, null=False)

    class Meta:
        ordering = ("tag",)

    def __str__(self):
        return self.tag


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
    modified = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(
        ArtifactAuthor,
        related_name='artifact_modified_by',
        null=True,
        on_delete=models.CASCADE
    )
    project_name = models.CharField(max_length=255, blank=True, null=True)
    project_uuid = models.CharField(max_length=255, blank=True, null=True)
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

    def __str__(self):
        return f"{self.artifact.title} ({self.created})"

    @property
    def urn(self) -> str:
        return 'urn:{0}:contents:{1}:{2}'.format(self.storage_type, self.storage_repo, self.uuid)

    class Meta:
        ordering = ('-created',)


class TaskTimeoutTracker(models.Model):
    """
    Task Timeout Tracker
    - description
    - last_updated
    - name
    - timeout_in_seconds
    - uuid
    - value
    """
    description = models.CharField(max_length=255, blank=True, null=True)
    last_updated = models.DateTimeField(blank=False, null=False)
    name = models.CharField(max_length=255, blank=False, null=False)
    timeout_in_seconds = models.IntegerField(default=0, blank=False, null=False)
    uuid = models.CharField(primary_key=True, max_length=255, blank=False, null=False)
    value = models.TextField(blank=True, null=True)

    # Order by name
    class Meta:
        db_table = "task_timeout_tracker"
        ordering = ("name",)

    def __str__(self):
        return self.name

    def timed_out(self) -> bool:
        if datetime.now(timezone.utc) > (self.last_updated + timedelta(seconds=int(self.timeout_in_seconds))):
            return True
        else:
            return False
