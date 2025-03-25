from django.urls import path, include
from rest_framework_nested import routers
from core.views import LanguageViewSet
from organization.views import OrganizationViewSet

router = routers.DefaultRouter()
router.register('languages', LanguageViewSet, basename='languages')
router.register(r'organizations', OrganizationViewSet, basename='organizations')


urlpatterns = [
     path(r'', include(router.urls)),
]