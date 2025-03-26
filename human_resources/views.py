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



# Attendance Reports
class BaseAttendanceReportView(TimezoneMixin, APIView):
    """Base class for attendance report views with common functionality."""
    
    def get_date_range(self, request):
        # This method is already optimized
        today = timezone.now().date()
        start_date = request.query_params.get('start_date', today.replace(day=1).isoformat())
        end_date = request.query_params.get('end_date', today.isoformat())
        
        try:
            start_date = datetime.fromisoformat(start_date).date()
            end_date = datetime.fromisoformat(end_date).date()
            return start_date, end_date
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def get_filtered_queryset(self, organization_pk, start_date, end_date, department_id=None):
        # Improve by adding select_related for common joins
        queryset = Attendance.objects.select_related(
            'employee',
            'employee__employment_details',
            'employee__employment_details__position',
            'employee__employment_details__position__department'
        ).filter(
            organization_id=organization_pk,
            date__gte=start_date,
            date__lte=end_date
        )
        
        if department_id:
            queryset = queryset.filter(
                employee__employment_details__position__department_id=department_id
            )
            
        return queryset
    
    def get_employees_queryset(self, organization_pk, department_id=None):
        # Improve by adding select_related for common joins
        employees_queryset = Employee.objects.select_related(
            'employment_details',
            'employment_details__position',
            'employment_details__position__department'
        ).filter(organization_id=organization_pk)
        
        if department_id:
            employees_queryset = employees_queryset.filter(
                employment_details__position__department_id=department_id
            )
        return employees_queryset
    
    def calculate_working_days(self, start_date, end_date, days_off):
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
    """
    
    def calculate_attendance_score(self, 
                                  employee_working_days, 
                                  days_present, 
                                  days_absent, 
                                  days_late, 
                                  total_minutes_late, 
                                  avg_working_hours,
                                  expected_hours=8):
        """
        Calculate an attendance score based on multiple factors:
        - Attendance rate (present days / working days)
        - Punctuality (inverse of lateness frequency and duration)
        - Work hours consistency (compared to expected hours)
        
        Returns a score from 0-100 where:
        90-100: Excellent
        80-89: Good
        70-79: Satisfactory
        60-69: Needs Improvement
        <60: Poor
        """
        # Only calculate if we have working days
        if employee_working_days == 0:
            return 0
        
        # Base score components
        # 1. Attendance rate (weighted at 50% of total score)
        attendance_rate = days_present / employee_working_days
        attendance_component = 50 * attendance_rate
        
        # 2. Punctuality (weighted at 30% of total score)
        # Perfect punctuality (no late days) gets full 30 points
        punctuality_rate = 1.0
        if days_present > 0:
            # Penalize for both frequency and severity of lateness
            lateness_frequency = days_late / days_present if days_present > 0 else 0
            average_minutes_late = total_minutes_late / days_late if days_late > 0 else 0
            
            # More severe penalty for frequent lateness
            punctuality_rate -= (lateness_frequency * 0.7)
            
            # Additional penalty for severe lateness (over 30 minutes)
            if average_minutes_late > 30:
                punctuality_rate -= min(0.3, (average_minutes_late - 30) / 100)
                
        punctuality_component = 30 * max(0, punctuality_rate)
            
        # 3. Work hours consistency (weighted at 20% of total score)
        hours_consistency = 1.0
        if avg_working_hours > 0:
            # Penalize for significant deviation from expected hours
            hours_deviation = abs(avg_working_hours - expected_hours) / expected_hours
            hours_consistency = max(0, 1 - hours_deviation)
        hours_component = 20 * hours_consistency
        
        # Calculate total score (round to 1 decimal place)
        attendance_score = round(attendance_component + punctuality_component + hours_component, 1)
        
        return attendance_score
    
    def get_score_category(self, score):
        """Return the category label for a given attendance score."""
        if score >= 90:
            return "Excellent"
        elif score >= 80:
            return "Good"
        elif score >= 70:
            return "Satisfactory"
        elif score >= 60:
            return "Needs Improvement"
        else:
            return "Poor"
    
    def get(self, request, organization_pk):
        # Get date range and department filter
        start_date, end_date = self.get_date_range(request)
        if isinstance(start_date, Response):  # Error occurred
            return start_date
            
        department_id = request.query_params.get('department_id')
        
        # Get filtered querysets with eager loading
        attendance_queryset = self.get_filtered_queryset(organization_pk, start_date, end_date, department_id)
        employees_queryset = self.get_employees_queryset(organization_pk, department_id)
        
        # Use prefetch_related with the correct related name
        employees_queryset = employees_queryset.prefetch_related('attendances')
        
        # Calculate total days in the period
        total_days = (end_date - start_date).days + 1
        
        # Preload all employee attendance records for the period to avoid N+1 problem
        employee_attendance_map = {}
        for attendance in attendance_queryset:
            if attendance.employee_id not in employee_attendance_map:
                employee_attendance_map[attendance.employee_id] = []
            employee_attendance_map[attendance.employee_id].append(attendance)
        
        # Employee-specific statistics
        employee_stats = []
        
        # Get organization-wide average expected hours (default to 8 if not defined)
        expected_work_hours = 8
        try:
            # You might want to get this from organization preferences or another source
            pass
        except:
            pass
        
        for employee in employees_queryset:
            # Get pre-loaded attendance records for this employee
            employee_attendance_records = employee_attendance_map.get(employee.id, [])
            
            # Get employment details - data already loaded via select_related
            try:
                employment_details = employee.employment_details
                shift_start = employment_details.shift_start
                days_off = employment_details.days_off or []
                position = employment_details.position
                
                if position:
                    department = position.department.name if position.department else "N/A"
                    position_title = position.title
                else:
                    department = "N/A"
                    position_title = "N/A"
                    
                # Get employee-specific expected hours
                if employment_details.shift_start and employment_details.shift_end:
                    shift_start_dt = datetime.combine(date.today(), employment_details.shift_start)
                    shift_end_dt = datetime.combine(date.today(), employment_details.shift_end)
                    
                    # Handle overnight shifts
                    if shift_end_dt < shift_start_dt:
                        shift_end_dt = datetime.combine(date.today() + timedelta(days=1), employment_details.shift_end)
                    
                    expected_work_hours = (shift_end_dt - shift_start_dt).total_seconds() / 3600
            except AttributeError:
                shift_start = None
                days_off = []
                department = "N/A"
                position_title = "N/A"
            
            # Calculate individual working days
            employee_working_days = self.calculate_working_days(start_date, end_date, days_off)
            
            # Calculate individual statistics using in-memory data
            days_present = sum(1 for a in employee_attendance_records if a.status != Attendance.ATTENDANCE_ABSENT)
            days_absent = sum(1 for a in employee_attendance_records if a.status == Attendance.ATTENDANCE_ABSENT)
            days_late = sum(1 for a in employee_attendance_records if a.status == Attendance.ATTENDANCE_LATE)
            
            # Calculate minutes late
            total_minutes_late = 0
            if shift_start:
                for attendance in (a for a in employee_attendance_records if a.status == Attendance.ATTENDANCE_LATE):
                    time_in = datetime.combine(date.today(), attendance.time_in)
                    expected_time = datetime.combine(date.today(), shift_start)
                    
                    # Add 15-minute grace period
                    expected_time = expected_time + timedelta(minutes=15)
                    
                    if time_in > expected_time:
                        minutes_late = (time_in - expected_time).total_seconds() / 60
                        total_minutes_late += minutes_late
            
            # Calculate average working hours
            total_working_hours = 0
            count_with_complete_hours = 0
            
            for attendance in (a for a in employee_attendance_records if a.time_out is not None):
                time_in = datetime.combine(date.today(), attendance.time_in)
                time_out = datetime.combine(date.today(), attendance.time_out)
                
                # Handle overnight shifts
                if time_out < time_in:
                    time_out = datetime.combine(date.today() + timedelta(days=1), attendance.time_out)
                
                working_hours = (time_out - time_in).total_seconds() / 3600
                total_working_hours += working_hours
                count_with_complete_hours += 1
            
            avg_working_hours = round(total_working_hours / count_with_complete_hours, 2) if count_with_complete_hours > 0 else 0
            
            # Calculate attendance percentage
            attendance_percentage = round((days_present / employee_working_days) * 100, 2) if employee_working_days > 0 else 0
            
            # Calculate attendance score
            attendance_score = self.calculate_attendance_score(
                employee_working_days,
                days_present,
                days_absent,
                days_late,
                total_minutes_late,
                avg_working_hours,
                expected_hours=expected_work_hours
            )
            
            # Get score category
            score_category = self.get_score_category(attendance_score)
            
            employee_stats.append({
                'id': employee.id,
                'name': f"{employee.first_name} {employee.last_name}",
                'department': department,
                'position': position_title,
                'days_present': days_present,
                'days_absent': days_absent,
                'days_late': days_late,
                'total_minutes_late': round(total_minutes_late, 2),
                'average_working_hours': avg_working_hours,
                'total_working_days': employee_working_days,
                'attendance_percentage': attendance_percentage,
                'attendance_score': attendance_score,
                'score_category': score_category,
                'score_breakdown': {
                    'attendance_component': round(50 * (days_present / employee_working_days) if employee_working_days > 0 else 0, 1),
                    'punctuality_component': round(30 * (1 - (days_late / days_present if days_present > 0 else 0)), 1),
                    'hours_consistency_component': round(20 * (1 - min(1, abs(avg_working_hours - expected_work_hours) / expected_work_hours) if avg_working_hours > 0 else 0), 1)
                }
            })
        
        # Generate the report
        report = {
            'report_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_days': total_days,
            },
            'employee_statistics': employee_stats,
        }
        
        return Response(report, status=status.HTTP_200_OK)


class DepartmentAttendanceReportView(BaseAttendanceReportView):
    """
    Generate attendance reports aggregated by department.
    """
    
    def get(self, request, organization_pk):
        # Get date range
        start_date, end_date = self.get_date_range(request)
        if isinstance(start_date, Response):  # Error occurred
            return start_date
            
        department_id = request.query_params.get('department_id')
        
        # If specific department is requested, return error since this view is for all departments
        if department_id:
            return Response(
                {"error": "This endpoint provides reports for all departments. Remove the department_id parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get filtered querysets with optimized joins
        attendance_queryset = self.get_filtered_queryset(organization_pk, start_date, end_date)
        
        # Load all departments in a single query with prefetched data
        departments = Department.objects.filter(organization_id=organization_pk).prefetch_related(
            'positions',
            'positions__employment_details',
            'positions__employment_details__employee'
        )
        
        # Pre-calculate attendance statistics by department to avoid repeated queries
        dept_attendance_stats = {}
        for attendance in attendance_queryset:
            try:
                dept_id = attendance.employee.employment_details.position.department_id
                if dept_id:
                    if dept_id not in dept_attendance_stats:
                        dept_attendance_stats[dept_id] = {
                            'present': 0,
                            'absent': 0,
                            'late': 0
                        }
                    
                    if attendance.status == Attendance.ATTENDANCE_ABSENT:
                        dept_attendance_stats[dept_id]['absent'] += 1
                    elif attendance.status == Attendance.ATTENDANCE_LATE:
                        dept_attendance_stats[dept_id]['late'] += 1
                        dept_attendance_stats[dept_id]['present'] += 1  # Late employees are also counted as present
                    else:
                        dept_attendance_stats[dept_id]['present'] += 1
            except AttributeError:
                # Skip attendance records without proper department association
                continue
        
        # Calculate department-wise statistics
        department_stats = []
        
        for dept in departments:
            # Collect all employees in this department (already prefetched)
            dept_employees = []
            for position in dept.positions.all():
                for emp_details in position.employment_details.all():
                    if hasattr(emp_details, 'employee') and emp_details.employee:
                        dept_employees.append(emp_details.employee)
            
            dept_employee_count = len(dept_employees)
            
            # Get attendance stats from our pre-calculated map
            dept_stats = dept_attendance_stats.get(dept.id, {'present': 0, 'absent': 0, 'late': 0})
            dept_days_present = dept_stats['present']
            dept_days_absent = dept_stats['absent']
            dept_days_late = dept_stats['late']
            
            # Calculate total working days across all employees
            dept_total_working_days = 0
            for employee in dept_employees:
                try:
                    days_off = employee.employment_details.days_off or []
                except (AttributeError, EmploymentDetails.DoesNotExist):
                    days_off = []
                
                # Count working days for this employee
                employee_working_days = self.calculate_working_days(start_date, end_date, days_off)
                dept_total_working_days += employee_working_days
            
            # Calculate department statistics
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
                'total_days': (end_date - start_date).days + 1,
            },
            'department_statistics': department_stats,
        }
        
        return Response(report, status=status.HTTP_200_OK)


class OverallAttendanceReportView(BaseAttendanceReportView):
    """
    Generate overall attendance statistics for the organization.
    """
    
    def get(self, request, organization_pk):
        # Get date range and department filter
        start_date, end_date = self.get_date_range(request)
        if isinstance(start_date, Response):  # Error occurred
            return start_date
            
        department_id = request.query_params.get('department_id')
        
        # Use Django's aggregation for efficient counting
        attendance_queryset = self.get_filtered_queryset(organization_pk, start_date, end_date, department_id)
        employees_queryset = self.get_employees_queryset(organization_pk, department_id)
        
        # Calculate total days in the period
        total_days = (end_date - start_date).days + 1
        
        # Calculate overall statistics using efficient aggregation
        total_employees = employees_queryset.count()
        
        # Using Django's aggregation and annotation for better performance
        attendance_stats = attendance_queryset.aggregate(
            total_records=Count('id'),
            total_absent=Count('id', filter=Q(status=Attendance.ATTENDANCE_ABSENT)),
            total_late=Count('id', filter=Q(status=Attendance.ATTENDANCE_LATE))
        )
        
        total_attendance_records = attendance_stats['total_records']
        total_absent = attendance_stats['total_absent']
        total_late = attendance_stats['total_late']
        total_present = total_attendance_records - total_absent
        
        # Calculate overall attendance percentage
        department_description = f"Department {department_id}" if department_id else "All departments"
        
        # Generate the report
        report = {
            'report_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total_days': total_days,
                'scope': department_description,
            },
            'overall_statistics': {
                'total_employees': total_employees,
                'total_attendance_records': total_attendance_records,
                'total_present': total_present,
                'total_absent': total_absent,
                'total_late': total_late,
                'average_attendance_percentage': round((total_present / (total_days * total_employees)) * 100, 2) if total_days * total_employees > 0 else 0
            }
        }
        
        return Response(report, status=status.HTTP_200_OK)