from rest_framework import serializers
from django.utils.translation import gettext_lazy as _
from django.utils import timezone as tz
import pytz
from api.libs import validate_phone
from phonenumber_field.modelfields import PhoneNumberField
from human_resources.models import Department, Employee, Position, EmploymentDetails, Attendance, EmployeeSchedule, HRPreferences
from django.db import transaction
from organization.models import Preference
from django.core.cache import cache
from datetime import datetime
from django.db import models
from human_resources.utils.mixins import OrganizationTimezoneMixin


# class OrganizationTimezoneMixin:
#     def _get_organization_timezone(self, organization_id):
#         """
#         Helper method to get the organization's timezone.
#         Uses caching to reduce database queries.
#         """
#         cache_key = f"org_timezone_{organization_id}"
#         cached_timezone = cache.get(cache_key)
        
#         if cached_timezone:
#             return pytz.timezone(str(cached_timezone))  # Convert to string first
        
#         try:
#             org_preferences = Preference.objects.select_related('organization').get(
#                 organization_id=organization_id
#             )
#             # Convert timezone to string first
#             timezone_str = str(org_preferences.timezone)
#             organization_timezone = pytz.timezone(timezone_str)
            
#             # Cache the timezone string
#             cache.set(cache_key, timezone_str, 3600)
            
#             return organization_timezone
#         except Preference.DoesNotExist:
#             # Default to UTC if preferences not found
#             return pytz.UTC

#     def _make_aware(self, naive_datetime, timezone):
#         """Helper method to make a naive datetime timezone-aware"""
#         if isinstance(timezone, str):
#             timezone = pytz.timezone(timezone)
#         return timezone.localize(naive_datetime) if hasattr(timezone, 'localize') else pytz.UTC.localize(naive_datetime)


class ManagerSerializer(serializers.ModelSerializer):
    """Simplified serializer for Employee model, used for nested representations."""
    position = serializers.SerializerMethodField(read_only=True, method_name='get_position')
    class Meta:
        model = Employee
        fields = ['id', 'first_name', 'last_name', 'position']
        
        
    
    def get_position(self, obj):
        try:
            return obj.employment_details.position.title
        except (AttributeError, EmploymentDetails.DoesNotExist):
            return None


class SimpleDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['id', 'name']

class DepartmentSerializer(serializers.ModelSerializer):
    manager = ManagerSerializer(read_only=True)
    total_employees = serializers.SerializerMethodField(read_only=True, method_name='get_total_employees')
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'image_url', 'manager', 'total_employees']
        
        
    def get_total_employees(self, obj):
        return Employee.objects.select_related('employment_details__position__department').filter(employment_details__position__department=obj).only('id').distinct().count()
    
        
        
class CreateDepartmentSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    class Meta:
        model = Department
        fields = ['id', 'name', 'description', 'image_url', 'manager']
    
    def validate_name(self, value):
        if len(value) < 2:
            raise serializers.ValidationError(_("Department name must be at least 2 characters long."))
            
        organization_id = self.context['organization_id']
        if Department.objects.select_related('organization').filter(organization_id=organization_id).filter(name__iexact=value).exists():
            raise serializers.ValidationError(_("A department with this name already exists in this organization."))
        return value
    
    
    
    def create(self, validated_data):
        organization_id = self.context['organization_id']
        return Department.objects.create(organization_id=organization_id, **validated_data)

class UpdateDepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ['name', 'description', 'manager', 'image_url']
    
    def validate_name(self, value):
        organization_id = self.context['organization_id']
        # Get queryset of departments with the same name in this company
        existing_departments = Department.objects.select_related('organization').filter(organization_id=organization_id).filter(name__iexact=value)
        
        # Exclude the current department being updated from the check
        if self.instance:
            existing_departments = existing_departments.exclude(id=self.instance.id)
            
        if existing_departments.exists():
            raise serializers.ValidationError(_("A department with this name already exists in this organization."))
        return value
    
    
    def update(self, instance, validated_data):
        return super().update(instance, validated_data)   
    
    
    
# ================== Position serializers =========================

class PositionSerializer(serializers.ModelSerializer):
    department = SimpleDepartmentSerializer(read_only=True)
    class Meta:
        model = Position
        fields = ['id', 'title', 'description', 'department', 'salary_range_min', 'salary_range_max']
        
        
