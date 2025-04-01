import logging
from datetime import datetime, timedelta
import pytz
from django.utils.translation import gettext as _
from human_resources.models import Attendance, HRPreferences, EmployeeSchedule

logger = logging.getLogger(__name__)

def verify_and_fix_late_attendance(attendance_id):
    """
    Verify if an attendance was wrongfully marked as late and fix it if necessary.
    
    Args:
        attendance_id: The ID of the attendance record to verify
        
    Returns:
        tuple: (bool, str) - (was_fixed, message)
        - was_fixed: True if the attendance was fixed, False otherwise
        - message: A message describing what was done or why nothing was done
    """
    try:
        attendance = Attendance.objects.select_related(
            'employee__organization',
            'employee__employment_details',
            'organization'
        ).get(id=attendance_id)
    except Attendance.DoesNotExist:
        return False, _("Attendance record not found.")

    if attendance.status != Attendance.ATTENDANCE_LATE:
        return False, _("Attendance is not marked as late.")

    # Get organization timezone
    try:
        org_preferences = attendance.organization.preferences
        org_timezone = pytz.timezone(str(org_preferences.timezone))
    except:
        org_timezone = pytz.UTC
        logger.warning(f"Could not get organization timezone, using UTC")

    # Get HR preferences with fallback values
    try:
        hr_preferences = attendance.organization.hr_preferences
        grace_period = hr_preferences.grace_period_minutes
    except HRPreferences.DoesNotExist:
        grace_period = 15  # Default grace period
        logger.info(f"Using default grace period: {grace_period} minutes")

    # Convert attendance time to organization's timezone
    utc_check_in = datetime.combine(attendance.date, attendance.time_in)
    utc_check_in = pytz.UTC.localize(utc_check_in)
    local_check_in = utc_check_in.astimezone(org_timezone)
    
    # Get the day of week for the attendance date
    day_of_week = local_check_in.strftime('%A').upper()
    logger.info(f"Processing attendance for {day_of_week}")

    # Get expected shift start time
    shift_start = None
    try:
        # First try to get the schedule for this specific day
        schedule = EmployeeSchedule.objects.get(
            employee=attendance.employee,
            day_of_week=day_of_week
        )
        if schedule.is_working_day and schedule.shift_start:
            shift_start = schedule.shift_start
            logger.info(f"Found schedule shift start time: {shift_start}")
    except EmployeeSchedule.DoesNotExist:
        # Fall back to employment details
        try:
            employment_details = attendance.employee.employment_details
            if employment_details.shift_start:
                shift_start = employment_details.shift_start
                logger.info(f"Using employment details shift start time: {shift_start}")
        except:
            return False, _("Could not determine shift start time.")

    if not shift_start:
        return False, _("No shift start time defined.")

    # Calculate late threshold in local time
    shift_start_dt = datetime.combine(local_check_in.date(), shift_start)
    late_threshold = shift_start_dt + timedelta(minutes=grace_period)
    
    logger.info(f"Check-in time (local): {local_check_in.time()}")
    logger.info(f"Shift start time: {shift_start}")
    logger.info(f"Late threshold: {late_threshold.time()}")

    # Check if the check-in time was actually within grace period
    if local_check_in.time() <= late_threshold.time():
        # Employee was not actually late, fix the status
        attendance.status = Attendance.ATTENDANCE_ON_TIME
        attendance.save()
        logger.info(f"Fixed attendance status from LATE to ON_TIME")
        return True, _("Attendance status corrected from LATE to ON TIME.")
    else:
        logger.info(f"Attendance was correctly marked as late")
        return False, _("Attendance was correctly marked as late.") 