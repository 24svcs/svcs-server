from rest_framework.viewsets import ModelViewSet
from .serializers import(
     DepartmentSerializer, CreateDepartmentSerializer, Department,  UpdateDepartmentSerializer, CreatePositionSerializer, UpdatePositionSerializer, PositionSerializer, Position, CreateEmployeeSerializer, UpdateEmployeeSerializer, EmployeeSerializer, Employee

)
from core.mixins import TimezoneMixin
from django.utils.translation import gettext as _
from .serializers import CheckInOutSerializer, Attendance, AttendanceSerializer
from rest_framework.response import Response
from rest_framework import status
from .models import EmploymentDetails
from datetime import datetime, date, timedelta
from organization.models import Preference
import pytz
from django.core.cache import cache
from django_filters.rest_framework import DjangoFilterBackend
from .filters import AttendanceFilter, PositionFilter
from core.pagination import DefaultPagination

from rest_framework import  filters
from django_filters.rest_framework import DjangoFilterBackend
from django.utils import timezone as tz

from .serializers import EmployeeAttendanceStatsSerializer
from django.db import models
from .models import EmployeeAttendance
from rest_framework.viewsets import ReadOnlyModelViewSet


class DepartmentModelViewset(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name__istartswith']

    def get_queryset(self):
        return Department.objects.select_related('manager__employment_details__position').filter(organization_id=self.kwargs['organization_pk']).order_by('name')
    
    def get_serializer_class(self):
        if self.request.method in 'POST':
            return  CreateDepartmentSerializer
        elif self.request.method in ['PUT', 'PATCH']:
            return UpdateDepartmentSerializer
        return DepartmentSerializer
    
    def get_serializer_context(self):
        return {'organization_id': self.kwargs['organization_pk']}
    
    
    # def get_permissions(self):
    #     if self.request.method in ['HEAD', 'OPTIONS']:
    #         return [IsAuthenticated()]
    #     if  self.request.method in 'POST':
    #         return [IsAuthenticated(), OrganizationPermission(Permission.CREATE_ORGANIZATION_DEPARTMENT)]
    #     elif self.request.method in ['PUT', 'PATCH']:
    #         return [IsAuthenticated(), OrganizationPermission(Permission.EDIT_ORGANIZATION_DEPARTMENT)]
    #     elif self.request.method in 'DELETE':
    #         return [IsAuthenticated(), OrganizationPermission(Permission.DELETE_ORGANIZATION_DEPARTMENT)]
    #     return [IsAuthenticated(), OrganizationPermission(Permission.VIEW_ORGANIZATION_DEPARTMENT)]
    
    
    
    #Todo Working Solution
    # def perform_create(self, serializer):
    #     # Check if the user has the proper permission
    #     organization_id = self.kwargs['organization_pk']
        
    #     # Get the organization member for this user
    #     member = self.request.user.memberships.filter(
    #         organization_id=organization_id,
    #         status='ACTIVE'
    #     ).first()
        
    #     if not member or not member.permissions.filter(name=Permission.CREATE_ORGANIZATION_DEPARTMENT).exists():
    #         raise PermissionDenied(_("You don't have permission to create departments."))
        
        
        
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Check if there are any employees associated with this department
        has_employees = Position.objects.filter(
            department=instance, 
            id__in=EmploymentDetails.objects.values('position_id')
        ).exists()
        
        if has_employees:
            return Response(
                {"detail": _("Cannot delete department because it has employees associated with it. Please reassign these employees to another department first.")},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If no employees, proceed with deletion
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)



class PositionModelViewset(ModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['title__istartswith']
    filterset_class = PositionFilter
    def get_queryset(self):
        return Position.objects.select_related('department').filter(department__organization_id=self.kwargs['organization_pk']).order_by('title')
    
    def get_serializer_class(self):
        if self.request.method in 'POST':
            return CreatePositionSerializer
        elif self.request.method in ['PUT', 'PATCH']:
            return UpdatePositionSerializer
        return PositionSerializer
    
    def get_serializer_context(self):
        return {'organization_id': self.kwargs['organization_pk']}
    
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Check if there are any employees associated with this position
        has_employees = EmploymentDetails.objects.filter(position=instance).exists()
        
        if has_employees:
            return Response(
                {"detail": _("Cannot delete position because it has employees assigned to it. Please reassign these employees to another position first.")},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If no employees, proceed with deletion
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmployeeModelViewset(TimezoneMixin, ModelViewSet):
    
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['first_name__istartswith', 'last_name__istartswith', 'id__exact']

    def get_queryset(self):
        return Employee.objects.select_related('employment_details__position').filter(organization_id=self.kwargs['organization_pk']).order_by('first_name', 'last_name')
    
    def get_serializer_class(self):
        if self.request.method in 'POST':
            return CreateEmployeeSerializer
        elif self.request.method in ['PUT', 'PATCH']:
            return UpdateEmployeeSerializer
        return EmployeeSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context
    
    

class AttendanceModelViewset(TimezoneMixin, ModelViewSet):
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = AttendanceFilter
    pagination_class = DefaultPagination
    search_fields = ['employee__first_name__istartswith', 'employee__last_name__istartswith']
    
    def get_queryset(self):
        queryset = Attendance.objects.select_related('employee').filter(organization_id=self.kwargs['organization_pk']).order_by('date', '-time_in', '-time_out')
        
        # By default, filter to show only current date's attendance records
        if not self.request.query_params.get('date__gte') and not self.request.query_params.get('date__lte'):
            # Get organization timezone
            organization_timezone = self.get_organization_timezone()
            
            # Get current datetime in organization's timezone
            current_datetime = datetime.now(organization_timezone)
            today = current_datetime.date()
            
            # Convert today's date to UTC for filtering
            utc_today = current_datetime.astimezone(pytz.UTC).date()
            queryset = queryset.filter(date=utc_today)
        
        return queryset
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CheckInOutSerializer
        return AttendanceSerializer
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context
    
    def get_organization_timezone(self):
        """
        Get the organization's timezone from preferences.
        Uses caching to reduce database queries.
        """
        organization_id = self.kwargs['organization_pk']
        cache_key = f"org_timezone_{organization_id}"
        cached_timezone = cache.get(cache_key)
        
        if cached_timezone:
            return pytz.timezone(cached_timezone) if isinstance(cached_timezone, str) else cached_timezone
        
        try:
            org_preferences = Preference.objects.select_related('organization').get(
                organization_id=organization_id
            )
            organization_timezone = org_preferences.timezone
            
            # Convert to timezone object if it's a string
            if isinstance(organization_timezone, str):
                organization_timezone = pytz.timezone(organization_timezone)
            
            # Cache the timezone for 1 hour (3600 seconds)
            cache.set(cache_key, organization_timezone, 3600)
            
            return organization_timezone
        except Preference.DoesNotExist:
            # Default to UTC if preferences not found
            return pytz.UTC
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        attendance = serializer.save()
        
        # Get employee information
        employee = attendance.employee
        
        # Get position information if available
        position_title = None
        try:
            employment_details = EmploymentDetails.objects.select_related('position').get(employee=employee)
            if employment_details.position:
                position_title = employment_details.position.title
        except:
            pass
        
        # Calculate work duration if checked out
        work_duration = None
        if attendance.time_out:
            dummy_date = date(2000, 1, 1)
            dt_in = datetime.combine(dummy_date, attendance.time_in)
            dt_out = datetime.combine(dummy_date, attendance.time_out)
            
            if dt_out < dt_in:
                dt_out = datetime.combine(dummy_date + timedelta(days=1), attendance.time_out)
            
            duration_seconds = (dt_out - dt_in).total_seconds()
            hours = int(duration_seconds // 3600)
            minutes = int((duration_seconds % 3600) // 60)
            work_duration = f"{hours}h {minutes}m"
        
        # Get the organization's timezone
        organization_timezone = self.get_organization_timezone()
        
        # Convert UTC times to organization's timezone for display
        if attendance.time_in:
            utc_dt_in = datetime.combine(attendance.date, attendance.time_in)
            utc_dt_in = pytz.UTC.localize(utc_dt_in)
            local_dt_in = utc_dt_in.astimezone(organization_timezone)
            time_in_local = local_dt_in.strftime('%H:%M:%S')
        else:
            time_in_local = None
            
        if attendance.time_out:
            utc_dt_out = datetime.combine(attendance.date, attendance.time_out)
            utc_dt_out = pytz.UTC.localize(utc_dt_out)
            local_dt_out = utc_dt_out.astimezone(organization_timezone)
            time_out_local = local_dt_out.strftime('%H:%M:%S')
        else:
            time_out_local = None
        
        # Format the response
        response_data = {
            'id': str(attendance.id),
            'employee': {
                'id': str(employee.id),
                'name': f"{employee.first_name} {employee.last_name}",
                'position': position_title,
            },
            'attendance': {
                'date': attendance.date.strftime('%Y-%m-%d'),
                'time_in': time_in_local,
                'time_out': time_out_local,
                'status': attendance.status,
                'status_display': attendance.get_status_display() if hasattr(attendance, 'get_status_display') else attendance.status,
                'work_duration': work_duration,
                'note': attendance.note,
                'timezone': str(organization_timezone),
            },
            'action': 'check_out' if attendance.time_out else 'check_in',
            'message': _("Successfully checked out.") if attendance.time_out else _("Successfully checked in.")
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)


class EmployeeAttendanceStatsViewSet(TimezoneMixin, ReadOnlyModelViewSet):
    """
    ViewSet for retrieving employee attendance statistics.
    Provides aggregated statistics from EmployeeAttendance records.
    """
    serializer_class = EmployeeAttendanceStatsSerializer
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['first_name__istartswith', 'last_name__istartswith']

    def get_queryset(self):
        """
        Get queryset with proper eager loading and annotations for performance.
        """
        # Get current date for consecutive days calculation
        current_date = tz.now().date()
        
        queryset = Employee.objects.select_related(
            'employment_details__position__department'
        ).filter(
            organization_id=self.kwargs['organization_pk']
        )

        # Get date range from query params
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')

        # Base attendance filter
        attendance_filter = models.Q(employee_attendances__organization_id=self.kwargs['organization_pk'])
        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                attendance_filter &= models.Q(
                    employee_attendances__date__range=[start_date, end_date]
                )
            except ValueError:
                pass

        # Add all annotations in a single query
        queryset = queryset.annotate(
            # Basic counts
            total_days=models.Count(
                'employee_attendances',
                filter=attendance_filter,
                distinct=True
            ),
            present_days=models.Count(
                'employee_attendances',
                filter=attendance_filter & models.Q(employee_attendances__is_present=True),
                distinct=True
            ),
            absent_days=models.Count(
                'employee_attendances',
                filter=attendance_filter & models.Q(employee_attendances__is_absent=True),
                distinct=True
            ),
            late_days=models.Count(
                'employee_attendances',
                filter=attendance_filter & models.Q(employee_attendances__is_late=True),
                distinct=True
            ),
            perfect_attendance_days=models.Count(
                'employee_attendances',
                filter=attendance_filter & models.Q(
                    employee_attendances__is_present=True,
                    employee_attendances__is_late=False
                ),
                distinct=True
            ),
            # Aggregations
            total_late_minutes=models.Sum(
                'employee_attendances__late_minutes',
                filter=attendance_filter & models.Q(employee_attendances__is_late=True)
            ),
            total_working_hours=models.Sum(
                'employee_attendances__working_hours',
                filter=attendance_filter
            ),
            # Latest dates
            last_attendance_date=models.Max(
                'employee_attendances__date',
                filter=attendance_filter & models.Q(employee_attendances__is_present=True)
            ),
            last_absence_date=models.Max(
                'employee_attendances__date',
                filter=attendance_filter & models.Q(employee_attendances__is_absent=True)
            ),
            # Early leaves
            early_leaves=models.Count(
                'employee_attendances',
                filter=attendance_filter & models.Q(
                    employee_attendances__is_present=True,
                    employee_attendances__working_hours__lt=8
                ),
                distinct=True
            )
        ).order_by('first_name', 'last_name')

        return queryset

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context

    def list(self, request, *args, **kwargs):
        """
        Override list method to add date range filtering.
        """
        queryset = self.get_queryset()
        
        # Get date range from query params
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                # Filter employee_attendances for the date range
                queryset = queryset.annotate(
                    employee_attendances=models.Subquery(
                        EmployeeAttendance.objects.filter(
                            employee=models.OuterRef('pk'),
                            date__range=[start_date, end_date]
                        ).values('employee').annotate(
                            count=models.Count('id')
                        ).values('count')
                    )
                )
            except ValueError:
                pass
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        """
        Override retrieve method to add date range filtering for single employee.
        """
        instance = self.get_object()
        
        # Get date range from query params
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date and end_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                # Filter employee_attendances for the date range
                instance.employee_attendances = instance.employee_attendances.filter(
                    date__range=[start_date, end_date]
                )
            except ValueError:
                pass
        
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


