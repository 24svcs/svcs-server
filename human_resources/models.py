from django.db import models
from django.core.validators import  MinLengthValidator
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
from core.models import User
from organization.models import Organization
import random

def generate_unique_employee_id():
    employee_id = None
    while not employee_id or Employee.objects.filter(id=employee_id).exists():
        employee_id = str(random.randint(10000000, 99999999))
    return employee_id

class Department(models.Model):
    organization = models.ForeignKey(Organization, related_name='departments', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, validators=[MinLengthValidator(2)],  unique=True)
    description = models.TextField(blank=True, null=True)
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_department')
    image_url = models.URLField(blank=True, null=True)


    class Meta:
        indexes = [
            models.Index(fields=['organization']),
            models.Index(fields=['name']),
            models.Index(fields=['manager']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['organization', 'name'], name='unique_department_per_organization')
        ]

    def __str__(self):
        return self.name

class Position(models.Model):
    title = models.CharField(max_length=100, validators=[MinLengthValidator(3)],  unique=True)
    organization = models.ForeignKey(Organization, related_name='positions', on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='positions')
    description = models.TextField(blank=True, null=True)
    salary_range_min = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    salary_range_max = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

    class Meta:
        indexes = [
            models.Index(fields=['department']),
            models.Index(fields=['title']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['organization', 'title'], name='unique_position_per_organization'),
            models.CheckConstraint(
                condition=models.Q(salary_range_max__gte=models.F('salary_range_min')),
                name='salary_range_max_gte_min'
            )
        ]

    def __str__(self):
        return f"{self.title} - {self.department.name}"

class Employee(models.Model):
    GENDER_CHOICES = (
        ('M', 'Male'),
        ('F', 'Female'),
        ('O', 'Other'),
    )
    
    organization = models.ForeignKey(Organization, related_name='employees', on_delete=models.CASCADE)
    id = models.CharField(
        max_length=8, 
        primary_key=True, 
        unique=True, 
        default=generate_unique_employee_id, 
        editable=False
    )
    user = models.OneToOneField(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='employee')
    first_name = models.CharField(max_length=50, validators=[MinLengthValidator(3)])
    last_name = models.CharField(max_length=50, validators=[MinLengthValidator(3)])
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    phone_number = PhoneNumberField(unique=True)
    address = models.TextField()
    emergency_contact_name = models.CharField(max_length=100, blank=True, null=True)
    emergency_contact_phone = PhoneNumberField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['organization']),
            models.Index(fields=['last_name', 'first_name']), 
        ]
        constraints = [
            models.UniqueConstraint(fields=['organization', 'user'], name='unique_employee_per_organization'),
        ]
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.id})"


class EmploymentDetails(models.Model):
    EMPLOYMENT_STATUS = (
        ('FT', 'Full-time'),
        ('PT', 'Part-time'),
        ('CT', 'Contract'),
        ('IN', 'Intern'),
    )
    
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='employment_details')
    position = models.ForeignKey(Position, on_delete=models.PROTECT, related_name='employment_details')
    hire_date = models.DateField()
    employment_status = models.CharField(max_length=2, choices=EMPLOYMENT_STATUS, default='FT')
    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)
    days_off = models.JSONField(default=list, blank=True, null=True)
    annual_leave_days = models.PositiveIntegerField(default=0)
    sick_leave_days = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['position']),
            models.Index(fields=['employment_status']),
            models.Index(fields=['hire_date']),
        ]
       
    
    def __str__(self):
        return f"Employment details for {self.employee}"

class Attendance(models.Model):
    ATTENDANCE_ON_TIME = 'O'
    ATTENDANCE_ABSENT = 'A'
    ATTENDANCE_LATE = 'L'
    
    ATTENDANCE_STATUSES = (
        (ATTENDANCE_ON_TIME, 'On Time'),
        (ATTENDANCE_ABSENT, 'Absent'),
        (ATTENDANCE_LATE, 'Late'),
    )

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='attendances')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    time_in = models.TimeField()
    time_out = models.TimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUSES)
    note = models.TextField(blank=True, null=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['date']),
            models.Index(fields=['status']),
            models.Index(fields=['employee', 'date']),  # For faster lookups by employee and date
        ]
        constraints = [
            models.UniqueConstraint(fields=['employee', 'date'], name='unique_attendance_per_day'),
            models.CheckConstraint(
                condition=models.Q(time_out__isnull=True) | models.Q(time_out__gt=models.F('time_in')),
                name='time_out_after_time_in'
            )
        ]
    
    def __str__(self):
        return f"{self.employee.first_name} - {self.date} - {self.status}"

class Payroll(models.Model):
    STATUSES_CHOICES = [
        ('PENDING', 'Pending'),
        ('PROCESSED', 'Processed'),
        ('PAID', 'Paid'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('BANK_TRANSFER', 'Bank Transfer'),
        ('CHECK', 'Check'),
        ('CASH', 'Cash'),
        ('PAYPAL', 'PayPal'),
        ('DIRECT_DEPOSIT', 'Direct Deposit'),
        ('MOBILE_PAYMENT', 'Mobile Payment'),
        ('OTHER', 'Other'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payrolls')
    period_start = models.DateField()
    period_end = models.DateField()
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2)
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    overtime_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    net_salary = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateField()
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUSES_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['period_start']),
            models.Index(fields=['period_end']),
            models.Index(fields=['payment_date']),
            models.Index(fields=['status']),
            models.Index(fields=['employee', 'period_start', 'period_end']),  # For unique constraint
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'period_start', 'period_end'],
                name='unique_payroll_per_period'
            ),
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F('period_start')),
                name='payroll_period_end_after_start'
            ),
            models.CheckConstraint(
                condition=models.Q(net_salary__gte=0),
                name='net_salary_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(overtime_hours__gte=0),
                name='overtime_hours_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(overtime_rate__gte=0),
                name='overtime_rate_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(deductions__gte=0),
                name='deductions_non_negative'
            ),
            models.CheckConstraint(
                condition=models.Q(tax__gte=0),
                name='tax_non_negative'
            )
        ]
    
    def __str__(self):
        return f"{self.employee.first_name} - {self.period_start} to {self.period_end}"
