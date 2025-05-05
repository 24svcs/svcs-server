
from core.services.moncash.configuration import gateway
from moncash.exceptions import  NotFoundError



def verify_payment_by_reference(request, reference):
    try:
        payment = gateway.payment.get_by_ref(reference=reference)
        json_data = {
            "reference": payment['reference'],
            "transaction_id": payment['transaction_id'],
            "cost": payment['cost'],
            "message": payment['message'],
            "payer": payment['payer'],
            "status": 'SUCCESS'
        }
        return json_data
    except NotFoundError as e:
        return {
            "status": 'NOT_FOUND'
        }
    except Exception as e:
        return {
            "status": 'ERROR',
            "message": str(e)
        }


def verify_payment_by_transaction_id(request, transaction_id):
    try:
        payment = gateway.payment.get_by_id(transactionId=transaction_id)
        json_data = {
            "transaction_id": payment['transaction_id'],
            "cost": payment['cost'],
            "message": payment['message'],
            "payer": payment['payer'],
            "status": 'SUCCESS'
        }
        return json_data
    except Exception as e:
        return {
            "status": 'ERROR',
            "message": 'Unable to verify payment'
        }