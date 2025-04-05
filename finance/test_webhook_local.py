#!/usr/bin/env python
"""
Test script for simulating Stripe webhooks locally.

This script allows you to test webhook handlers without deploying your application.
Set STRIPE_WEBHOOK_TEST_MODE=true in your environment before running this script.

Usage:
    python test_webhook_local.py [event_type] [payment_id]

Example:
    python test_webhook_local.py payment_intent.succeeded 123
    python test_webhook_local.py payment_intent.payment_failed 123
    python test_webhook_local.py charge.refunded 123
"""

import requests
import json
import sys
import os
import logging
from datetime import datetime

# Set up Django environment first
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.prod')
django.setup()

# Now import Django models
from finance.models import Payment

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
WEBHOOK_URL = "http://localhost:8000/api/webhooks/stripe/"  # Change to your webhook URL

def get_payment_by_id(payment_id):
    """
    Get payment details from database.
    """
    try:
        payment = Payment.objects.get(id=payment_id)
        return {
            'id': payment.id,
            'transaction_id': payment.transaction_id,
            'amount': float(payment.amount),
            'status': payment.status,
            'invoice_id': payment.invoice_id,
            'invoice_number': payment.invoice.invoice_number,
        }
    except Payment.DoesNotExist:
        logger.error(f"Payment {payment_id} not found")
        return None
    except Exception as e:
        logger.error(f"Error retrieving payment: {str(e)}")
        return None

def create_mock_event(event_type, payment_info):
    """Create a mock Stripe event payload."""
    if not payment_info or not payment_info['transaction_id']:
        logger.error("Cannot create event without transaction_id")
        return None
        
    amount_in_cents = int(payment_info['amount'] * 100)
    
    # Base event structure
    event = {
        'id': f'evt_test_{datetime.now().strftime("%Y%m%d%H%M%S")}',
        'type': event_type,
        'created': int(datetime.now().timestamp()),
        'data': {
            'object': {
                'id': payment_info['transaction_id'],
                'object': 'payment_intent',
                'amount': amount_in_cents,
                'currency': 'usd',
                'status': 'succeeded' if event_type == 'payment_intent.succeeded' else 'failed',
                'metadata': {
                    'invoice_id': str(payment_info['invoice_id']),
                    'invoice_number': payment_info['invoice_number']
                }
            }
        }
    }
    
    # Add event-specific data
    if event_type == 'charge.refunded':
        event['data']['object']['object'] = 'charge'
        event['data']['object']['refunded'] = True
        event['data']['object']['payment_intent'] = payment_info['transaction_id']
    
    return event

def send_webhook(event_payload):
    """Send the webhook to the local server."""
    logger.info(f"Sending webhook of type {event_payload['type']}")
    
    try:
        # Set fake signature header to simulate Stripe
        headers = {
            'Content-Type': 'application/json',
            'Stripe-Signature': 'test_signature_for_local_testing_only'
        }
        
        # Send the request
        response = requests.post(
            WEBHOOK_URL,
            headers=headers,
            json=event_payload
        )
        
        # Log result
        if response.status_code == 200:
            logger.info("Webhook sent successfully!")
            logger.info(f"Response: {response.status_code} {response.text}")
        else:
            logger.error(f"Failed to send webhook: {response.status_code} {response.text}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error sending webhook: {str(e)}")
        return None

def main():
    # Get arguments
    if len(sys.argv) < 3:
        print("Usage: python test_webhook_local.py <event_type> <payment_id>")
        print("Available event types: payment_intent.succeeded, payment_intent.payment_failed, charge.refunded")
        return
        
    event_type = sys.argv[1]
    payment_id = sys.argv[2]
    
    valid_event_types = ['payment_intent.succeeded', 'payment_intent.payment_failed', 'charge.refunded']
    if event_type not in valid_event_types:
        logger.error(f"Invalid event type: {event_type}")
        print(f"Valid event types: {', '.join(valid_event_types)}")
        return
    
    # Get payment information
    payment_info = get_payment_by_id(payment_id)
    if not payment_info:
        return
        
    # Create mock event
    event = create_mock_event(event_type, payment_info)
    if not event:
        return
        
    # Print event for debugging
    logger.info("Created mock webhook event:")
    print(json.dumps(event, indent=2))
    
    # Confirm with user
    confirm = input(f"\nSend webhook for payment {payment_id} with event type {event_type}? (y/n): ")
    if confirm.lower() != 'y':
        logger.info("Webhook sending cancelled by user")
        return
        
    # Send webhook
    send_webhook(event)

if __name__ == "__main__":
    # Check if test mode is enabled
    if os.environ.get('STRIPE_WEBHOOK_TEST_MODE', '').lower() != 'true':
        print("ERROR: STRIPE_WEBHOOK_TEST_MODE environment variable must be set to 'true'")
        print("Set with: export STRIPE_WEBHOOK_TEST_MODE=true")
        sys.exit(1)
        
    main() 