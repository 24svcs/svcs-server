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
from django.db.models import Count, Sum, F, ExpressionWrapper, DurationField, Avg, Q
from django.db.models.functions import Extract
from django.utils import timezone
    
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
            return cached_timezone
        
        try:
            org_preferences = Preference.objects.select_related('organization').get(
                organization_id=organization_id
            )
            organization_timezone = org_preferences.timezone
            
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

class AttendanceReportView(TimezoneMixin, APIView):
    """
    Generate a comprehensive attendance report for employees in an organization.
    
    This report includes statistics on attendance patterns, including:
    - Total working days
    - Total days present
    - Total days absent
    - Total late arrivals
    - Average working hours
    - Total minutes late
    
    The report can be filtered by date range and department.
    """
    
    def get(self, request, organization_pk):
        # Get date range from request params (default to current month)
        today = timezone.now().date()
        start_date = request.query_params.get('start_date', today.replace(day=1).isoformat())
        end_date = request.query_params.get('end_date', today.isoformat())
        department_id = request.query_params.get('department_id')
        
        # Convert string dates to date objects
        try:
            start_date = datetime.fromisoformat(start_date).date()
            end_date = datetime.fromisoformat(end_date).date()
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # Initial queryset - filter by organization and date range
        queryset = Attendance.objects.filter(
            organization_id=organization_pk,
            date__gte=start_date,
            date__lte=end_date
        )
        
        # Filter by department if provided
        if department_id:
            queryset = queryset.filter(
                employee__employment_details__position__department_id=department_id
            )
        
        # Get all employees from the filtered department (or all)
        employees_queryset = Employee.objects.filter(organization_id=organization_pk)
        if department_id:
            employees_queryset = employees_queryset.filter(
                employment_details__position__department_id=department_id
            )
        
        # Calculate total days in the period (include all days)
        total_days = (end_date - start_date).days + 1
        
        # Employee-specific statistics
        employee_stats = []
        
        for employee in employees_queryset:
            employee_attendance = queryset.filter(employee=employee)
            
            # Get employment details for shift times and days off
            try:
                employment_details = EmploymentDetails.objects.get(employee=employee)
                shift_start = employment_details.shift_start
                days_off = employment_details.days_off or []  # Get employee's days off, default to empty list
                department = employment_details.position.department.name if employment_details.position and employment_details.position.department else "N/A"
                position = employment_details.position.title if employment_details.position else "N/A"
            except EmploymentDetails.DoesNotExist:
                shift_start = None
                days_off = []
                department = "N/A"
                position = "N/A"
            
            # Calculate individual working days (excluding their days off)
            employee_working_days = 0
            current_date = start_date
            while current_date <= end_date:
                day_name = current_date.strftime('%A').upper()  # Get day name (e.g., 'MONDAY')
                if day_name not in days_off:  # If not a day off for this employee
                    employee_working_days += 1
                current_date += timedelta(days=1)
            
            # Calculate individual statistics
            days_present = employee_attendance.exclude(status=Attendance.ATTENDANCE_ABSENT).count()
            days_absent = employee_attendance.filter(status=Attendance.ATTENDANCE_ABSENT).count()
            days_late = employee_attendance.filter(status=Attendance.ATTENDANCE_LATE).count()
            
            # Calculate minutes late
            total_minutes_late = 0
            if shift_start:
                for attendance in employee_attendance.filter(status=Attendance.ATTENDANCE_LATE):
                    time_in = datetime.combine(date.today(), attendance.time_in)
                    expected_time = datetime.combine(date.today(), shift_start)
                    
                    # Add 15-minute grace period
                    expected_time = expected_time + timedelta(minutes=15)
                    
                    if time_in > expected_time:
                        minutes_late = (time_in - expected_time).total_seconds() / 60
                        total_minutes_late += minutes_late
            
            # Calculate average working hours
            avg_working_hours = 0
            count_with_complete_hours = 0
            
            for attendance in employee_attendance.filter(time_out__isnull=False):
                time_in = datetime.combine(date.today(), attendance.time_in)
                time_out = datetime.combine(date.today(), attendance.time_out)
                
                # Handle overnight shifts
                if time_out < time_in:
                    time_out = datetime.combine(date.today() + timedelta(days=1), attendance.time_out)
                
                working_hours = (time_out - time_in).total_seconds() / 3600
                avg_working_hours += working_hours
                count_with_complete_hours += 1
            
            avg_working_hours = round(avg_working_hours / count_with_complete_hours, 2) if count_with_complete_hours > 0 else 0
            
            # Use employee_working_days instead of working_days for percentage
            attendance_percentage = round((days_present / employee_working_days) * 100, 2) if employee_working_days > 0 else 0
            
            employee_stats.append({
                'id': employee.id,
                'name': f"{employee.first_name} {employee.last_name}",
                'department': department,
                'position': position,
                'days_present': days_present,
                'days_absent': days_absent,
                'days_late': days_late,
                'total_minutes_late': round(total_minutes_late, 2),
                'average_working_hours': avg_working_hours,
                'total_working_days': employee_working_days,  # Add this field to show employee-specific working days
                'attendance_percentage': attendance_percentage
            })
        
        # Calculate department-wise statistics if not filtered by department
        department_stats = []
        if not department_id:
            departments = Department.objects.filter(organization_id=organization_pk)
            
            for dept in departments:
                dept_employees = employees_queryset.filter(
                    employment_details__position__department=dept
                )
                
                dept_attendance = queryset.filter(
                    employee__employment_details__position__department=dept
                )
                
                dept_employee_count = dept_employees.count()
                dept_days_present = dept_attendance.exclude(status=Attendance.ATTENDANCE_ABSENT).count()
                dept_days_absent = dept_attendance.filter(status=Attendance.ATTENDANCE_ABSENT).count()
                dept_days_late = dept_attendance.filter(status=Attendance.ATTENDANCE_LATE).count()
                
                dept_total_working_days = 0  # Initialize total working days for department
                
                # Calculate working days for each employee in this department
                for employee in dept_employees:
                    try:
                        days_off = employee.employment_details.days_off or []
                    except (AttributeError, EmploymentDetails.DoesNotExist):
                        days_off = []
                    
                    # Count working days for this employee
                    employee_working_days = 0
                    current_date = start_date
                    while current_date <= end_date:
                        day_name = current_date.strftime('%A').upper()
                        if day_name not in days_off:
                            employee_working_days += 1
                        current_date += timedelta(days=1)
                    
                    dept_total_working_days += employee_working_days
                
                # Calculate department statistics using the summed working days
                dept_attendance_percentage = round((dept_days_present / dept_total_working_days) * 100, 2) if dept_total_working_days > 0 else 0
                
                department_stats.append({
                    'id': dept.id,
                    'name': dept.name,
                    'employee_count': dept_employee_count,
                    'days_present': dept_days_present,
                    'days_absent': dept_days_absent,
                    'days_late': dept_days_late,
                    'attendance_percentage': dept_attendance_percentage
                })
        
        # Generate the report
        report = {
            'report_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_days': total_days,
            },
            'overall_statistics': {
                'total_employees': employees_queryset.count(),
                'total_attendance_records': queryset.count(),
                'total_present': queryset.exclude(status=Attendance.ATTENDANCE_ABSENT).count(),
                'total_absent': queryset.filter(status=Attendance.ATTENDANCE_ABSENT).count(),
                'total_late': queryset.filter(status=Attendance.ATTENDANCE_LATE).count(),
                'average_attendance_percentage': round((queryset.exclude(status=Attendance.ATTENDANCE_ABSENT).count() / (total_days * employees_queryset.count())) * 100, 2) if total_days * employees_queryset.count() > 0 else 0
            },
            'employee_statistics': employee_stats,
        }
        
        # Add department statistics if not filtered
        if not department_id:
            report['department_statistics'] = department_stats
        
        return Response(report, status=status.HTTP_200_OK)

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