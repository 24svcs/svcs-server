from django_filters.rest_framework import FilterSet
from .models import Attendance, Position, Employee

class AttendanceFilter(FilterSet):


    class Meta:
        model = Attendance  
        fields = {
            'status': ['exact'],
            'date': ['gte', 'lte']
        }
        
        
class PositionFilter(FilterSet):
    class Meta:
        model = Position    
        fields = {
            'department__id': ['exact']
        }


class EmployeePositionFilter(FilterSet):
    class Meta:
        model = Employee
        fields = {
            'employment_details__position__id': ['exact']
        }
