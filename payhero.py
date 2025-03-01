import os
import requests

# Load PayHero credentials from environment variables
PAYHERO_API_USERNAME = os.getenv('PAYHERO_API_USERNAME')
PAYHERO_API_PASSWORD = os.getenv('PAYHERO_API_PASSWORD')
CALLBACK_URL = os.getenv('CALLBACK_URL')

def stk_push(phone, amount):
    """ Sends STK push using PayHero API. """
    try:
        url = "https://backend.payhero.co.ke/api/v2/payments"
        payload = {
            "amount": float(amount),  # Ensure amount is a float
            "phone_number": phone,
            "channel_id": 852,
            "provider": "m-pesa",
            "external_reference": "INV-009",
            "callback_url": CALLBACK_URL
        }
        auth = (PAYHERO_API_USERNAME, PAYHERO_API_PASSWORD)
        response = requests.post(url, json=payload, auth=auth)

        if response.status_code in [200, 201]:
            response_json = response.json()
            return response_json.get("success", False)
        else:
            print(f"Error initiating STK push: Received status code {response.status_code}")
            print(f"Response: {response.text}")
            return False
    except Exception as e:
        print(f"Error initiating STK push: {e}")
        return False