from django.contrib import admin
from .models import Employee, Attendance, EmployeeSchedule, EmployeeAttendance



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
