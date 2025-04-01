from django.db import models
from django.core.validators import  MinLengthValidator
from django.utils.translation import gettext_lazy as _
from phonenumber_field.modelfields import PhoneNumberField
from core.models import User
from organization.models import Organization
import random
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver
from datetime import datetime, timedelta
from django.db.models import Max
import logging

logger = logging.getLogger(__name__)

def generate_unique_employee_id():
    employee_id = None
    while not employee_id or Employee.objects.filter(id=employee_id).exists():
        employee_id = str(random.randint(10000000, 99999999))
    return employee_id

class Department(models.Model):
    organization = models.ForeignKey(Organization, related_name='departments', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, validators=[MinLengthValidator(2)])
    description = models.TextField(blank=True, null=True)
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_department')
    image_url = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


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

    def clean(self):
        if self.manager and self.manager.organization != self.organization:
            raise ValidationError("Manager must belong to the same organization")

class Position(models.Model):
    title = models.CharField(max_length=100, validators=[MinLengthValidator(3)])
    organization = models.ForeignKey(Organization, related_name='positions', on_delete=models.CASCADE)
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='positions')
    description = models.TextField(blank=True, null=True)
    salary_range_min = models.DecimalField(max_digits=10, decimal_places=2)
    salary_range_max = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['department']),
            models.Index(fields=['title']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['organization', 'title', 'department'], name='unique_position_per_organization'),

            models.CheckConstraint(
                condition=models.Q(salary_range_max__gte=models.F('salary_range_min')),
                name='salary_range_max_gte_min'
            ),
            models.CheckConstraint(
                condition=models.Q(salary_range_min__gt=0),
                name='salary_range_min_positive'
            )
        ]

    def __str__(self):
        return f"{self.title} - {self.department.name}"

    def clean(self):
        if self.department.organization != self.organization:
            raise ValidationError("Department must belong to the same organization")

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
    is_active = models.BooleanField(default=True)
    
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
    salary = models.DecimalField(max_digits=10, decimal_places=2)
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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(shift_end__gt=models.F('shift_start')) | 
                         models.Q(shift_start__isnull=True) | 
                         models.Q(shift_end__isnull=True),
                name='shift_end_after_start'
            ),
            models.CheckConstraint(
                condition=models.Q(days_off__isnull=True) |
                         models.Q(days_off__contained_by=[
                             'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']),
                name='valid_days_off'
            )
        ]
    
    def __str__(self):
        return f"Employment details for {self.employee}"

    def clean(self):
        if self.position.organization != self.employee.organization:
            raise ValidationError("Position must belong to employee's organization")
        if self.salary < self.position.salary_range_min or self.salary > self.position.salary_range_max:
            raise ValidationError("Salary must be within position's range")

class EmployeeSchedule(models.Model):
    DAYS_OF_WEEK = (
        ('MONDAY', 'Monday'),
        ('TUESDAY', 'Tuesday'),
        ('WEDNESDAY', 'Wednesday'),
        ('THURSDAY', 'Thursday'),
        ('FRIDAY', 'Friday'),
        ('SATURDAY', 'Saturday'),
        ('SUNDAY', 'Sunday'),
    )
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.CharField(max_length=10, choices=DAYS_OF_WEEK)
    shift_start = models.TimeField(null=True, blank=True)
    shift_end = models.TimeField(null=True, blank=True)
    is_working_day = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['day_of_week']),
            models.Index(fields=['is_working_day']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'day_of_week'],
                name='unique_schedule_per_day'
            ),
            models.CheckConstraint(
                condition=models.Q(shift_end__gt=models.F('shift_start')),
                name='schedule_end_after_start'
            )
        ]
    
    def __str__(self):
        return f"{self.employee.first_name} - {self.day_of_week} ({self.shift_start} to {self.shift_end})"

    def clean(self):
        if not self.is_working_day and (self.shift_start or self.shift_end):
            raise ValidationError("Non-working days should not have shift times")

