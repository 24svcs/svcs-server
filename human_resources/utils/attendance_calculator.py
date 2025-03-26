from datetime import datetime, date, timedelta

class AttendanceCalculator:
    @staticmethod
    def calculate_working_days(start_date, end_date, days_off):
        """Calculate working days between two dates, excluding days off."""
        if start_date is None or end_date is None:
            return 0
        
        working_days = 0
        current_date = start_date
        while current_date <= end_date:
            day_name = current_date.strftime('%A').upper()
            if day_name not in days_off:
                working_days += 1
            current_date += timedelta(days=1)
        return working_days

    @staticmethod
    def calculate_attendance_score(employee_working_days, days_present, days_absent, 
                                 days_late, total_minutes_late, avg_working_hours, 
                                 expected_hours=8):
        """Calculate attendance score based on multiple factors."""
        if employee_working_days == 0:
            return 0
        
        # Attendance rate (50%)
        attendance_rate = days_present / employee_working_days
        attendance_component = 50 * attendance_rate
        
        # Punctuality (30%)
        punctuality_component = AttendanceCalculator._calculate_punctuality_component(
            days_present, days_late, total_minutes_late)
        
        # Hours consistency (20%)
        hours_component = AttendanceCalculator._calculate_hours_component(
            avg_working_hours, expected_hours)
        
        return round(attendance_component + punctuality_component + hours_component, 1)

    @staticmethod
    def _calculate_punctuality_component(days_present, days_late, total_minutes_late):
        punctuality_rate = 1.0
        if days_present > 0:
            lateness_frequency = days_late / days_present
            average_minutes_late = total_minutes_late / days_late if days_late > 0 else 0
            
            punctuality_rate -= (lateness_frequency * 0.7)
            if average_minutes_late > 30:
                punctuality_rate -= min(0.3, (average_minutes_late - 30) / 100)
                
        return 30 * max(0, punctuality_rate)

    @staticmethod
    def _calculate_hours_component(avg_working_hours, expected_hours):
        if avg_working_hours > 0:
            hours_deviation = abs(avg_working_hours - expected_hours) / expected_hours
            hours_consistency = max(0, 1 - hours_deviation)
            return 20 * hours_consistency
        return 0

    @staticmethod
    def get_score_category(score):
        """Get category label for attendance score."""
        if score >= 90: return "Excellent"
        elif score >= 80: return "Good"
        elif score >= 70: return "Satisfactory"
        elif score >= 60: return "Needs Improvement"
        return "Poor" 