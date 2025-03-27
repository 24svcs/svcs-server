from django.contrib import admin
from .models import Employee, Attendance, EmployeeSchedule



# Register your models here.
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name','employment_details__shift_start', 'employment_details__shift_end' )



@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'status', 'date', 'time_in', 'time_out')
    


@admin.register(EmployeeSchedule)
class EmployeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'employee__id', 'day_of_week', 'shift_start', 'shift_end')

