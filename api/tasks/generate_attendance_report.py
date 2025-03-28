from celery import shared_task
from datetime import datetime, timedelta
import logging
from django.db.models import Max
import pytz
from decimal import Decimal

from human_resources.models import EmployeeAttendance, Employee, EmployeeSchedule, Attendance
from organization.models import Organization, Preference

logger = logging.getLogger(__name__)

@shared_task
def generate_attendance_reports():
    """
    Task to generate attendance reports for all employees across all organizations.
    This task is scheduled to run every 7 days but will create records for each day
    since the last recorded attendance for each employee.
    """
    try:
        organizations = Organization.objects.all()
        total_report_count = 0
        
        for organization in organizations:
            org_report_count = generate_organization_reports(organization)
            total_report_count += org_report_count
            
        return f"Generated {total_report_count} attendance reports across all organizations"
    except Exception as e:
        logger.error(f"Error generating attendance reports: {str(e)}")
        return f"Error generating attendance reports: {str(e)}"

def generate_organization_reports(organization):
    """
    Generate attendance reports for all employees in the given organization.
    """
    employees = Employee.objects.filter(organization=organization)
    report_count = 0
    
    for employee in employees:
        reports_created = generate_single_employee_report(employee)
        report_count += reports_created
        
    logger.info(f"Generated {report_count} attendance reports for {employees.count()} employees in organization {organization.id}")
    return report_count

def get_organization_timezone(organization):
    """Helper function to get the organization's timezone"""
    try:
        if hasattr(organization, 'preferences') and organization.preferences.timezone:
            org_timezone = organization.preferences.timezone
            logger.info(f"Using organization timezone: {org_timezone}")
            return pytz.timezone(str(org_timezone))
    except Exception as e:
        logger.warning(f"Could not get organization timezone, using UTC: {str(e)}")
    
    return pytz.UTC

