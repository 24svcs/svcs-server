from django.urls import path, include
from rest_framework_nested import routers
from core.views import LanguageViewSet

router = routers.DefaultRouter()
router.register('languages', LanguageViewSet, basename='languages')


urlpatterns = [
     path(r'', include(router.urls)),
]