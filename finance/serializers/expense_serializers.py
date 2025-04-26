from rest_framework import serializers
from finance.models import Expense
from django.utils import timezone
from datetime import date
import calendar
from dateutil.relativedelta import relativedelta

class ExpenseSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    expense_type_display = serializers.CharField(source='get_expense_type_display', read_only=True)
    frequency_display = serializers.CharField(source='get_frequency_display', read_only=True)
    recurring_status_display = serializers.CharField(source='get_recurring_status_display', read_only=True)
    next_billing_date = serializers.DateField(source='get_next_billing_date', read_only=True)
    is_due_soon = serializers.BooleanField(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(source='organization', read_only=True)
    can_reactivate = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            'id', 'organization_id', 
            'category', 'category_display',
            'name', 'amount', 'date',
            'expense_type', 'expense_type_display',
            'frequency', 'frequency_display',
            'billing_day',
            'recurring_status', 'recurring_status_display',
            'next_billing_date', 'is_due_soon',
            'end_date', 'notes', 'can_reactivate'
        ]

    def get_can_reactivate(self, obj):
        """Check if this expense can be reactivated."""
        if obj.expense_type != 'RECURRING':
            return False
            
        if obj.recurring_status not in ['CANCELLED', 'PAUSED']:
            return False
            
        # Check if this is the most recent version
        latest_expense = Expense.objects.filter(
            organization=obj.organization,
            name=obj.name,
            expense_type='RECURRING'
        ).order_by('-date').first()
        
        return latest_expense.id == obj.id


    
class CreateExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = [
            'category', 'name', 'amount', 'date',
            'expense_type', 'frequency', 'billing_day',
            'recurring_status', 'end_date', 'notes',
        ]
    
    def validate_amount(self, value):
        """Validate amount is positive and has correct decimal places."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        if len(str(value).split('.')[-1]) > 2:
            raise serializers.ValidationError("Amount cannot have more than 2 decimal places.")
        return value

    def validate_billing_day(self, value):
        """Validate billing day based on frequency."""
        expense_type = self.initial_data.get('expense_type')
        frequency = self.initial_data.get('frequency')

        # Only validate billing_day for recurring expenses
        if expense_type == 'RECURRING':
            if value is None:
                raise serializers.ValidationError("Billing day is required for recurring expenses.")
            
            if not isinstance(value, int):
                raise serializers.ValidationError("Billing day must be a number.")

            if frequency == 'MONTHLY' and value > 31:
                raise serializers.ValidationError("Day of month cannot be greater than 31.")
            elif frequency == 'WEEKLY' and value > 7:
                raise serializers.ValidationError("Day of week cannot be greater than 7.")
            elif frequency == 'YEARLY' and value > 366:
                raise serializers.ValidationError("Day of year cannot be greater than 366.")

        return value

    def validate(self, data):
        """Cross-field validation."""
        expense_type = data.get('expense_type')
        frequency = data.get('frequency')
        billing_day = data.get('billing_day')
        recurring_status = data.get('recurring_status')
        end_date = data.get('end_date')
        start_date = data.get('date')

        today = timezone.now().date()
        current_month_start = date(today.year, today.month, 1)
        current_month_end = date(today.year, today.month, 
                               calendar.monthrange(today.year, today.month)[1])

        # Validate one-time expense date is within current month
        if expense_type == 'ONE_TIME':
            if not (current_month_start <= start_date <= current_month_end):
                raise serializers.ValidationError({
                    'date': f'One-time expenses must be within the current month ({current_month_start} to {current_month_end})'
                })
            # Clear recurring fields
            data['frequency'] = None
            data['billing_day'] = None
            data['recurring_status'] = None
            data['end_date'] = None

        # Validate recurring expense requirements
        elif expense_type == 'RECURRING':
            if not frequency:
                raise serializers.ValidationError({
                    'frequency': 'Frequency is required for recurring expenses.'
                })
            if not billing_day:
                raise serializers.ValidationError({
                    'billing_day': 'Billing day is required for recurring expenses.'
                })
            
            # Set default status for new recurring expenses
            if not recurring_status:
                data['recurring_status'] = 'ACTIVE'

            # Validate start_date is within the current period based on frequency
            if start_date:
                period_start = None
                if frequency == 'MONTHLY':
                    # Get first day of current month
                    period_start = date(today.year, today.month, 1)
                elif frequency == 'WEEKLY':
                    # Get monday of current week
                    period_start = today - relativedelta(days=today.isoweekday() - 1)
                elif frequency == 'BIWEEKLY':
                    # Get monday of current or previous week depending on billing_day
                    current_week_monday = today - relativedelta(days=today.isoweekday() - 1)
                    period_start = current_week_monday - relativedelta(days=7 if today.isoweekday() >= billing_day else 0)
                elif frequency == 'QUARTERLY':
                    # Get first day of current quarter
                    current_quarter = (today.month - 1) // 3
                    period_start = date(today.year, current_quarter * 3 + 1, 1)
                elif frequency == 'BIANNUAL':
                    # Get first day of current half-year
                    current_half = (today.month - 1) // 6
                    period_start = date(today.year, current_half * 6 + 1, 1)
                elif frequency == 'YEARLY':
                    # Get first day of current year
                    period_start = date(today.year, 1, 1)
                elif frequency == 'DAILY':
                    # Daily expenses can be added for any date
                    period_start = None

                if period_start and start_date < period_start:
                    raise serializers.ValidationError({
                        'date': f'Start date for {frequency.lower()} recurring expense cannot be before {period_start}'
                    })

            # Validate end_date is after start_date
            if end_date and start_date and end_date <= start_date:
                raise serializers.ValidationError({
                    'end_date': 'End date must be after start date.'
                })

        return data

    def create(self, validated_data):
        """Create expense with organization from context."""
        organization_id = self.context.get('organization_id')
        if not organization_id:
            raise serializers.ValidationError({
                'organization': 'Organization ID is required.'
            })
            
        validated_data['organization_id'] = organization_id
        return super().create(validated_data)
