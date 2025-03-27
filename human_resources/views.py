from rest_framework.viewsets import ModelViewSet
from .serializers import(
     DepartmentSerializer, CreateDepartmentSerializer, Department,  UpdateDepartmentSerializer, CreatePositionSerializer, UpdatePositionSerializer, PositionSerializer, Position, CreateEmployeeSerializer, UpdateEmployeeSerializer, EmployeeSerializer, Employee

)
from core.mixins import TimezoneMixin
from core.models import Permission
from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied
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
from rest_framework.views import APIView
from django.db.models import Count, Q

from .utils.statistics_calculator import StatisticsCalculator
from .serializers import EmployeeAttendanceStatsSerializer
from django.db import models
    
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
        queryset = Attendance.objects.select_related('employee').filter(organization_id=self.kwargs['organization_pk'])
        
        # By default, filter to show only current date's attendance records
        if not self.request.query_params.get('date__gte') and not self.request.query_params.get('date__lte'):
            # Get organization timezone
            organization_timezone = self.get_organization_timezone()

            
            # Get current datetime in organization's timezone
            current_datetime = datetime.now(organization_timezone)
            today = current_datetime.date()
            
            queryset = queryset.filter(date=today)
        
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
        
        # Get the organization's timezone from preferences
        organization_timezone = self.get_organization_timezone()
        
        # Format times in the organization's timezone
        from django.utils import timezone as tz
        
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
                'time_in': attendance.time_in.strftime('%H:%M:%S'),
                'time_out': attendance.time_out.strftime('%H:%M:%S') if attendance.time_out else None,
                'status': attendance.status,
                'status_display': attendance.get_status_display() if hasattr(attendance, 'get_status_display') else attendance.status,
                'work_duration': work_duration,
                'note': attendance.note,
                'timezone': str(organization_timezone),  # Include timezone info in response
            },
            'action': 'check_out' if attendance.time_out else 'check_in',
            'message': _("Successfully checked out.") if attendance.time_out else _("Successfully checked in.")
        }
        
        return Response(response_data, status=status.HTTP_201_CREATED)