def generate_single_employee_report(employee):
    """
    Generate attendance report for a single employee based on existing Attendance records.
    Only creates EmployeeAttendance entries for days that have Attendance records.
    """
    organization = employee.organization
    today = datetime.now().date()
    
    # Get organization timezone
    org_timezone = get_organization_timezone(organization)
    
    # Only process active employees
    if not employee.is_active:
        logger.info(f"Skipping inactive employee {employee.id}")
        return 0
    
    # Find the most recent attendance report for this employee
    last_report_date = EmployeeAttendance.objects.filter(employee=employee).aggregate(Max('date'))['date__max']
    
    # Find attendance records that don't have corresponding attendance reports
    attendance_query = employee.attendances.all()
    
    # If there's a last report, only process attendance records after that date
    if last_report_date:
        attendance_query = attendance_query.filter(date__gt=last_report_date)
    
    # Get all attendance records that need reports
    attendance_records = attendance_query.order_by('date')
    
    logger.info(f"Found {attendance_records.count()} attendance records to process for employee {employee.id}")
    
    report_count = 0
    
    # Process each attendance record
    for attendance in attendance_records:
        # Skip if an attendance report already exists for this date
        if EmployeeAttendance.objects.filter(employee=employee, date=attendance.date).exists():
            continue
        
        # Get the day of week for this date
        day_of_week = attendance.date.strftime('%A').upper()
        
        # Calculate working hours and lateness
        is_present = attendance.status != 'A'
        is_absent = attendance.status == 'A'
        is_late = attendance.status == 'L'
        
        working_hours = Decimal('0')
        late_minutes = 0
        
        # If the attendance record already has a 'late' status, ensure late_minutes is at least 1
        if is_late:
            late_minutes = max(1, late_minutes)
        
        # Get the overtime hours directly from the attendance record
        overtime_hours = attendance.overtime_hours
        
        # Only calculate these if the employee was present and both time_in and time_out exist
        if is_present and attendance.time_in and attendance.time_out:
            # Find the employee's schedule for this day to get official shift times
            schedule = None
            scheduled_start = None
            scheduled_end = None
            
            # First try to get specific schedule for this day
            try:
                schedule = EmployeeSchedule.objects.get(employee=employee, day_of_week=day_of_week)
                if schedule.shift_start and schedule.shift_end:
                    # Create naive datetime objects using the attendance date
                    naive_start = datetime.combine(attendance.date, schedule.shift_start)
                    naive_end = datetime.combine(attendance.date, schedule.shift_end)
                    
                    # Make them timezone-aware in the organization's timezone
                    scheduled_start = org_timezone.localize(naive_start)
                    scheduled_end = org_timezone.localize(naive_end)
                    
                    logger.info(f"Schedule times for employee {employee.id} on {day_of_week}: start={scheduled_start}, end={scheduled_end}")
            except EmployeeSchedule.DoesNotExist:
                # Fall back to employment details if no specific schedule
                try:
                    employment_details = employee.employment_details
                    if employment_details.shift_start and employment_details.shift_end:
                        # Create naive datetime objects using the attendance date
                        naive_start = datetime.combine(attendance.date, employment_details.shift_start)
                        naive_end = datetime.combine(attendance.date, employment_details.shift_end)
                        
                        # Make them timezone-aware in the organization's timezone
                        scheduled_start = org_timezone.localize(naive_start)
                        scheduled_end = org_timezone.localize(naive_end)
                        
                        logger.info(f"Employment details times for employee {employee.id}: start={scheduled_start}, end={scheduled_end}")
                except Exception as e:
                    logger.warning(f"No schedule found for employee {employee.id} on {day_of_week}: {str(e)}")
            
            # Convert attendance times to timezone-aware datetime objects
            naive_time_in = datetime.combine(attendance.date, attendance.time_in)
            naive_time_out = datetime.combine(attendance.date, attendance.time_out)
            
            # Make datetime objects timezone-aware in UTC (assuming DB stores in UTC)
            time_in_utc = pytz.UTC.localize(naive_time_in)
            time_out_utc = pytz.UTC.localize(naive_time_out)
            
            # Convert to organization's timezone
            time_in = time_in_utc.astimezone(org_timezone)
            time_out = time_out_utc.astimezone(org_timezone)
            
            logger.info(f"Attendance times for employee {employee.id}: in={time_in}, out={time_out}")
            
            # Handle overnight shifts
            if scheduled_end and scheduled_end < scheduled_start:
                scheduled_end += timedelta(days=1)
            
            if time_out < time_in:
                time_out += timedelta(days=1)
            
            # Calculate working hours based on scheduled times and actual check-in/out
            if scheduled_start and scheduled_end:
                # Use the LATER of scheduled_start or time_in (don't count early arrival)
                effective_start = max(scheduled_start, time_in)
                
                # Use the EARLIER of scheduled_end or time_out (don't count staying late)
                effective_end = min(scheduled_end, time_out)
                
                # Calculate actual working hours within scheduled shift
                if effective_end > effective_start:
                    duration = effective_end - effective_start
                    working_hours = Decimal(str(round(duration.total_seconds() / 3600, 2)))
                else:
                    # If effective_end <= effective_start, they didn't work during scheduled hours
                    working_hours = Decimal('0')
                    
                # Calculate lateness
                if time_in > scheduled_start:
                    late_delta = time_in - scheduled_start
                    late_minutes = int(late_delta.total_seconds() / 60)
                    is_late = late_minutes > 0
                    
                    # Add debug logging
                    logger.info(f"DEBUG: Employee {employee.id} lateness calculation:")
                    logger.info(f"DEBUG: Scheduled start: {scheduled_start} ({scheduled_start.tzinfo})")
                    logger.info(f"DEBUG: Check-in time: {time_in} ({time_in.tzinfo})")
                    logger.info(f"DEBUG: Late by: {late_delta} = {late_minutes} minutes")
                
                # Ensure consistency: if marked as late but minutes is 0, set to at least 1
                if is_late and late_minutes == 0:
                    late_minutes = 1
                    logger.info(f"Setting minimum late minutes to 1 for employee {employee.id} on {attendance.date}")
                
                # Log if there's overtime in the attendance record
                if overtime_hours > 0:
                    logger.info(f"Using overtime of {overtime_hours} hours for employee {employee.id} on {attendance.date}")
                
                # Add overtime hours to the total working hours
                working_hours += overtime_hours
            else:
                # If no schedule information is available, use actual times but log a warning
                logger.warning(f"No shift schedule times for employee {employee.id} on {attendance.date}. Using actual check-in/out times.")
                duration = time_out - time_in
                working_hours = Decimal(str(round(duration.total_seconds() / 3600, 2)))
                
                # Add overtime hours to the total working hours
                working_hours += overtime_hours
        elif is_present and attendance.time_in:
            # If employee checked in but didn't check out, we can still calculate lateness
            # Find the employee's schedule for this day to get official shift times
            schedule = None
            scheduled_start = None
            
            # First try to get specific schedule for this day
            try:
                schedule = EmployeeSchedule.objects.get(employee=employee, day_of_week=day_of_week)
                if schedule.shift_start:
                    # Create naive datetime object using the attendance date
                    naive_start = datetime.combine(attendance.date, schedule.shift_start)
                    
                    # Make it timezone-aware in the organization's timezone
                    scheduled_start = org_timezone.localize(naive_start)
            except EmployeeSchedule.DoesNotExist:
                # Fall back to employment details if no specific schedule
                try:
                    employment_details = employee.employment_details
                    if employment_details.shift_start:
                        # Create naive datetime object using the attendance date
                        naive_start = datetime.combine(attendance.date, employment_details.shift_start)
                        
                        # Make it timezone-aware in the organization's timezone
                        scheduled_start = org_timezone.localize(naive_start)
                except Exception as e:
                    logger.warning(f"No schedule found for employee {employee.id} on {day_of_week}: {str(e)}")
            
            # Calculate lateness if schedule information is available
            if scheduled_start and attendance.time_in:
                # Make time_in timezone-aware in UTC and convert to organization timezone
                naive_time_in = datetime.combine(attendance.date, attendance.time_in)
                time_in_utc = pytz.UTC.localize(naive_time_in)
                time_in = time_in_utc.astimezone(org_timezone)
                
                if time_in > scheduled_start:
                    late_delta = time_in - scheduled_start
                    late_minutes = int(late_delta.total_seconds() / 60)
                    is_late = late_minutes > 0
                    
                    # Add debug logging
                    logger.info(f"DEBUG: Employee {employee.id} lateness calculation:")
                    logger.info(f"DEBUG: Scheduled start: {scheduled_start} ({scheduled_start.tzinfo})")
                    logger.info(f"DEBUG: Check-in time: {time_in} ({time_in.tzinfo})")
                    logger.info(f"DEBUG: Late by: {late_delta} = {late_minutes} minutes")
                    
                    # Ensure consistency: if marked as late but minutes is 0, set to at least 1
                    if is_late and late_minutes == 0:
                        late_minutes = 1
                        logger.info(f"Setting minimum late minutes to 1 for employee {employee.id} on {attendance.date}")
                logger.info(f"Employee {employee.id} was {late_minutes} minutes late on {attendance.date}")
            
            # Still set working hours to zero since check-out is missing
            logger.warning(f"Missing check-out data for employee {employee.id} on {attendance.date}. Setting working hours to zero.")
            working_hours = Decimal('0')
        else:
            # If check-in data is also missing, ensure working hours remain zero
            logger.warning(f"Missing check-in/out data for employee {employee.id} on {attendance.date}. Setting working hours to zero.")
            working_hours = Decimal('0')
        
        # Create the attendance report
        EmployeeAttendance.objects.create(
            employee=employee,
            organization=organization,
            date=attendance.date,
            is_present=is_present,
            is_late=is_late,
            is_absent=is_absent,
            late_minutes=late_minutes,
            working_hours=working_hours,
        )
        report_count += 1
        
    logger.info(f"Generated {report_count} attendance reports for employee {employee.id}")
    return report_count