class CreatePositionSerializer(serializers.ModelSerializer):
    department_id = serializers.IntegerField()
    class Meta:
        model = Position
        fields = ['id', 'title', 'department_id', 'description', 'salary_range_min', 'salary_range_max']
    
    
    def validate_department_id(self, value):
        organization_id = self.context.get('organization_id')

        if not Department.objects.filter(id=value).exists():
            raise serializers.ValidationError(_("Department does not exist."))
        
        if organization_id and not Department.objects.filter(id=value, organization_id=organization_id).exists():
            raise serializers.ValidationError(_("Department does not belong to this organization."))
        
        return value
    
    def validate_title(self, value):
        organization_id = self.context.get('organization_id')

        if Position.objects.filter(department__organization_id=organization_id).filter(title__iexact=value).exists():
            raise serializers.ValidationError(_("A position with this title already exists in this department."))
        
        return value
    
    def validate(self, data):
        # Validate salary range values
        salary_min = data.get('salary_range_min')
        salary_max = data.get('salary_range_max')
        
        if salary_min is not None and salary_min < 0:
            raise serializers.ValidationError(_("Minimum salary range cannot be negative."))
            
        if salary_max is not None and salary_max < 0:
            raise serializers.ValidationError(_("Maximum salary range cannot be negative."))
            
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            raise serializers.ValidationError(_("Minimum salary range cannot be greater than maximum salary range."))
            
        return data

    def create(self, validated_data):
        organization_id = self.context.get('organization_id')
        return Position.objects.create(organization_id=organization_id,**validated_data)


class UpdatePositionSerializer(serializers.ModelSerializer):
    department_id = serializers.IntegerField()
    class Meta:
        model = Position
        fields = ['title', 'description', 'department_id', 'salary_range_min', 'salary_range_max']
        
        
    def validate_department_id(self, value):
        if not Department.objects.filter(id=value).exists():
            raise serializers.ValidationError(_("Department does not exist."))
        
        # Ensure department belongs to the current company
        organization_id = self.context.get('organization_id')
        if organization_id and not Department.objects.filter(id=value, organization_id=organization_id).exists():
            raise serializers.ValidationError(_("Department does not belong to this organization."))

        return value
    

    
    def validate_title(self, value):
        organization_id = self.context['organization_id']
        # Get queryset of positions with the same title in this department
        existing_positions = Position.objects.filter(department__organization_id=organization_id).filter(title__iexact=value)
        
        # Exclude the current position being updated from the check
        if self.instance:
            existing_positions = existing_positions.exclude(id=self.instance.id)
            
        if existing_positions.exists():
            raise serializers.ValidationError(_("A position with this title already exists in this department."))
    
        
        return value
    
    def validate(self, data):
        # Validate salary range values
        salary_min = data.get('salary_range_min')
        salary_max = data.get('salary_range_max')
        
        if salary_min is not None and salary_min < 0:
            raise serializers.ValidationError(_("Minimum salary range cannot be negative."))
            
        if salary_max is not None and salary_max < 0:
            raise serializers.ValidationError(_("Maximum salary range cannot be negative."))
            
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            raise serializers.ValidationError(_("Minimum salary range cannot be greater than maximum salary range."))
            
        return data
    
    def update(self, instance, validated_data):
        return super().update(instance, validated_data)   
    
    
# ================== Employee serializers =========================

class EmployeeSerializer(serializers.ModelSerializer):
    """
    Serializer for the Employee model with basic employee information.
    """
    position = serializers.SerializerMethodField(read_only=True)
    hire_date = serializers.SerializerMethodField(read_only=True)
    employment_status = serializers.SerializerMethodField(read_only=True)
    class Meta:
        model = Employee
        fields = [
            'id', 'first_name', 'last_name', 'gender', 'date_of_birth',
            'phone_number', 'address',
            'position', 'hire_date', 'employment_status'
        ]

    def get_position(self, obj):
        try:
            return obj.employment_details.position.title
        except (AttributeError, EmploymentDetails.DoesNotExist):
            return None
    
    
    def get_hire_date(self, obj):
        try:
            return obj.employment_details.hire_date
        except (AttributeError, EmploymentDetails.DoesNotExist):
            return None
    
    def get_employment_status(self, obj):
        try:
            return obj.employment_details.employment_status
        except (AttributeError, EmploymentDetails.DoesNotExist):
            return None
    

class EmployeeScheduleSerializer(OrganizationTimezoneMixin, serializers.ModelSerializer):
    """
    Serializer for the EmployeeSchedule model.
    """
    class Meta:
        model = EmployeeSchedule
        fields = ['id', 'day_of_week', 'shift_start', 'shift_end', 'is_working_day', 'created_at', 'updated_at']
    
    def validate(self, data):
        """Convert local times to UTC and validate schedule."""
        organization_id = self.context.get('organization_id')
        org_timezone = self._get_organization_timezone(organization_id)
        
        shift_start = data.get('shift_start')
        shift_end = data.get('shift_end')
        
        if shift_start and shift_end:
            # First validate the times in local timezone
            if shift_start >= shift_end:
                raise serializers.ValidationError(_("Shift end time must be after shift start time."))
            
            # Convert to UTC for storage
            today = datetime.now().date()
            
            # Create timezone-aware datetime objects in organization's timezone
            local_start = org_timezone.localize(datetime.combine(today, shift_start))
            local_end = org_timezone.localize(datetime.combine(today, shift_end))
            
            # Convert to UTC for storage
            utc_start = local_start.astimezone(pytz.UTC)
            utc_end = local_end.astimezone(pytz.UTC)
            
            # Update the times in data to UTC
            data['shift_start'] = utc_start.time()
            data['shift_end'] = utc_end.time()
        
        return data
    
    def to_representation(self, instance):
        """
        Convert UTC times to organization's timezone for display
        """
        representation = super().to_representation(instance)
        
        # Get timezone from context
        org_timezone = self.context.get('timezone', pytz.UTC)
        
        # Use today's date for conversion
        today = datetime.now(pytz.UTC).date()
        
        # Convert shift times if they exist
        if representation.get('shift_start'):
            # Create UTC datetime
            utc_start = pytz.UTC.localize(
                datetime.combine(today, instance.shift_start)
            )
            # Convert to local time for display
            local_start = utc_start.astimezone(org_timezone)
            representation['shift_start'] = local_start.time().isoformat()
            
        if representation.get('shift_end'):
            # Create UTC datetime
            utc_end = pytz.UTC.localize(
                datetime.combine(today, instance.shift_end)
            )
            # Convert to local time for display
            local_end = utc_end.astimezone(org_timezone)
            representation['shift_end'] = local_end.time().isoformat()
        
        return representation


