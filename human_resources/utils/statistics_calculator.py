from datetime import datetime, date, timedelta
from .attendance_calculator import AttendanceCalculator

class StatisticsCalculator:
    @staticmethod
    def calculate_employee_statistics(employee, attendance_records, start_date, end_date, 
                                   expected_work_hours=8):
        """Calculate attendance statistics for an employee."""
        # Ensure attendance_records is a list, even if empty
        attendance_records = attendance_records or []

        try:
            employment_details = employee.employment_details
            position = employment_details.position
            department = position.department.name if position and position.department else "N/A"
            position_title = position.title if position else "N/A"
            days_off = employment_details.days_off or []
            shift_start = employment_details.shift_start

            # Get employee-specific expected hours
            if employment_details.shift_start and employment_details.shift_end:
                shift_start_dt = datetime.combine(date.today(), employment_details.shift_start)
                shift_end_dt = datetime.combine(date.today(), employment_details.shift_end)
                
                # Handle overnight shifts
                if shift_end_dt < shift_start_dt:
                    shift_end_dt = datetime.combine(date.today() + timedelta(days=1), employment_details.shift_end)
                
                expected_work_hours = (shift_end_dt - shift_start_dt).total_seconds() / 3600

        except AttributeError:
            department = position_title = "N/A"
            days_off = []
            shift_start = None

        # Calculate basic statistics
        stats = StatisticsCalculator._calculate_basic_stats(attendance_records)
        
        # Calculate working days
        working_days = AttendanceCalculator.calculate_working_days(start_date, end_date, days_off)
        
        # Calculate time-based statistics
        time_stats = StatisticsCalculator._calculate_time_stats(
            attendance_records, shift_start, expected_work_hours)
        
        # Calculate attendance score
        attendance_score = AttendanceCalculator.calculate_attendance_score(
            working_days,
            stats['days_present'],
            stats['days_absent'],
            stats['days_late'],
            time_stats['total_minutes_late'],
            time_stats['avg_working_hours'],
            expected_work_hours
        )

        # Calculate attendance percentage
        attendance_percentage = round((stats['days_present'] / working_days) * 100, 2) if working_days > 0 else 0

        return {
            'id': employee.id,
            'name': f"{employee.first_name} {employee.last_name}",
            'department': department,
            'position': position_title,
            'days_present': stats['days_present'],
            'days_absent': stats['days_absent'],
            'days_late': stats['days_late'],
            'total_minutes_late': round(time_stats['total_minutes_late'], 2),
            'average_working_hours': time_stats['avg_working_hours'],
            'total_working_days': working_days,
            'attendance_percentage': attendance_percentage,
            'attendance_score': attendance_score,
            'score_category': AttendanceCalculator.get_score_category(attendance_score)
        }

    @staticmethod
    def _calculate_basic_stats(attendance_records):
        """Calculate basic attendance statistics."""
        return {
            'days_present': sum(1 for a in attendance_records if a.status != 'ABSENT'),
            'days_absent': sum(1 for a in attendance_records if a.status == 'ABSENT'),
            'days_late': sum(1 for a in attendance_records if a.status == 'LATE'),
        }

    @staticmethod
    def _calculate_time_stats(attendance_records, shift_start, expected_hours):
        """Calculate time-based statistics."""
        total_minutes_late = 0
        total_working_hours = 0
        count_with_complete_hours = 0

        # Calculate late minutes if shift start is defined
        if shift_start:
            for attendance in (a for a in attendance_records if a.status == 'LATE'):
                time_in = datetime.combine(date.today(), attendance.time_in)
                expected_time = datetime.combine(date.today(), shift_start)
                
                # Add 15-minute grace period
                expected_time = expected_time + timedelta(minutes=15)
                
                if time_in > expected_time:
                    minutes_late = (time_in - expected_time).total_seconds() / 60
                    total_minutes_late += minutes_late

        # Calculate working hours
        for attendance in (a for a in attendance_records if a.time_out is not None):
            time_in = datetime.combine(date.today(), attendance.time_in)
            time_out = datetime.combine(date.today(), attendance.time_out)
            
            # Handle overnight shifts
            if time_out < time_in:
                time_out = datetime.combine(date.today() + timedelta(days=1), attendance.time_out)
            
            working_hours = (time_out - time_in).total_seconds() / 3600
            total_working_hours += working_hours
            count_with_complete_hours += 1

        return {
            'total_minutes_late': total_minutes_late,
            'avg_working_hours': round(total_working_hours / count_with_complete_hours, 2) if count_with_complete_hours > 0 else 0
        } 