@receiver(pre_save, sender=EmployeeSchedule)
def validate_schedule(sender, instance, **kwargs):
    # Check if the day is marked as a day off in EmploymentDetails
    try:
        employment_details = instance.employee.employment_details
        if employment_details.days_off and instance.day_of_week in employment_details.days_off:
            raise ValidationError(f"Cannot create schedule for {instance.day_of_week} as it's marked as a day off")
    except EmploymentDetails.DoesNotExist:
        pass

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
    time_in = models.TimeField(null=True, blank=True)
    time_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ATTENDANCE_STATUSES)
    overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
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
                condition=models.Q(time_out__isnull=True) | 
                         models.Q(time_out__gt=models.F('time_in')),
                name='time_out_after_time_in'
            ),
            models.CheckConstraint(
                condition=(models.Q(status='A') & models.Q(time_out__isnull=True)) |
                         models.Q(status__in=['O', 'L']),
                name='status_time_consistency'
            )
        ]
    
    def __str__(self):
        return f"{self.employee.first_name} - {self.date} - {self.status}"

    def clean(self):
        if self.employee.organization != self.organization:
            raise ValidationError("Employee must belong to the organization")
        
        # Get the day of week for the attendance date
        day_of_week = self.date.strftime('%A').upper()
        
        try:
            # First try to get the schedule for this specific day
            schedule = self.employee.schedules.get(day_of_week=day_of_week)
            
            if not schedule.is_working_day:
                raise ValidationError(f"{day_of_week} is not a working day for this employee")
                
            if self.time_in and schedule.shift_start:
                if self.time_in < schedule.shift_start:
                    raise ValidationError(f"Time in must be after shift start time ({schedule.shift_start})")
                    
        except EmployeeSchedule.DoesNotExist:
            # If no specific schedule exists, fall back to employment details
            try:
                employment_details = self.employee.employment_details
                if employment_details.shift_start and self.time_in < employment_details.shift_start:
                    raise ValidationError(f"Time in must be after shift start time ({employment_details.shift_start})")
            except EmploymentDetails.DoesNotExist:
                pass

@receiver(pre_save, sender=Attendance)
def validate_attendance(sender, instance, **kwargs):
    if instance.employee.organization != instance.organization:
        raise ValidationError("Employee must belong to the organization")

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


class EmployeeAttendance(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='employee_attendances')
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='employee_attendances')
    date = models.DateField()
    is_present = models.BooleanField(default=False)
    is_late = models.BooleanField(default=False)
    is_absent = models.BooleanField(default=False)
    is_holiday = models.BooleanField(default=False)
    late_minutes = models.IntegerField(default=0)
    working_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['employee']),
            models.Index(fields=['date']),
            models.Index(fields=['is_present']),
            models.Index(fields=['is_late']),
            models.Index(fields=['is_absent']),
            models.Index(fields=['organization', 'date']),  # For organization-wide reports
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['employee', 'date'], 
                name='unique_employee_attendance_stat_per_day'
            ),
            models.CheckConstraint(
                condition=~(models.Q(is_present=True) & models.Q(is_absent=True)),
                name='cannot_be_present_and_absent'
            ),
            models.CheckConstraint(
                condition=models.Q(working_hours__gte=0),
                name='working_hours_non_negative'
            ),
            models.CheckConstraint(
                condition=(models.Q(is_late=False) & models.Q(late_minutes=0)) |
                         models.Q(is_late=True) & models.Q(late_minutes__gt=0),
                name='late_minutes_consistency'
            ),
            models.CheckConstraint(
                condition=(models.Q(is_absent=True) & models.Q(working_hours=0)) |
                         models.Q(is_absent=False),
                name='working_hours_zero_when_absent'
            ),
            models.CheckConstraint(
                condition=models.Q(late_minutes__gte=0) & models.Q(late_minutes__lte=720),
                name='late_minutes_bounds'
            ),
            models.CheckConstraint(
                condition=models.Q(working_hours__lte=24),
                name='working_hours_max_bound'
            ),
        ]

    def __str__(self):
        return f"{self.employee.first_name} - {self.date} - {'Present' if self.is_present else 'Absent'}"

