from django.contrib import admin
from .models import Employee, Attendance, EmployeeSchedule, EmployeeAttendance, HRPreferences



# Register your models here.
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name','created_at' )



@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'status', 'date', 'time_in', 'time_out')
    


@admin.register(EmployeeSchedule)
class EmployeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'employee__id', 'day_of_week', 'shift_start', 'shift_end')



@admin.register(EmployeeAttendance)
class EmployeeAttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'date', 'is_present', 'is_late', 'is_absent', 'late_minutes', 'working_hours')
    list_per_page = 500


@admin.register(HRPreferences)
class HRPreferencesAdmin(admin.ModelAdmin):
    list_display = ('id', 'organization', 'grace_period_minutes', 'early_check_in_minutes', 'allow_overtime', 'max_overtime_hours', 'default_annual_leave_days', 'default_sick_leave_days', 'allow_leave_carryover', 'max_leave_carryover_days', 'standard_working_hours', 'standard_working_days', 'lunch_break_minutes', 'tea_break_minutes', 'notify_late_attendance', 'notify_early_checkout', 'notify_leave_requests')
