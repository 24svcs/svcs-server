
from django.http import HttpResponse
from .jobs.tasks import notify_customers
from .jobs.refine_attendance_record import refine_attendance_records
from .jobs.generate_attendance_report import generate_attendance_reports


def notify_customers_view(request):
    notify_customers.delay('Hello, world!')
    return HttpResponse('Notification sent')

def refine_attendance_records_view(request):
    refine_attendance_records.delay()
    return HttpResponse('Attendance records refined')

def generate_attendance_reports_view(request):
    generate_attendance_reports.delay()
    return HttpResponse('Attendance reports generated')