class EmploymentDetailsSerializer(serializers.ModelSerializer):
    """
    Serializer for the EmploymentDetails model with employment-related information.
    """
    position = serializers.SerializerMethodField(read_only=True)
    schedules = EmployeeScheduleSerializer(many=True, read_only=True)
    
    class Meta:
        model = EmploymentDetails
        fields = [
            'position', 'hire_date', 'employment_status', 'salary',
            'shift_start', 'shift_end', 'days_off', 'annual_leave_days',
            'sick_leave_days', 'schedules', 'created_at', 'updated_at'
        ]
        
    def validate_days_off(self, value):
        """Validate that days off are valid day names."""
        if value:
            valid_days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
            for day in value:
                if day not in valid_days:
                    raise serializers.ValidationError(_(f"Invalid day '{day}'. Must be one of: {', '.join(valid_days)}"))
        return value
    
    def get_position(self, obj):
        """Return the position title from the position object."""
        return obj.position.title if obj.position else None

class EmployeeWithDetailsSerializer(EmployeeSerializer):
    """
    Combined serializer that includes both Employee and EmploymentDetails information.
    """
    employment_details = EmploymentDetailsSerializer(read_only=True)
    
    class Meta(EmployeeSerializer.Meta):
        fields = EmployeeSerializer.Meta.fields + ['employment_details']


