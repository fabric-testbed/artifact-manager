import os
from datetime import datetime, timedelta, timezone

from django.contrib.postgres.fields import ArrayField
from django.db import models


# Create your models here.
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
    uuid = models.CharField(primary_key=False, max_length=255, blank=False)

    @property
    def can_create_artifact(self):
        return os.getenv('CAN_CREATE_ARTIFACT_ROLE') in self.fabric_roles

    @property
    def is_artifact_manager_admin(self):
        return os.getenv('ARTIFACT_MANAGER_ADMINS_ROLE') in self.fabric_roles

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
            'cilogon_id': self.cilogon_id,
            'email': self.email,
            'fabric_roles': self.fabric_roles,
            'is_artifact_manager_admin': self.is_artifact_manager_admin,
            'is_authenticated': self.is_authenticated,
            'name': self.name,
            'projects': self.projects,
            'uuid': self.uuid
        }

    def __str__(self):
        return self.uuid


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
