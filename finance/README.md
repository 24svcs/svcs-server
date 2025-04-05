# Finance Module Payment System Documentation

## Payment Workflow

The invoice payment system supports several payment methods:

1. **Credit Card Payments**: Processed via Stripe, requiring webhook confirmations
2. **Cash Payments**: Automatically marked as completed upon creation
3. **Bank Transfer Payments**: Automatically marked as completed upon creation
4. **Other Payments**: Automatically marked as completed upon creation

## Security Improvements

Recent security improvements include:

1. **Automatic Payment Status**:

   - Non-credit card payments (cash, bank transfers, etc.) are automatically marked as COMPLETED
   - Only credit card payments remain in PENDING status waiting for Stripe webhook confirmation

2. **Restricted Manual Status Changes**:

   - Credit card payments cannot be manually marked as completed or failed
   - Only Stripe webhooks can update credit card payment statuses
   - Refunding credit card payments requires special permissions

3. **Enhanced Webhook Security**:

   - Rate limiting to prevent abuse
   - IP logging and validation
   - Detailed error logging
   - Proper webhook signature verification in production

4. **Role-Based Access Control**:
   - Permission checks for payment status changes
   - Organization-level access validation

## Testing Stripe Webhooks Locally

To test the complete payment flow including webhooks locally without deploying:

1. **Enable Test Mode**:

```bash
export STRIPE_WEBHOOK_TEST_MODE=true
```

2. **Create a Test Payment**:

   Use the API to create a credit card payment. Make note of the payment ID.

3. **Simulate a Webhook Event**:

```bash
# To mark a payment as successful
python finance/test_webhook_local.py payment_intent.succeeded 123

# To mark a payment as failed
python finance/test_webhook_local.py payment_intent.payment_failed 123

# To mark a payment as refunded
python finance/test_webhook_local.py charge.refunded 123
```

Replace `123` with the actual payment ID from step 2.

4. **Verify Results**:

   Check the payment status in the database - it should be updated to COMPLETED, FAILED, or REFUNDED based on the webhook type.

## Using the Stripe CLI (Alternative Method)

For a more authentic testing experience, you can use the Stripe CLI:

1. **Install Stripe CLI**: Follow instructions at https://stripe.com/docs/stripe-cli

2. **Login to Stripe**:

```bash
stripe login
```

3. **Forward Webhooks**:

```bash
stripe listen --forward-to localhost:8000/api/webhooks/stripe/
```

4. **Trigger Test Webhooks**:

```bash
stripe trigger payment_intent.succeeded
```

## Important Notes

1. Always set `STRIPE_WEBHOOK_TEST_MODE=false` in production environments
2. Ensure proper signature verification in production
3. Regularly audit payment status changes through logs
4. Never manually update credit card payment statuses
