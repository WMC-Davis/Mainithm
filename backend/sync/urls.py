from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r'maimai/songs', views.MaimaiSongViewSet)
router.register(r'chunithm/songs', views.ChunithmSongViewSet)
router.register(r'delays', views.DelayDifferenceViewSet)

urlpatterns = [
    path('ping/', views.ping),
    path('', include(router.urls)),
]
