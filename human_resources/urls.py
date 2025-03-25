from django.urls import path, include
from rest_framework_nested import routers
from . import views

router = routers.DefaultRouter()
router.register('', views.OrganizationViewSet, basename='organization')

# Nested routes for departments
organizations_router = routers.NestedDefaultRouter(router, '', lookup='organization')
organizations_router.register('departments', views.DepartmentModelViewset, basename='organization-departments')
organizations_router.register('positions', views.PositionModelViewset, basename='organization-positions')
organizations_router.register('employees', views.EmployeeModelViewset, basename='organization-employees')
organizations_router.register('attendance', views.AttendanceModelViewset, basename='organization-attendance')

urlpatterns = [
    path('', include(router.urls)),
    path('', include(organizations_router.urls)),
    path('organizations/<str:organization_pk>/attendance-report/', views.AttendanceReportView.as_view(), name='organization-attendance-report'),
] 