from django.db.models import ExpressionWrapper, Sum, F, Value, Q, DecimalField
from django.db.models.functions import Coalesce
from decimal import Decimal


def annotate_invoice_calculations(queryset):
    """
    Annotate an invoice queryset with calculated fields for totals, payments, and balances.
    
    This utility consolidates complex annotations used throughout the app,
    reducing code duplication and ensuring consistent calculations.
    
    Args:
        queryset: The Invoice queryset to annotate
        
    Returns:
        Annotated queryset with the following fields:
        - calculated_total: Total invoice amount including tax
        - completed_payments_sum: Sum of completed payments
        - calculated_balance: Remaining balance (total - payments)
        - pending_payments_sum: Sum of pending payments
    """
    return queryset.annotate(
        calculated_total=ExpressionWrapper(
            Coalesce(
                Sum(
                    F('items__quantity') * F('items__unit_price'),
                    output_field=DecimalField(max_digits=10, decimal_places=2)
                ),
                Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
            ) * (1 + F('tax_rate') / 100),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        ),
        completed_payments_sum=Coalesce(
            Sum(
                'payments__amount',
                filter=Q(payments__status='COMPLETED'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
            Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
        ),
        calculated_balance=ExpressionWrapper(
            F('calculated_total') - F('completed_payments_sum'),
            output_field=DecimalField(max_digits=10, decimal_places=2)
        ),
        pending_payments_sum=Coalesce(
            Sum(
                'payments__amount',
                filter=Q(payments__status='PENDING'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
            Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
        )
    )


def calculate_payment_statistics(queryset):
    """
    Calculate statistics for payment data.
    
    Args:
        queryset: The Payment queryset to analyze
        
    Returns:
        Dictionary with payment statistics
    """
    
    return queryset.aggregate(
        completed_payments=Sum('amount', filter=Q(status='COMPLETED'), default=0),
        pending_payments=Sum('amount', filter=Q(status='PENDING'), default=0),
        failed_payments=Sum('amount', filter=Q(status='FAILED'), default=0),
        refunded_payments=Sum('amount', filter=Q(status='REFUNDED'), default=0),
    ) 