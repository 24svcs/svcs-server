from django_moncash.utils import init_payment, verify_payment, consume_payment

def process_moncash_payment(request, amount, return_url='http://127.0.0.1:8000/api/moncash-return/', order_id=None, meta_data=None,  transaction_fee=0, total_amount=0):
    payment = init_payment(request, total_amount, return_url, order_id, meta_data)
    
    # Extract relevant data from payment response
    response_data = {
        'payment_url': payment['payment_url'],
        'transaction_id': payment['transaction'].id if payment.get('transaction') else None,
        'amount': amount,
        'order_id': order_id,
        'transaction_fee': transaction_fee,
        'total_amount': total_amount
    }
    
    return response_data

def verify_moncash_payment(request, moncash_transaction_id=None):
    """
    Verify a MonCash payment transaction.
    Returns the payment data if verified, None if verification fails.
    """
    try:
        payment = verify_payment(request, moncash_transaction_id)
        if payment and payment.get('transaction'):
            return payment
        return None
    except Exception as e:
        print(f"Error verifying payment: {str(e)}")
        return None

def consume_moncash_payment(request, moncash_transaction_id=None):
    """
    Consume a MonCash payment transaction.
    Returns:
    {
        'success': bool,
        'error': str,  # Only present if success is False
        'payment': dict  # Only present if transaction was found
    }
    """
    try:
        result = consume_payment(request, moncash_transaction_id)
        
        # If already consumed, return success=False but include payment data
        if result.get('error') == 'USED' and result.get('payment'):
            return {
                'success': False,
                'error': 'USED',
                'payment': result['payment']
            }
        
        # If payment not found
        if result.get('error') == 'NOT_FOUND':
            return {
                'success': False,
                'error': 'NOT_FOUND'
            }
        
        # If successfully consumed
        if result.get('payment'):
            return {
                'success': True,
                'payment': result['payment']
            }
        
        return {
            'success': False,
            'error': 'UNKNOWN_ERROR'
        }
        
    except Exception as e:
        print(f"Error consuming payment: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }



MONCASH_ONLINE_TRANSACTION_FEES = [
    {
        'AMOUNT_FROM': 20,
        'AMOUNT_TO': 99,
        'FEE': 5
    },
    {
        'AMOUNT_FROM': 100,
        'AMOUNT_TO': 249,
        'FEE': 5
    },
    {
        'AMOUNT_FROM': 250,
        'AMOUNT_TO': 499,
        'FEE': 10
    },
    {
        'AMOUNT_FROM': 500,
        'AMOUNT_TO': 999,
        'FEE': 20
    },
    {
        'AMOUNT_FROM': 1000,
        'AMOUNT_TO': 1999,
        'FEE': 40
    },
    {
        'AMOUNT_FROM': 2000,
        'AMOUNT_TO': 3999,
        'FEE': 60
    },
    {
        'AMOUNT_FROM': 4000,
        'AMOUNT_TO': 7999,
        'FEE': 90
    },
    {
        'AMOUNT_FROM': 8000,
        'AMOUNT_TO': 11999,
        'FEE': 125
    },
    {
        'AMOUNT_FROM': 12000,
        'AMOUNT_TO': 19999,
        'FEE': 145
    },
    {
        'AMOUNT_FROM': 20000,
        'AMOUNT_TO': 39999,
        'FEE': 170
    },
    {
        'AMOUNT_FROM': 40000,
        'AMOUNT_TO': 59999,
        'FEE': 200
    },
    
]

MONCASH_MAX_AMOUNT = 59999
MAX_TRANSACTION_FEE = 200

def get_moncash_online_transaction_fee(amount):
    for fee in MONCASH_ONLINE_TRANSACTION_FEES:
        if amount >= fee['AMOUNT_FROM'] and amount <= fee['AMOUNT_TO']:
            return fee['FEE']
    return MAX_TRANSACTION_FEE

def get_moncash_online_transaction_fee_percentage(amount):
    return get_moncash_online_transaction_fee(amount) / amount

def get_moncash_online_transaction_fee_percentage_range():
    return [get_moncash_online_transaction_fee_percentage(fee['AMOUNT_FROM']) for fee in MONCASH_ONLINE_TRANSACTION_FEES]

