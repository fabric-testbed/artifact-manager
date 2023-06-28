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
from django.urls import path

from artifactmgr.apps.artifacts.views import author_list, author_detail, artifact_list, artifact_detail

urlpatterns = [
    path('', artifact_list, name='artifact_list'),
    path('<uuid>', artifact_detail, name='artifact_detail'),
    path('people/', author_list, name='author_list'),
    path('people/<uuid>', author_detail, name='author_detail'),
]