class CreateEmployeeSerializer(OrganizationTimezoneMixin, serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    phone_number = PhoneNumberField(validators=[validate_phone.validate_phone])
    position_id = serializers.IntegerField(write_only=True)
    hire_date = serializers.DateField(write_only=True)
    employment_status = serializers.ChoiceField(choices=EmploymentDetails.EMPLOYMENT_STATUS, default='FT', write_only=True)
    salary = serializers.DecimalField(max_digits=10, decimal_places=2, required=True, write_only=True)
    shift_start = serializers.TimeField(required=False, write_only=True)  # Made optional
    shift_end = serializers.TimeField(required=False, write_only=True)    # Made optional
    days_off = serializers.JSONField(required=False, allow_null=True, write_only=True)
    annual_leave_days = serializers.IntegerField(default=0, required=False, write_only=True)
    sick_leave_days = serializers.IntegerField(default=0, required=False, write_only=True)
    schedules = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        write_only=True
    )
    
    class Meta:
        model = Employee
        fields = [
            'id', 'first_name', 'last_name', 'gender', 'date_of_birth', 
            'phone_number', 'address', 'emergency_contact_name', 'emergency_contact_phone',
            # Employment details fields
            'position_id', 'hire_date', 'employment_status', 'salary',
            'shift_start', 'shift_end', 'days_off', 'annual_leave_days', 'sick_leave_days',
            'schedules'
        ]
  
    def validate_position_id(self, value):
        organization_id = self.context['organization_id']
        # Check if the position belongs to a department in the current organization
        if not Position.objects.select_related('department').filter(
            id=value,
            department__organization_id=organization_id
        ).exists():
            raise serializers.ValidationError(_("This position does not belong to a department in this organization."))
        return value
    
    def validate_gender(self, value):
        if value not in [choice[0] for choice in Employee.GENDER_CHOICES]:
            raise serializers.ValidationError(_("Invalid gender."))
        return value
    
    def validate_hire_date(self, value):
        """Validate hire date against UTC now"""
        if value > tz.now().date():
            raise serializers.ValidationError(_("Hire date cannot be in the future."))
        return value
    
    def validate_employment_status(self, value):
        if value not in [choice[0] for choice in EmploymentDetails.EMPLOYMENT_STATUS]:
            raise serializers.ValidationError(_("Invalid employment status."))
        return value
    
    def validate_date_of_birth(self, value):
        """Validate date of birth against UTC now"""
        today = tz.now().date()
        if value > today:
            raise serializers.ValidationError(_("Date of birth cannot be in the future."))
        
        min_age_date = today.replace(year=today.year - 16)
        if value > min_age_date:
            raise serializers.ValidationError(_("Employee must be at least 16 years old."))
        
        return value
    
    def validate_salary(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(_("Salary cannot be negative."))
        return value
    
    def validate_days_off(self, value):
        if value:
            valid_days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
            for day in value:
                if day not in valid_days:
                    raise serializers.ValidationError(_(f"Invalid day '{day}'. Must be one of: {', '.join(valid_days)}"))
        return value
    
    def validate_schedules(self, value):
        """Validate the schedule data"""
        for schedule in value:
            # Check required fields
            required_fields = {'day_of_week', 'is_working_day'}
            if not all(field in schedule for field in required_fields):
                raise serializers.ValidationError(
                    _("Each schedule must contain day_of_week and is_working_day")
                )
            
            # Validate day_of_week
            if schedule['day_of_week'] not in dict(EmployeeSchedule.DAYS_OF_WEEK):
                raise serializers.ValidationError(
                    _(f"Invalid day_of_week. Must be one of: {', '.join(dict(EmployeeSchedule.DAYS_OF_WEEK).keys())}")
                )
            
            # If it's a working day, validate shift times
            if schedule.get('is_working_day'):
                if 'shift_start' not in schedule or 'shift_end' not in schedule:
                    raise serializers.ValidationError(
                        _("Working days must have both shift_start and shift_end times")
                    )
                
                try:
                    # Parse time strings
                    shift_start = datetime.strptime(schedule['shift_start'], '%H:%M:%S').time()
                    shift_end = datetime.strptime(schedule['shift_end'], '%H:%M:%S').time()
                    
                    # Update the schedule with parsed times
                    schedule['shift_start'] = shift_start
                    schedule['shift_end'] = shift_end
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        _("Invalid time format. Use HH:MM:SS format.")
                    )
            else:
                # Remove shift times for non-working days
                schedule.pop('shift_start', None)
                schedule.pop('shift_end', None)
        
        return value
    
    def validate(self, data):
        # Convert shift times from local to UTC
        organization_id = self.context['organization_id']
        org_timezone = self._get_organization_timezone(organization_id)
        
        shift_start = data.get('shift_start')
        shift_end = data.get('shift_end')
        
        if shift_start and shift_end:
            # First validate the times in local timezone
            if shift_start >= shift_end:
                raise serializers.ValidationError(_("Shift end time must be after shift start time."))
            
            # Convert to UTC for storage
            today = datetime.now().date()
            
            # Create timezone-aware datetime objects in organization's timezone
            local_start = org_timezone.localize(datetime.combine(today, shift_start))
            local_end = org_timezone.localize(datetime.combine(today, shift_end))
            
            # Convert to UTC for storage
            utc_start = local_start.astimezone(pytz.UTC)
            utc_end = local_end.astimezone(pytz.UTC)
            
            # Update the times in data to UTC
            data['shift_start'] = utc_start.time()
            data['shift_end'] = utc_end.time()
        
        # Validate salary against position salary range
        salary = data.get('salary')
        position_id = data.get('position_id')
        
        if salary is not None and position_id:
            try:
                position = Position.objects.get(id=position_id)
                
                # Check if position has defined salary ranges
                if position.salary_range_min is not None and salary < position.salary_range_min:
                    raise serializers.ValidationError(_("Salary cannot be lower than the position's minimum salary range."))
                
                if position.salary_range_max is not None and salary > position.salary_range_max:
                    raise serializers.ValidationError(_("Salary cannot be higher than the position's maximum salary range."))
                    
            except Position.DoesNotExist:
                pass  # This will be caught by position_id validator
        
        return data
    
    def create(self, validated_data):
        organization_id = self.context['organization_id']
        
        # Extract employment details data
        employment_details_fields = [
            'position_id', 'hire_date', 'employment_status', 'salary',
            'shift_start', 'shift_end', 'days_off', 'annual_leave_days', 'sick_leave_days'
        ]
        
        employment_details_data = {}
        for field in employment_details_fields:
            if field in validated_data:
                employment_details_data[field] = validated_data.pop(field)
        
        # Get position object from position_id
        if 'position_id' in employment_details_data:
            position_id = employment_details_data.pop('position_id')
            try:
                position = Position.objects.get(id=position_id)
                employment_details_data['position'] = position
            except Position.DoesNotExist:
                raise serializers.ValidationError(_("Position does not exist."))
        
        # Extract schedules data
        schedules_data = validated_data.pop('schedules', [])
                
        with transaction.atomic():
            # Create employee
            employee = Employee.objects.create(organization_id=organization_id, **validated_data)
            
            # Create employment details
            employment_details = EmploymentDetails.objects.create(employee=employee, **employment_details_data)
            
            # Create schedules if provided
            for schedule_data in schedules_data:
                EmployeeSchedule.objects.create(employee=employee, **schedule_data)
        
        return employee
    
    def to_representation(self, instance):
        # After creating, return the full employee data with employment details
        serializer = EmployeeWithDetailsSerializer(instance, context=self.context)
        return serializer.data


