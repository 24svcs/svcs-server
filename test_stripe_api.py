#!/usr/bin/env python
"""
Standalone script to test the Stripe payment API.
Usage:
    python test_stripe_api.py <organization_id> <invoice_uuid>
"""
import sys
import json
import requests
import logging
from pprint import pprint

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Variables that you need to set
API_BASE_URL = "http://localhost:8000/api"  # Change to your server URL
AUTH_TOKEN = "your_auth_token"  # You'll need to get this from your authentication flow

def get_payment_intent(organization_id, invoice_uuid):
    """
    Test creating a payment intent through the API
    """
    url = f"{API_BASE_URL}/organizations/{organization_id}/stripe-payments/create-payment-intent/{invoice_uuid}/"
    
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    data = {
        "return_url": "http://localhost:3000/payment-success"  # Your frontend return URL
    }
    
    logger.info(f"Calling API: POST {url}")
    response = requests.post(url, headers=headers, json=data)
    
    if response.status_code == 200 or response.status_code == 201:
        logger.info("API call successful")
        result = response.json()
        logger.info("Response data:")
        pprint(result)
        
        print("\n-------------------------------------")
        print("STRIPE PAYMENT INTENT CREATED SUCCESSFULLY")
        print(f"Client Secret: {result.get('client_secret')}")
        print(f"Payment ID: {result.get('payment_id')}")
        print(f"Amount: {result.get('amount')}")
        print(f"Invoice Number: {result.get('invoice_number')}")
        print("-------------------------------------\n")
        
        return result
    else:
        logger.error(f"API call failed with status code {response.status_code}")
        logger.error(f"Response: {response.text}")
        return None

def main():
    if len(sys.argv) < 3:
        print("Usage: python test_stripe_api.py <organization_id> <invoice_uuid>")
        return
    
    organization_id = sys.argv[1]
    invoice_uuid = sys.argv[2]
    
    logger.info(f"Testing Stripe API with organization ID {organization_id} and invoice UUID {invoice_uuid}")
    
    # Test creating a payment intent
    payment_intent = get_payment_intent(organization_id, invoice_uuid)
    
    if payment_intent:
        print("Test completed successfully!")
        print("You can now use the client_secret with Stripe.js to complete the payment on the frontend.")
        print("For example:")
        print("""
// Use in your frontend code:
const stripe = Stripe('your_publishable_key');
const {error} = await stripe.confirmCardPayment(client_secret, {
  payment_method: {
    card: elements.getElement('card'),
    billing_details: {
      name: 'Customer Name'
    }
  }
});
        """)
    else:
        print("Test failed. Check logs for details.")

if __name__ == "__main__":
    main() 