# Attendance Reports
class BaseAttendanceReportView(APIView):
    """Base class for attendance report views with common functionality."""
    
    def get_date_range(self, request):
        """
        Get and validate date range from request parameters.
        Returns (start_date, end_date) tuple if valid, or None, None if not specified/invalid.
        """
        start_date_param = request.query_params.get('start_date', '')
        end_date_param = request.query_params.get('end_date', '')

        # Handle null, undefined, or empty string cases
        if not start_date_param or start_date_param.lower() in ['null', 'undefined', '']:
            start_date_param = None
        if not end_date_param or end_date_param.lower() in ['null', 'undefined', '']:
            end_date_param = None

        # If no valid dates provided, return None to skip date filtering
        if start_date_param is None and end_date_param is None:
            return None, None

        try:
            # Parse dates if provided
            start_date = datetime.fromisoformat(start_date_param).date() if start_date_param else None
            end_date = datetime.fromisoformat(end_date_param).date() if end_date_param else None

            # Validate date range if both dates are provided
            if start_date and end_date and start_date > end_date:
                return Response(
                    {"error": "Start date cannot be after end date."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return start_date, end_date

        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
    def get_filtered_queryset(self, organization_pk, start_date, end_date, department_id=None):
        """
        Get filtered queryset based on date range and department.
        Date filtering is only applied if both dates are provided.
        """
        queryset = Attendance.objects.select_related(
            'employee',
            'employee__employment_details',
            'employee__employment_details__position',
            'employee__employment_details__position__department'
        ).filter(organization_id=organization_pk)
        
        # Only apply date filtering if both dates are provided and not None
        if start_date is not None and end_date is not None:
            queryset = queryset.filter(
            date__gte=start_date,
            date__lte=end_date
        )
        
        if department_id:
            queryset = queryset.filter(
                employee__employment_details__position__department_id=department_id
            )
        
        return queryset
    
    def get_employees_queryset(self, organization_pk, start_date, end_date, department_id=None):
        """
        Get all employees in the organization, regardless of attendance records.
        """
        employees_queryset = Employee.objects.select_related(
            'employment_details',
            'employment_details__position',
            'employment_details__position__department'
        ).filter(organization_id=organization_pk)

        if department_id:
            employees_queryset = employees_queryset.filter(
                employment_details__position__department_id=department_id
            )
        
        return employees_queryset.distinct()
    
    def calculate_working_days(self, start_date, end_date, days_off):
        """
        Calculate working days between two dates, excluding specified days off.
        Returns 0 if either date is None.
        """
        # Return 0 if either date is None
        if start_date is None or end_date is None:
            return 0
        
        # This method is already optimized
        working_days = 0
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime('%A').upper()
            if day_name not in days_off:
                working_days += 1
            current_date += timedelta(days=1)
        return working_days


class EmployeeAttendanceReportView(BaseAttendanceReportView):
    """
    Generate attendance reports for individual employees with attendance scoring.
    Includes pagination for handling large employee datasets.
    """
    pagination_class = DefaultPagination
    
    def _load_attendance_records(self, attendance_queryset, start_date, end_date):
        """
        Load and map attendance records by employee ID.
        """
        employee_attendance_map = {}
        base_attendance_query = attendance_queryset
        
        # Only apply date filtering if both dates are provided
        if start_date is not None and end_date is not None:
            base_attendance_query = base_attendance_query.filter(
                date__gte=start_date,
                date__lte=end_date
            )
        
        for attendance in base_attendance_query:
            if attendance.employee_id not in employee_attendance_map:
                employee_attendance_map[attendance.employee_id] = []
            employee_attendance_map[attendance.employee_id].append(attendance)
            
        return employee_attendance_map
    
    def _generate_paginated_response(self, employee_stats, start_date, end_date, request):
        """
        Generate paginated response with report data.
        """
        paginator = self.pagination_class()
        paginated_stats = paginator.paginate_queryset(employee_stats, request)
        
        # Calculate total days in the period
        total_days = (end_date - start_date).days + 1 if start_date and end_date else None
        
        # Generate the report with paginated data
        report = {
            'report_period': {
                'start_date': start_date.isoformat() if start_date else None,
                'end_date': end_date.isoformat() if end_date else None,
                'total_days': total_days,
            },
            'employee_statistics': paginated_stats,
        }
        
        return paginator.get_paginated_response(report)
    
    def get(self, request, organization_pk):
        # Get date range and department filter
        date_range = self.get_date_range(request)
        if isinstance(date_range, Response):  # Error occurred
            return date_range
        
        start_date, end_date = date_range
        department_id = request.query_params.get('department_id')
        
        # Get filtered querysets with eager loading
        attendance_queryset = self.get_filtered_queryset(
            organization_pk, start_date, end_date, department_id)
        employees_queryset = self.get_employees_queryset(
            organization_pk, start_date, end_date, department_id)
        
        # Load attendance records
        employee_attendance_map = self._load_attendance_records(
            attendance_queryset, start_date, end_date)
        
        # Calculate statistics for each employee
        employee_stats = [
            StatisticsCalculator.calculate_employee_statistics(
                employee,
                employee_attendance_map.get(employee.id, []),
                start_date,
                end_date
            )
            for employee in employees_queryset
        ]
        
        # Paginate and return response
        return self._generate_paginated_response(
            employee_stats, start_date, end_date, request)

class EmployeeAttendanceStatsViewSet(ModelViewSet):
    """
    ViewSet for managing employee attendance statistics.
    Provides detailed attendance statistics for employees.
    """
    serializer_class = EmployeeAttendanceStatsSerializer
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['employee__first_name__istartswith', 'employee__last_name__istartswith']

    def get_queryset(self):
        """
        Get queryset of employees with their attendance statistics.
        Filters by organization and optionally by department.
        """
        queryset = Employee.objects.select_related(
            'employment_details',
            'employment_details__position',
            'employment_details__position__department'
        ).filter(organization_id=self.kwargs['organization_pk'])

        # Filter by department if specified
        department_id = self.request.query_params.get('department_id')
        if department_id:
            queryset = queryset.filter(
                employment_details__position__department_id=department_id
            )

        # Filter by date range if specified
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        
        if start_date and end_date:
            try:
                start_date = datetime.fromisoformat(start_date).date()
                end_date = datetime.fromisoformat(end_date).date()
                
                # Filter employee_attendances by date range
                queryset = queryset.filter(
                    employee_attendances__date__gte=start_date,
                    employee_attendances__date__lte=end_date
                ).distinct()
            except ValueError:
                pass  # Invalid date format, ignore the filter

        return queryset.order_by('first_name', 'last_name')

    def get_serializer_context(self):
        """
        Add organization_id to serializer context.
        """
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context

    def list(self, request, *args, **kwargs):
        """
        Override list method to include summary statistics.
        """
        queryset = self.get_queryset()
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        
        # Calculate summary statistics
        total_employees = queryset.count()
        total_attendance = queryset.aggregate(
            total_present=models.Count('employee_attendances', filter=models.Q(employee_attendances__is_present=True)),
            total_absent=models.Count('employee_attendances', filter=models.Q(employee_attendances__is_absent=True)),
            total_late=models.Count('employee_attendances', filter=models.Q(employee_attendances__is_late=True)),
            total_working_hours=models.Sum('employee_attendances__working_hours'),
            total_late_minutes=models.Sum('employee_attendances__late_minutes')
        )

        response_data = {
            'summary': {
                'total_employees': total_employees,
                'total_present_days': total_attendance['total_present'] or 0,
                'total_absent_days': total_attendance['total_absent'] or 0,
                'total_late_days': total_attendance['total_late'] or 0,
                'total_working_hours': total_attendance['total_working_hours'] or 0,
                'total_late_minutes': total_attendance['total_late_minutes'] or 0,
                'average_attendance_rate': round(
                    (total_attendance['total_present'] / 
                     (total_attendance['total_present'] + total_attendance['total_absent'])) * 100
                    if (total_attendance['total_present'] + total_attendance['total_absent']) > 0
                    else 0,
                    2
                )
            },
            'results': serializer.data
        }
        
        return Response(response_data)

    def retrieve(self, request, *args, **kwargs):
        """
        Override retrieve method to include detailed statistics for a single employee.
        """
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        # Get date range from query params if specified
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if start_date and end_date:
            try:
                start_date = datetime.fromisoformat(start_date).date()
                end_date = datetime.fromisoformat(end_date).date()
                
                # Get attendance records for the date range
                attendance_records = instance.employee_attendances.filter(
                    date__gte=start_date,
                    date__lte=end_date
                )
            except ValueError:
                attendance_records = instance.employee_attendances.all()
        else:
            attendance_records = instance.employee_attendances.all()
        
        # Calculate additional statistics
        attendance_stats = {
            'attendance_records': {
                'total': attendance_records.count(),
                'present': attendance_records.filter(is_present=True).count(),
                'absent': attendance_records.filter(is_absent=True).count(),
                'late': attendance_records.filter(is_late=True).count(),
                'working_hours': attendance_records.aggregate(
                    total=models.Sum('working_hours')
                )['total'] or 0,
                'late_minutes': attendance_records.aggregate(
                    total=models.Sum('late_minutes')
                )['total'] or 0
            }
        }
        
        response_data = {
            **serializer.data,
            'detailed_stats': attendance_stats
        }
        
        return Response(response_data)