class UpdateEmployeeSerializer(serializers.ModelSerializer):
    phone_number = PhoneNumberField(validators=[validate_phone.validate_phone]) 
    id = serializers.UUIDField(read_only=True)
    
    class Meta:
        model = Employee
        fields = ['id', 'first_name', 'last_name', 'gender', 'date_of_birth', 
                 'phone_number', 'address', 'emergency_contact_name', 'emergency_contact_phone']
    
    def validate_gender(self, value):
        if value not in [choice[0] for choice in Employee.GENDER_CHOICES]:
            raise serializers.ValidationError(_("Invalid gender."))
        return value
    
    def validate_date_of_birth(self, value):
        today = tz.now().date()
        if value > today:
            raise serializers.ValidationError(_("Date of birth cannot be in the future."))
        
        # Check if employee is at least 16 years old    
        min_age_date = today.replace(year=today.year - 16)
        if value > min_age_date:
            raise serializers.ValidationError(_("Employee must be at least 16 years old."))
        return value
    
    def update(self, instance, validated_data):
        return super().update(instance, validated_data)


class UpdateEmploymentDetailsSerializer(OrganizationTimezoneMixin, serializers.ModelSerializer):
    position_id = serializers.IntegerField()
    schedules = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )
    
    class Meta:
        model = EmploymentDetails
        fields = [
            'position_id', 'hire_date', 'employment_status', 'salary',
            'shift_start', 'shift_end', 'days_off', 'annual_leave_days', 'sick_leave_days',
            'schedules'
        ]

    def validate_position_id(self, value):
        organization_id = self.context['organization_id']
        # Check if the position belongs to a department in the current company
        if not Position.objects.filter(
            id=value,
            department__organization_id=organization_id
        ).exists():
            raise serializers.ValidationError(_("This position does not belong to a department in this organization."))
        return value
    
    def validate_hire_date(self, value):
        """Validate hire date against UTC now"""
        if value > tz.now().date():
            raise serializers.ValidationError(_("Hire date cannot be in the future."))
        return value
    
    def validate_employment_status(self, value):
        if value not in [choice[0] for choice in EmploymentDetails.EMPLOYMENT_STATUS]:
            raise serializers.ValidationError(_("Invalid employment status."))
        return value
    
    def validate_salary(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError(_("Salary cannot be negative."))
        return value
    
    def validate_days_off(self, value):
        if value:
            valid_days = ['MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY', 'SUNDAY']
            for day in value:
                if day not in valid_days:
                    raise serializers.ValidationError(_(f"Invalid day '{day}'. Must be one of: {', '.join(valid_days)}"))
        return value
    
    def validate_schedules(self, value):
        """Validate the schedule data"""
        for schedule in value:
            # Check required fields
            required_fields = {'day_of_week', 'is_working_day'}
            if not all(field in schedule for field in required_fields):
                raise serializers.ValidationError(
                    _("Each schedule must contain day_of_week and is_working_day")
                )
            
            # Validate day_of_week
            if schedule['day_of_week'] not in dict(EmployeeSchedule.DAYS_OF_WEEK):
                raise serializers.ValidationError(
                    _(f"Invalid day_of_week. Must be one of: {', '.join(dict(EmployeeSchedule.DAYS_OF_WEEK).keys())}")
                )
            
            # If it's a working day, validate shift times
            if schedule.get('is_working_day'):
                if 'shift_start' not in schedule or 'shift_end' not in schedule:
                    raise serializers.ValidationError(
                        _("Working days must have both shift_start and shift_end times")
                    )
                
                try:
                    # Parse time strings
                    shift_start = datetime.strptime(schedule['shift_start'], '%H:%M:%S').time()
                    shift_end = datetime.strptime(schedule['shift_end'], '%H:%M:%S').time()
                    
                    # Update the schedule with parsed times
                    schedule['shift_start'] = shift_start
                    schedule['shift_end'] = shift_end
                except (ValueError, TypeError):
                    raise serializers.ValidationError(
                        _("Invalid time format. Use HH:MM:SS format.")
                    )
            else:
                # Remove shift times for non-working days
                schedule.pop('shift_start', None)
                schedule.pop('shift_end', None)
        
        return value

    def validate(self, data):
        # Convert shift times from local to UTC
        organization_id = self.context['organization_id']
        org_timezone = self._get_organization_timezone(organization_id)
        
        shift_start = data.get('shift_start')
        shift_end = data.get('shift_end')
        
        # If one is provided but not the other, get the existing value
        if shift_start and not shift_end and self.instance:
            shift_end = self.instance.shift_end
        elif shift_end and not shift_start and self.instance:
            shift_start = self.instance.shift_start
        
        if shift_start and shift_end:
            # First validate the times in local timezone
            if shift_start >= shift_end:
                raise serializers.ValidationError(_("Shift end time must be after shift start time."))
            
            # Convert to UTC
            # Use today's date for conversion
            today = datetime.now().date()
            
            # Create timezone-aware datetime objects in organization's timezone
            local_start = org_timezone.localize(datetime.combine(today, shift_start))
            local_end = org_timezone.localize(datetime.combine(today, shift_end))
            
            # Convert to UTC
            utc_start = local_start.astimezone(pytz.UTC)
            utc_end = local_end.astimezone(pytz.UTC)
            
            # Update the times in data to UTC
            data['shift_start'] = utc_start.time()
            data['shift_end'] = utc_end.time()
        
        # Validate salary against position salary range
        salary = data.get('salary')
        position_id = data.get('position_id')
        
        if salary is not None and position_id:
            try:
                position = Position.objects.get(id=position_id)
                
                # Check if position has defined salary ranges
                if position.salary_range_min is not None and salary < position.salary_range_min:
                    raise serializers.ValidationError(_("Salary cannot be lower than the position's minimum salary range."))
                
                if position.salary_range_max is not None and salary > position.salary_range_max:
                    raise serializers.ValidationError(_("Salary cannot be higher than the position's maximum salary range."))
                    
            except Position.DoesNotExist:
                pass  # This will be caught by position_id validator
        
        return data
    
    def update(self, instance, validated_data):
        schedules_data = validated_data.pop('schedules', [])
        
        # Update employment details
        instance = super().update(instance, validated_data)
        
        # Update schedules
        if schedules_data:
            # Delete existing schedules
            instance.employee.schedules.all().delete()
            # Create new schedules
            for schedule_data in schedules_data:
                EmployeeSchedule.objects.create(employee=instance.employee, **schedule_data)
        
        return instance
        
        
# ================== Attendance serializers =========================

class AttendanceSerializer(OrganizationTimezoneMixin, serializers.ModelSerializer):
    """
    Serializer for the Attendance model with employee attendance information.
    """
    employee_name = serializers.SerializerMethodField()
    time_in_local = serializers.SerializerMethodField()
    time_out_local = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = ['id', 'employee', 'employee_name', 'date', 'time_in', 'time_out', 
                 'time_in_local', 'time_out_local', 'status']
    
    def get_time_in_local(self, obj):
        """Convert UTC time_in to organization's local time"""
        if not obj.time_in:
            return None
            
        org_timezone = self._get_organization_timezone(obj.organization_id)
        utc_dt = datetime.combine(obj.date, obj.time_in)
        utc_dt = pytz.UTC.localize(utc_dt)
        local_dt = utc_dt.astimezone(org_timezone)
        return local_dt.time()

    def get_time_out_local(self, obj):
        """Convert UTC time_out to organization's local time"""
        if not obj.time_out:
            return None
            
        org_timezone = self._get_organization_timezone(obj.organization_id)
        utc_dt = datetime.combine(obj.date, obj.time_out)
        utc_dt = pytz.UTC.localize(utc_dt)
        local_dt = utc_dt.astimezone(org_timezone)
        return local_dt.time()

    def get_employee_name(self, obj):
        """Get the full name of the employee."""
        return f"{obj.employee.first_name} {obj.employee.last_name}"
    
    

class CheckInOutSerializer(OrganizationTimezoneMixin, serializers.Serializer):
    """
    Serializer for handling employee check-in and check-out operations.
    This serializer handles both creating new attendance records (check-in)
    and updating existing records (check-out).
    """
    employee_id = serializers.CharField()
    note = serializers.CharField(required=False, allow_blank=True, default='')
    
    def validate_employee_id(self, value):
        """Validate that the employee exists and belongs to the organization."""
        organization_id = self.context.get('organization_id')
        
        try:
            Employee.objects.get(id=value, organization_id=organization_id)
        except Employee.DoesNotExist:
            raise serializers.ValidationError(_("Invalid employee ID."))
        
        return value
    
    def _get_current_datetime(self):
        """Helper method to get the current UTC datetime."""
        return tz.now()
    
    def _handle_check_in(self, employee_id, current_datetime, note, organization_id):
        """
        Helper method to handle employee check-in.
        Creates a new attendance record with appropriate status.
        """
        employee = Employee.objects.get(id=employee_id)
        
        # Get the day of week for the current date
        day_of_week = current_datetime.strftime('%A').upper()
        
        # Get HR preferences with fallback values
        try:
            hr_preferences = employee.organization.hr_preferences
            grace_period = hr_preferences.grace_period_minutes
            early_check_in_limit = hr_preferences.early_check_in_minutes
        except HRPreferences.DoesNotExist:
            # Fallback values if HR preferences not set
            grace_period = 15  # Default grace period
            early_check_in_limit = 45  # Default early check-in limit
        
        try:
            # First try to get the schedule for this specific day
            schedule = employee.schedules.get(day_of_week=day_of_week)
            
            if not schedule.is_working_day:
                raise serializers.ValidationError(_(
                    f"You cannot check in because {day_of_week} is not a working day for you."
                ))
            
            # Compare times directly in UTC
            current_utc_time = current_datetime.time()
            
            # Check if trying to check in too early
            if schedule.shift_start:
                from datetime import datetime, timedelta
                
                # Calculate earliest allowed check-in time based on HR preferences
                earliest_check_in = (datetime.combine(current_datetime.date(), schedule.shift_start) - 
                                   timedelta(minutes=early_check_in_limit)).time()
                
                if current_utc_time < earliest_check_in:
                    raise serializers.ValidationError(_(
                        f"You cannot check in more than {early_check_in_limit} minutes before your shift start time."
                    ))
                
                # Determine status based on shift start time and grace period
                status = Attendance.ATTENDANCE_ON_TIME
                if current_utc_time > schedule.shift_start:
                    # Calculate late threshold using grace period from HR preferences
                    late_threshold = (datetime.combine(current_datetime.date(), schedule.shift_start) + 
                                    timedelta(minutes=grace_period)).time()
                    
                    if current_utc_time > late_threshold:
                        status = Attendance.ATTENDANCE_LATE
                    
        except EmployeeSchedule.DoesNotExist:
            # If no specific schedule exists, fall back to employment details
            try:
                employment_details = employee.employment_details
                
                if employment_details.shift_start is None or employment_details.shift_end is None:
                    raise serializers.ValidationError(_(
                        "You cannot check in because your shift period is not defined. Please contact an administrator."
                    ))
                
                # Compare times directly in UTC
                current_utc_time = current_datetime.time()
                
                # Check if trying to check in too early
                if employment_details.shift_start:
                    from datetime import datetime, timedelta
                    
                    # Calculate earliest allowed check-in time based on HR preferences
                    earliest_check_in = (datetime.combine(current_datetime.date(), employment_details.shift_start) - 
                                       timedelta(minutes=early_check_in_limit)).time()
                    
                    if current_utc_time < earliest_check_in:
                        raise serializers.ValidationError(_(
                            f"You cannot check in more than {early_check_in_limit} minutes before your shift start time."
                        ))
                    
                    # Determine status based on shift start time and grace period
                    status = Attendance.ATTENDANCE_ON_TIME
                    if current_utc_time > employment_details.shift_start:
                        # Calculate late threshold using grace period from HR preferences
                        late_threshold = (datetime.combine(current_datetime.date(), employment_details.shift_start) + 
                                        timedelta(minutes=grace_period)).time()
                        
                        if current_utc_time > late_threshold:
                            status = Attendance.ATTENDANCE_LATE
                        
            except EmploymentDetails.DoesNotExist:
                raise serializers.ValidationError(_(
                    "You cannot check in because you don't have employment details recorded. Please contact an administrator."
                ))
        
        # Create new attendance record using UTC datetime
        attendance = Attendance.objects.create(
            employee=employee,
            date=current_datetime.date(),  # Store UTC date
            time_in=current_datetime.time(),  # Store UTC time
            status=status,
            note=note,
            organization_id=organization_id
        )
        
        return attendance
    
    def _handle_check_out(self, attendance, current_datetime, note, employee_id):
        """
        Helper method to handle employee check-out.
        Updates the existing attendance record with check-out time.
        """
        # Get the day of week for the attendance date
        day_of_week = attendance.date.strftime('%A').upper()
        
        try:
            # First try to get the schedule for this specific day
            schedule = attendance.employee.schedules.get(day_of_week=day_of_week)
            
            # Compare times directly in UTC
            current_utc_time = current_datetime.time()
            
            if schedule.shift_end and current_utc_time < schedule.shift_end:
                raise serializers.ValidationError(_(
                    "You cannot check out before your scheduled shift end time. Please contact an administrator."
                ))
                
        except EmployeeSchedule.DoesNotExist:
            # If no specific schedule exists, fall back to employment details
            try:
                employment_details = attendance.employee.employment_details
                
                # Compare times directly in UTC
                current_utc_time = current_datetime.time()
                
                if employment_details.shift_end and current_utc_time < employment_details.shift_end:
                    raise serializers.ValidationError(_(
                        "You cannot check out before your scheduled shift end time. Please contact an administrator."
                    ))
                    
            except EmploymentDetails.DoesNotExist:
                pass
        
        # Calculate work duration using UTC times
        from datetime import datetime, date, timedelta
        
        dummy_date = date(2000, 1, 1)
        dt_in = datetime.combine(dummy_date, attendance.time_in)
        dt_out = datetime.combine(dummy_date, current_datetime.time())
        
        if dt_out < dt_in:
            dt_out = datetime.combine(dummy_date + timedelta(days=1), current_datetime.time())
        
        duration = (dt_out - dt_in).total_seconds() / 3600
        
        # Update time_out with UTC time
        attendance.time_out = current_datetime.time()
        
        if note:
            attendance.note = note
            
        attendance.save()
        return attendance
    
    def save(self):
        """
        Save method that handles both check-in and check-out operations.
        """
        employee_id = self.validated_data.get('employee_id')
        note = self.validated_data.get('note', '')
        organization_id = self.context.get('organization_id')
        
        # Get current UTC datetime
        current_datetime = self._get_current_datetime()
        
        # Check if attendance record exists for today (using UTC date)
        try:
            attendance = Attendance.objects.get(
                employee_id=employee_id, 
                date=current_datetime.date()
            )
            
            if attendance.time_out is not None:
                raise serializers.ValidationError(_("Employee has already checked out today."))
            
            return self._handle_check_out(attendance, current_datetime, note, employee_id)
            
        except Attendance.DoesNotExist:
            return self._handle_check_in(employee_id, current_datetime, note, organization_id)


class AdminAttendanceSerializer(OrganizationTimezoneMixin, serializers.ModelSerializer):
    """
    Serializer for administrators to manage attendance records.
    """
    time_in = serializers.TimeField(required=False)
    time_out = serializers.TimeField(required=False)

    class Meta:
        model = Attendance
        fields = ['id', 'employee', 'date', 'time_in', 'time_out', 'status', 'note']
    
    def validate(self, data):
        """Convert any local times to UTC before validation"""
        organization_id = self.context.get('organization_id')
        org_timezone = self._get_organization_timezone(organization_id)
        
        # Convert time_in and time_out to UTC if provided
        time_in = data.get('time_in')
        time_out = data.get('time_out')
        date = data.get('date') or (self.instance.date if self.instance else None)

        if time_in:
            # Create local datetime and convert to UTC
            local_dt = self._make_aware(datetime.combine(date, time_in), org_timezone)
            utc_dt = local_dt.astimezone(pytz.UTC)
            data['time_in'] = utc_dt.time()

        if time_out:
            # Create local datetime and convert to UTC
            local_dt = self._make_aware(datetime.combine(date, time_out), org_timezone)
            utc_dt = local_dt.astimezone(pytz.UTC)
            data['time_out'] = utc_dt.time()

        # Validate times in UTC
        if data.get('time_out') and data.get('time_in'):
            if data['time_out'] <= data['time_in']:
                raise serializers.ValidationError(_("Check-out time must be after check-in time."))
        
        # If status is being updated to 'half_day', validate work duration
        if data.get('status') == 'half_day' and data.get('time_in') and data.get('time_out'):
            from datetime import datetime, date, timedelta
            
            # Create datetime objects for comparison
            dummy_date = date(2000, 1, 1)
            dt_in = datetime.combine(dummy_date, data['time_in'])
            dt_out = datetime.combine(dummy_date, data['time_out'])
            
            # If time_out is earlier than time_in (overnight shift), add a day to time_out
            if dt_out < dt_in:
                dt_out = datetime.combine(dummy_date + timedelta(days=1), data['time_out'])
            
            # Calculate duration in hours
            duration = (dt_out - dt_in).total_seconds() / 3600
            
            # Warn if half_day status doesn't match duration
            if duration >= 4:
                self.context['warnings'] = [
                    _("Work duration is 4 hours or more, but status is set to 'half_day'.")
                ]
        
        return data
        
        
        
        
        
class EmployeeAttendanceStatsSerializer(serializers.Serializer):
    """
    Serializer for employee attendance statistics.
    Uses annotated fields from the queryset for better performance.
    """
    employee_id = serializers.CharField(source='id', read_only=True)
    employee_name = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()
    total_days = serializers.IntegerField()
    present_days = serializers.IntegerField()
    absent_days = serializers.IntegerField()
    late_days = serializers.IntegerField()
    total_late_minutes = serializers.IntegerField()
    average_late_minutes = serializers.SerializerMethodField()
    total_working_hours = serializers.FloatField()
    average_working_hours = serializers.SerializerMethodField()
    attendance_rate = serializers.SerializerMethodField()
    late_rate = serializers.SerializerMethodField()
    last_attendance = serializers.DateField(source='last_attendance_date')
    last_absence = serializers.DateField(source='last_absence_date')
    perfect_attendance_days = serializers.IntegerField()
    overtime_hours = serializers.SerializerMethodField()
    early_leaves = serializers.IntegerField()

    def get_employee_name(self, obj):
        return f"{obj.first_name} {obj.last_name}"

    def get_department(self, obj):
        try:
            return obj.employment_details.position.department.name
        except (AttributeError, EmploymentDetails.DoesNotExist):
            return None

    def get_position(self, obj):
        try:
            return obj.employment_details.position.title
        except (AttributeError, EmploymentDetails.DoesNotExist):
            return None

    def get_average_late_minutes(self, obj):
        if not obj.late_days or not obj.total_late_minutes:
            return 0
        return round(obj.total_late_minutes / obj.late_days, 2)

    def get_average_working_hours(self, obj):
        if not obj.present_days or not obj.total_working_hours:
            return 0
        return round(obj.total_working_hours / obj.present_days, 2)

    def get_attendance_rate(self, obj):
        if not obj.total_days:
            return 0
        return round((obj.present_days / obj.total_days) * 100, 2)

    def get_late_rate(self, obj):
        if not obj.present_days:
            return 0
        return round((obj.late_days / obj.present_days) * 100, 2)

    def get_overtime_hours(self, obj):
        if not obj.total_working_hours or not obj.present_days:
            return 0
        standard_hours = 8 * obj.present_days
        overtime = max(0, obj.total_working_hours - standard_hours)
        return round(overtime, 2)

        
