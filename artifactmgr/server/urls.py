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
from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from rest_framework import routers

from artifactmgr.apps.artifacts.api.artifact_viewsets import ArtifactViewSet
from artifactmgr.apps.artifacts.api.author_viewsets import AuthorViewSet
from artifactmgr.apps.artifacts.api.tag_viewsets import TagViewSet
from artifactmgr.apps.artifacts.api.version_viewsets import ArtifactVersionViewSet
from artifactmgr.server.views import landing_page

router = routers.DefaultRouter(trailing_slash=False)
router.register(r'authors', AuthorViewSet, basename='authors')
router.register(r'artifacts', ArtifactViewSet, basename='artifacts')
router.register(r'contents', ArtifactVersionViewSet, basename='contents')
router.register(r'meta/tags', TagViewSet, basename='tags')

# Wire up our API using automatic URL routing.
# Additionally, we include login URLs for the browsable API.
urlpatterns = [
    # path('', landing_page, name='home'),
    # path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('', include('artifactmgr.apps.artifacts.urls')),
    path('admin/', admin.site.urls),
    path('api/', include((router.urls, 'artifactmgr.apps.artifacts'))),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    # Optional UI:
    path('api/swagger/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
