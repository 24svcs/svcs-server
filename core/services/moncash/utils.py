
from core.services.moncash.constant import MAX_TRANSACTION_FEE, MONCASH_ONLINE_TRANSACTION_FEES


def get_moncash_online_transaction_fee(amount):
    for fee in MONCASH_ONLINE_TRANSACTION_FEES:
        if amount >= fee['AMOUNT_FROM'] and amount <= fee['AMOUNT_TO']:
            return fee['FEE']
    return MAX_TRANSACTION_FEE

def get_moncash_online_transaction_fee_percentage(amount):
    return get_moncash_online_transaction_fee(amount) / amount

def get_moncash_online_transaction_fee_percentage_range():
    return [get_moncash_online_transaction_fee_percentage(fee['AMOUNT_FROM']) for fee in MONCASH_ONLINE_TRANSACTION_FEES]

