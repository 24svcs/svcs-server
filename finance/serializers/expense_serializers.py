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
    billing_type_display = serializers.CharField(source='get_billing_type_display', read_only=True)
    next_due_date = serializers.DateField(read_only=True)
    is_due_soon = serializers.BooleanField(read_only=True)
    organization_id = serializers.PrimaryKeyRelatedField(source='organization', read_only=True)
    amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        coerce_to_string=True
    )
    total_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        read_only=True,
        coerce_to_string=True,
        help_text="Total amount including prepaid periods"
    )

    class Meta:
        model = Expense
        fields = [
            'id', 'organization_id',
            'category', 'category_display',
            'name', 'amount', 'total_amount',
            'date',
            'expense_type', 'expense_type_display',
            'frequency', 'frequency_display',
            'billing_type', 'billing_type_display',
            'billing_day', 'prepaid_periods',
            'next_due_date', 'is_due_soon',
            'notes'
        ]

class CreateExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Expense
        fields = [
            'category', 'name', 'amount', 'date',
            'expense_type', 'frequency', 'billing_type',
            'billing_day', 'prepaid_periods', 'notes',
        ]
    
    def validate_amount(self, value):
        """Validate amount is positive and has correct decimal places."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        if len(str(value).split('.')[-1]) > 2:
            raise serializers.ValidationError("Amount cannot have more than 2 decimal places.")
        return value

    def validate_prepaid_periods(self, value):
        """Validate prepaid periods."""
        expense_type = self.initial_data.get('expense_type')
        
        # Only validate prepaid_periods for recurring expenses
        if expense_type == 'RECURRING':
            if value < 0:
                raise serializers.ValidationError("Prepaid periods cannot be negative.")
            if value > 120:  # Cap at 10 years for monthly expenses
                raise serializers.ValidationError("Prepaid periods cannot exceed 120 periods.")
        else:
            # Clear prepaid_periods for one-time expenses
            return 0
            
        return value

    def validate_billing_day(self, value):
        """Validate billing day based on frequency and billing type."""
        expense_type = self.initial_data.get('expense_type')
        frequency = self.initial_data.get('frequency')
        billing_type = self.initial_data.get('billing_type')

        # Only validate billing_day for recurring expenses with fixed billing
        if expense_type == 'RECURRING' and billing_type == 'FIXED':
            if value is None:
                raise serializers.ValidationError("Billing day is required for fixed date billing.")
            
            if not isinstance(value, int):
                raise serializers.ValidationError("Billing day must be a number.")

            if frequency == 'MONTHLY' and value > 31:
                raise serializers.ValidationError("Day of month cannot be greater than 31.")
            elif frequency == 'WEEKLY' and value > 7:
                raise serializers.ValidationError("Day of week cannot be greater than 7 (1=Monday, 7=Sunday).")
            elif frequency == 'YEARLY' and value > 366:
                raise serializers.ValidationError("Day of year cannot be greater than 366.")

        return value

    def validate(self, data):
        """Cross-field validation."""
        expense_type = data.get('expense_type')
        frequency = data.get('frequency')
        billing_type = data.get('billing_type')
        billing_day = data.get('billing_day')
        prepaid_periods = data.get('prepaid_periods', 0)
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
            data['billing_type'] = None
            data['billing_day'] = None
            data['prepaid_periods'] = 0

        # Validate recurring expense requirements
        elif expense_type == 'RECURRING':
            if not frequency:
                raise serializers.ValidationError({
                    'frequency': 'Frequency is required for recurring expenses.'
                })
            if not billing_type:
                raise serializers.ValidationError({
                    'billing_type': 'Billing type is required for recurring expenses.'
                })
            
            # Validate billing_day for fixed billing
            if billing_type == 'FIXED' and not billing_day:
                raise serializers.ValidationError({
                    'billing_day': 'Billing day is required for fixed date billing.'
                })
            
            # Clear billing_day for relative billing
            if billing_type == 'RELATIVE':
                data['billing_day'] = None
            
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
