from django.urls import path, include
from rest_framework_nested import routers
from core.views import LanguageViewSet
from organization.views import OrganizationViewSet, MemberViewSet, MemberInvitationViewSet
from human_resources.views import (
    DepartmentModelViewset, 
    PositionModelViewset, 
    EmployeeModelViewset, 
    AttendanceModelViewset, 
    EmployeeAttendanceStatsViewSet,
)

from api.views import notify_customers_view, refine_attendance_records_view, generate_attendance_reports_view


router = routers.DefaultRouter()
router.register('languages', LanguageViewSet, basename='languages')
router.register(r'organizations', OrganizationViewSet, basename='organizations')
member_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
member_router.register(r'members', MemberViewSet, basename='member')




invitation_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
invitation_router.register(r'invitations', MemberInvitationViewSet, basename='invitation')

department_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
department_router.register(r'departments', DepartmentModelViewset, basename='department')


position_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
position_router.register(r'positions', PositionModelViewset, basename='position')


employee_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
employee_router.register(r'employees', EmployeeModelViewset, basename='employee')


attendance_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
attendance_router.register(r'attendances', AttendanceModelViewset, basename='attendance')

employee_attendance_stats_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
employee_attendance_stats_router.register(r'employee-attendance-stats', EmployeeAttendanceStatsViewSet, basename='employee-attendance-stats')



urlpatterns = [
     path(r'', include(router.urls)),
     path(r'', include(member_router.urls)),
     path(r'', include(invitation_router.urls)),
     path(r'', include(department_router.urls)),
     path(r'', include(position_router.urls)),
     path(r'', include(employee_router.urls)),
     path(r'', include(attendance_router.urls)),
     path(r'', include(employee_attendance_stats_router.urls)),
     path(r'notify-customers/', notify_customers_view, name='notify-customers'),
     path(r'refine-attendance-records/', refine_attendance_records_view, name='refine-attendance-records'),
     path(r'generate-attendance-reports/', generate_attendance_reports_view, name='generate-attendance-reports'),
]