def generate_single_employee_report(employee):
    """
    Generate attendance report for a single employee starting from:
    1. The day after their last recorded attendance, or
    2. Their creation date in the system if they have no previous records and are active
    Records are generated up to yesterday.
    """
    organization = employee.organization
    today = datetime.now().date()
    
    # Only process active employees
    if not employee.is_active:
        logger.info(f"Skipping inactive employee {employee.id}")
        return 0
    
    # Find the most recent attendance record for this employee
    last_record = EmployeeAttendance.objects.filter(employee=employee).aggregate(Max('date'))['date__max']
    
    if not last_record:
        # If no previous record exists, use employee creation date
        # Convert created_at datetime to date object
        creation_date = employee.created_at.date()
        start_date = creation_date
        logger.info(f"No previous records for employee {employee.id}. Using creation date: {creation_date}")
    else:
        # Start from the day after the last record
        start_date = last_record + timedelta(days=1)
        logger.info(f"Continuing from last record for employee {employee.id}: {last_record}")
    
    # Only generate reports up to yesterday
    end_date = today - timedelta(days=1)
    
    # If start date is today or in the future, or if start date is after end date, no reports needed
    if start_date >= today or start_date > end_date:
        return 0
    
    # Rest of the function remains the same...

class HRPreferences(models.Model):
    """
    Model to store organization-specific HR preferences and settings.
    """
    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name='hr_preferences')
    
    # Attendance Settings
    grace_period_minutes = models.PositiveIntegerField(
        default=15,
        help_text=_("Number of minutes allowed after shift start time before marking attendance as late")
    )
    early_check_in_minutes = models.PositiveIntegerField(
        default=45,
        help_text=_("Maximum number of minutes before shift start time when employees can check in")
    )
    allow_overtime = models.BooleanField(
        default=True,
        help_text=_("Whether to allow overtime hours")
    )
    max_overtime_hours = models.PositiveIntegerField(
        default=4,
        help_text=_("Maximum overtime hours allowed per day")
    )
    
    # Leave Settings
    default_annual_leave_days = models.PositiveIntegerField(
        default=20,
        help_text=_("Default number of annual leave days for new employees")
    )
    default_sick_leave_days = models.PositiveIntegerField(
        default=10,
        help_text=_("Default number of sick leave days for new employees")
    )
    allow_leave_carryover = models.BooleanField(
        default=True,
        help_text=_("Whether to allow leave days to be carried over to next year")
    )
    max_leave_carryover_days = models.PositiveIntegerField(
        default=5,
        help_text=_("Maximum number of leave days that can be carried over")
    )
    
    # Working Hours Settings
    standard_working_hours = models.PositiveIntegerField(
        default=8,
        help_text=_("Standard working hours per day")
    )
    standard_working_days = models.PositiveIntegerField(
        default=5,
        help_text=_("Standard working days per week")
    )
    
    # Break Settings
    lunch_break_minutes = models.PositiveIntegerField(
        default=60,
        help_text=_("Standard lunch break duration in minutes")
    )
    tea_break_minutes = models.PositiveIntegerField(
        default=15,
        help_text=_("Standard tea break duration in minutes")
    )
    
    # Notification Settings
    notify_late_attendance = models.BooleanField(
        default=True,
        help_text=_("Whether to notify managers of late attendance")
    )
    notify_early_checkout = models.BooleanField(
        default=True,
        help_text=_("Whether to notify managers of early checkouts")
    )
    notify_leave_requests = models.BooleanField(
        default=True,
        help_text=_("Whether to notify managers of leave requests")
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("HR Preferences")
        verbose_name_plural = _("HR Preferences")
        indexes = [
            models.Index(fields=['organization']),
        ]

    def __str__(self):
        return f"HR Preferences for {self.organization.name}"

    def clean(self):
        if self.grace_period_minutes > 60:
            raise ValidationError(_("Grace period cannot exceed 60 minutes"))
        
        if self.early_check_in_minutes > 120:
            raise ValidationError(_("Early check-in period cannot exceed 120 minutes"))
        
        if self.max_overtime_hours > 8:
            raise ValidationError(_("Maximum overtime hours cannot exceed 8 hours per day"))
        
        if self.standard_working_hours > 24:
            raise ValidationError(_("Standard working hours cannot exceed 24 hours per day"))
        
        if self.standard_working_days > 7:
            raise ValidationError(_("Standard working days cannot exceed 7 days per week"))
        
        if self.lunch_break_minutes > 120:
            raise ValidationError(_("Lunch break cannot exceed 120 minutes"))
        
        if self.tea_break_minutes > 30:
            raise ValidationError(_("Tea break cannot exceed 30 minutes"))

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

