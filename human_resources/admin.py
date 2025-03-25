from django.contrib import admin
from .models import Employee, Attendance



# Register your models here.
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name','employment_details__shift_start', 'employment_details__shift_end' )


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'employee', 'status', 'date', 'time_in', 'time_out')

