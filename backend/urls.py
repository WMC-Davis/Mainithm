from django.urls import path, include
from backend import views
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register('latency', views.LatencyViewSet, basename='latency')

urlpatterns = [
    path('api/', include(router.urls)),
]
