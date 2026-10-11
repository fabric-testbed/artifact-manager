"""
URL configuration for drf project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.urls import path, register_converter
from django.urls.converters import UUIDConverter

from artifactmgr.apps.artifacts.views import artifact_create, artifact_detail, artifact_list, artifact_update, \
    author_detail, author_list, project_detail, project_list


class UUIDStringConverter(UUIDConverter):
    """Match only canonical UUIDs at routing time, but hand the views the matched string."""

    def to_python(self, value):
        return value


register_converter(UUIDStringConverter, 'uuidstr')

urlpatterns = [
    path('', artifact_list, name='artifact_list'),
    path('create/', artifact_create, name='artifact_create'),
    path('<uuidstr:uuid>', artifact_detail, name='artifact_detail'),
    path('<uuidstr:uuid>/update', artifact_update, name='artifact_update'),
    path('authors/', author_list, name='author_list'),
    path('authors/<uuidstr:uuid>', author_detail, name='author_detail'),
    path('projects/', project_list, name='project_list'),
    path('projects/<uuidstr:uuid>', project_detail, name='project_detail'),
]
