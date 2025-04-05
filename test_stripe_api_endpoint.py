#!/usr/bin/env python
"""
Test script for the Stripe API endpoint.
Generates curl commands for testing and directly calls the API.

Usage: python test_stripe_api_endpoint.py [organization_id] [invoice_uuid]
"""
import sys
import os
import requests
import json
import subprocess
from pprint import pprint

def find_invoice():
    """Find an invoice to test with"""
    # Set up Django environment
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'svcs.settings.dev')
    import django
    django.setup()
    
    from finance.models import Invoice
    
    # Find a suitable invoice
    invoice = Invoice.objects.filter(
        status__in=['PENDING', 'OVERDUE', 'PARTIALLY_PAID']
    ).first()
    
    if not invoice:
        print("No suitable invoice found for testing")
        return None, None
    
    return invoice.organization_id, invoice.uuid

def generate_curl_command(organization_id, invoice_uuid, token=None):
    """Generate a curl command for testing"""
    # Set default values
    api_url = "http://localhost:8000/api"
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    url = f"{api_url}/organizations/{organization_id}/stripe-payments/create-payment-intent/{invoice_uuid}/"
    
    # Generate curl command
    curl_cmd = ["curl", "-X", "POST", url]
    
    for header, value in headers.items():
        curl_cmd.extend(["-H", f"{header}: {value}"])
    
    curl_cmd.extend([
        "-H", "Content-Type: application/json",
        "-d", '{"return_url": "http://localhost:3000/payment-success"}'
    ])
    
    # Print as copyable command
    print("\n=== CURL Command for Testing ===")
    print(" ".join(curl_cmd))
    print()
    
    return curl_cmd

def get_auth_token():
    """
    Get auth token for API (placeholder)
    In a real application, you would implement proper token retrieval
    """
    # For testing purposes, you might want to provide the token as an environment variable
    return os.environ.get("API_AUTH_TOKEN")

def make_api_request(organization_id, invoice_uuid, token=None):
    """Make actual API request"""
    api_url = "http://localhost:8000/api"
    url = f"{api_url}/organizations/{organization_id}/stripe-payments/create-payment-intent/{invoice_uuid}/"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    data = {
        "return_url": "http://localhost:3000/payment-success"
    }
    
    print(f"Making API request to: {url}")
    try:
        response = requests.post(url, headers=headers, json=data)
        
        if response.status_code == 200 or response.status_code == 201:
            print("API call successful!")
            print("\nResponse:")
            pprint(response.json())
            
            # Extract client_secret for Stripe.js usage
            client_secret = response.json().get("client_secret")
            if client_secret:
                print("\n=== For use with Stripe.js ===")
                print(f"const clientSecret = '{client_secret}';")
                print("const {error, paymentIntent} = await stripe.confirmCardPayment(clientSecret, {")
                print("  payment_method: {")
                print("    card: elements.getElement('card'),")
                print("    billing_details: { name: 'Test Customer' }")
                print("  }")
                print("});")
            
            return response.json()
        else:
            print(f"API call failed with status code: {response.status_code}")
            print(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print(f"Error making API request: {str(e)}")
        return None

def main():
    """Main function"""
    print("=== Stripe API Endpoint Test ===")
    
    # Get organization_id and invoice_uuid
    if len(sys.argv) >= 3:
        organization_id = sys.argv[1]
        invoice_uuid = sys.argv[2]
    else:
        print("No organization_id and invoice_uuid provided, attempting to find one automatically...")
        organization_id, invoice_uuid = find_invoice()
        
        if not organization_id or not invoice_uuid:
            print("ERROR: Could not find a suitable invoice for testing")
            return 1
    
    print(f"Using organization_id: {organization_id}")
    print(f"Using invoice_uuid: {invoice_uuid}")
    
    # Get auth token (optional)
    token = get_auth_token()
    
    # Generate curl command
    generate_curl_command(organization_id, invoice_uuid, token)
    
    # Ask user if they want to make the actual API call
    choice = input("\nDo you want to make the actual API call? (y/n): ")
    if choice.lower() != 'y':
        print("Exiting without making API call.")
        return 0
    
    # Make API request
    result = make_api_request(organization_id, invoice_uuid, token)
    
    if result:
        print("\nTest completed successfully!")
        return 0
    else:
        print("\nTest failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 