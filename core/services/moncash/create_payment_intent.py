from django_moncash.utils import init_payment
from core.services.moncash.constant import MONCASH_WEBHOOK_URL


def create_payment_intent(
    request,
    amount,
    order_id=None,
    meta_data=None,
    transaction_fee=0,
    total_amount=0
):
    payment = init_payment(request, total_amount,return_url=MONCASH_WEBHOOK_URL, order_id=order_id, meta_data=meta_data)
    
    response_data = {
        'payment_url': payment['payment_url'],
        'transaction_id': payment['transaction'].id if payment.get('transaction') else None,
        'amount': amount,
        'order_id': order_id,
        'transaction_fee': transaction_fee,
        'total_amount': total_amount
    }
    
    return response_data