@shared_task
def debug_employee_report(employee_id=None):
    """
    Task to debug attendance report generation for a specific employee or all employees.
    """
    try:
        if employee_id:
            try:
                employee = Employee.objects.get(id=employee_id)
                logger.info(f"Manually generating report for employee {employee.id} ({employee.first_name} {employee.last_name})")
                
                # Additional debug info
                creation_date = getattr(employee, 'created_at', None)
                if creation_date:
                    logger.info(f"Employee creation date: {creation_date}")
                else:
                    logger.warning(f"Employee {employee.id} has no created_at attribute")
                
                reports_created = generate_single_employee_report(employee)
                return f"Generated {reports_created} attendance reports for employee {employee.id}"
            except Employee.DoesNotExist:
                logger.error(f"Employee with ID {employee_id} does not exist")
                return f"Error: Employee with ID {employee_id} does not exist"
        else:
            # Generate for all employees
            employees = Employee.objects.filter(is_active=True)
            total_count = 0
            
            for employee in employees:
                logger.info(f"Processing employee {employee.id}: {employee.first_name} {employee.last_name}")
                reports_created = generate_single_employee_report(employee)
                total_count += reports_created
                
            return f"Generated {total_count} attendance reports for {employees.count()} employees"
    except Exception as e:
        logger.error(f"Error in debug_employee_report: {str(e)}")
        return f"Error debugging employee reports: {str(e)}"