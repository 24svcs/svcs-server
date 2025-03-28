from celery import shared_task
from datetime import datetime, timedelta
import logging
import pytz
from django.db import transaction

from human_resources.models import Employee, EmployeeSchedule, Attendance
from organization.models import Organization

logger = logging.getLogger(__name__)

@shared_task
def refine_attendance_records():
    """
    Task to check for missing attendance records and create absence records
    for employees who missed their shifts. This task should run frequently
    (e.g., hourly) to ensure timely recording of absences.
    """
    try:
        organizations = Organization.objects.all()
        total_absence_count = 0
        
        for organization in organizations:
            org_absence_count = process_organization_absences(organization)
            total_absence_count += org_absence_count
            
        return f"Created {total_absence_count} absence records across all organizations"
    except Exception as e:
        logger.error(f"Error refining attendance records: {str(e)}")
        return f"Error refining attendance records: {str(e)}"

def process_organization_absences(organization):
    """
    Process absences for all active employees in the given organization.
    """
    # Get organization timezone
    org_timezone = get_organization_timezone(organization)
    
    # Get current time in the organization's timezone
    current_time = datetime.now(org_timezone)
    today = current_time.date()
    
    # Get day of week for scheduling lookup
    day_of_week = current_time.strftime('%A').upper()
    
    # Only process active employees
    employees = Employee.objects.filter(organization=organization, is_active=True)
    absence_count = 0
    
    for employee in employees:
        absences_created = check_employee_absence(employee, today, current_time, day_of_week, org_timezone)
        absence_count += absences_created
        
    logger.info(f"Created {absence_count} absence records for {employees.count()} employees in organization {organization.id}")
    return absence_count

def get_organization_timezone(organization):
    """Helper function to get the organization's timezone"""
    try:
        if hasattr(organization, 'preferences') and organization.preferences.timezone:
            org_timezone = organization.preferences.timezone
            return pytz.timezone(str(org_timezone))
    except Exception as e:
        logger.warning(f"Could not get organization timezone, using UTC: {str(e)}")
    
    return pytz.UTC

def check_employee_absence(employee, today, current_time, day_of_week, org_timezone):
    """
    Check if an employee should be marked absent based on their schedule.
    Only processes employees whose shifts have passed without check-in.
    """
    # Check if attendance already exists for today
    if Attendance.objects.filter(employee=employee, date=today).exists():
        return 0  # Attendance already recorded for today
    
    # Try to get employee's schedule for this day
    schedule = None
    
    try:
        # First try specific schedule for this day
        schedule = EmployeeSchedule.objects.get(employee=employee, day_of_week=day_of_week)
        
        # If no shift today, return early
        if not schedule.shift_start:
            logger.info(f"Employee {employee.id} has no shift scheduled on {day_of_week}")
            return 0
            
    except EmployeeSchedule.DoesNotExist:
        # Fall back to employment details if no specific schedule
        try:
            employment_details = employee.employment_details
            if not employment_details.shift_start:
                logger.info(f"Employee {employee.id} has no default shift scheduled")
                return 0
                
            # Create a pseudo schedule from employment details
            from django.utils.functional import SimpleLazyObject
            schedule = SimpleLazyObject(lambda: type('ScheduleProxy', (), {
                'shift_start': employment_details.shift_start,
                'shift_end': employment_details.shift_end
            }))
        except Exception as e:
            logger.warning(f"No schedule found for employee {employee.id}: {str(e)}")
            return 0
    
    # Convert schedule times to datetime for comparison
    shift_start_naive = datetime.combine(today, schedule.shift_start)
    shift_start = org_timezone.localize(shift_start_naive)
    
    shift_end_naive = datetime.combine(today, schedule.shift_end)
    shift_end = org_timezone.localize(shift_end_naive)
    
    # Handle overnight shifts (end time before start time)
    if shift_end < shift_start:
        shift_end += timedelta(days=1)
    
    # Calculate a grace period (e.g., shift end + 30 minutes)
    grace_period = shift_end + timedelta(minutes=30)
    
    # Only mark as absent if the grace period has passed
    if current_time > grace_period:
        # Create an absence record
        with transaction.atomic():
            # Double-check no attendance was created while processing
            if not Attendance.objects.filter(employee=employee, date=today).exists():
                Attendance.objects.create(
                    employee=employee,
                    organization=employee.organization,
                    date=today,
                    time_in=None,  # No check-in
                    time_out=None, # No check-out
                    status='A',    # Absent
                    note="Automatically marked absent due to missed shift",
                    overtime_hours=0
                )
                logger.info(f"Marked employee {employee.id} as absent for {today} (shift time: {shift_start.time()} - {shift_end.time()})")
                return 1
    
    return 0
