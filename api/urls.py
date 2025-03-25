from django.urls import path, include
from rest_framework_nested import routers
from core.views import LanguageViewSet
from organization.views import OrganizationViewSet, MemberViewSet, MemberInvitationViewSet

router = routers.DefaultRouter()
router.register('languages', LanguageViewSet, basename='languages')
router.register(r'organizations', OrganizationViewSet, basename='organizations')
member_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
member_router.register(r'members', MemberViewSet, basename='member')

invitation_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
invitation_router.register(r'invitations', MemberInvitationViewSet, basename='invitation')


urlpatterns = [
     path(r'', include(router.urls)),
     path(r'', include(member_router.urls)),
     path(r'', include(invitation_router.urls)),
]