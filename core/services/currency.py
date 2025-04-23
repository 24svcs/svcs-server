import requests
from decimal import Decimal
import logging
import time
from functools import lru_cache
from django.conf import settings
from django.core.cache import cache
from typing import Dict, Optional

# Configure logging
logger = logging.getLogger(__name__)

# Constants
HTG_ADJUSTMENT_PERCENTAGE = 2  # 2% increase for HTG conversions
CACHE_TIMEOUT = 3600  # Cache exchange rates for 1 hour
RATE_LIMIT_WINDOW = 60  # Rate limit window in seconds
MAX_REQUESTS_PER_WINDOW = 100  # Maximum requests per rate limit window

class CurrencyConverterError(Exception):
    """Base exception for currency converter errors"""
    pass

class APIError(CurrencyConverterError):
    """Exception for API-related errors"""
    pass

class RateLimitError(CurrencyConverterError):
    """Exception for rate limit errors"""
    pass

class CurrencyConverter:
    def __init__(self):
        self.api_key = settings.EXCHANGE_RATE_API_KEY
        self.base_url = 'https://v6.exchangerate-api.com/v6'
        self.last_request_time = 0
        self.request_count = 0
        self.rate_limit_reset_time = time.time() + RATE_LIMIT_WINDOW

    def _check_rate_limit(self):
        """Check if we've exceeded the rate limit"""
        current_time = time.time()
        
        # Reset counter if window has passed
        if current_time > self.rate_limit_reset_time:
            self.request_count = 0
            self.rate_limit_reset_time = current_time + RATE_LIMIT_WINDOW
        
        # Check if we've exceeded the limit
        if self.request_count >= MAX_REQUESTS_PER_WINDOW:
            raise RateLimitError("Rate limit exceeded. Please try again later.")
        
        self.request_count += 1

    @lru_cache(maxsize=1)
    def _get_exchange_rates(self) -> Dict[str, float]:
        """
        Get exchange rates from API with caching.
        Uses both LRU cache and Django's cache system.
        """
        # Try to get from Django cache first
        cached_rates = cache.get('exchange_rates')
        if cached_rates:
            logger.debug("Retrieved exchange rates from cache")
            return cached_rates

        try:
            self._check_rate_limit()
            
            url = f"{self.base_url}/{self.api_key}/latest/USD"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            
            if data['result'] != 'success':
                raise APIError(f"API returned error: {data.get('error-type', 'Unknown error')}")
            
            rates = data['conversion_rates']
            
            # Cache the rates
            cache.set('exchange_rates', rates, CACHE_TIMEOUT)
            logger.info("Successfully fetched and cached new exchange rates")
            
            return rates
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch exchange rates: {str(e)}")
            raise APIError(f"Failed to fetch exchange rates: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error fetching exchange rates: {str(e)}")
            raise CurrencyConverterError(f"Unexpected error: {str(e)}")

    def convert(self, amount: float, from_currency: str, to_currency: str) -> float:
        """
        Convert an amount from one currency to another.
        
        Args:
            amount (float): The amount to convert
            from_currency (str): The source currency code (e.g., 'USD', 'EUR')
            to_currency (str): The target currency code (e.g., 'USD', 'EUR')
        
        Returns:
            float: The converted amount
            
        Raises:
            CurrencyConverterError: For general conversion errors
            APIError: For API-related errors
            RateLimitError: When rate limit is exceeded
            ValueError: For invalid input
        """
        try:
            # Input validation
            if not isinstance(amount, (int, float)) or amount < 0:
                raise ValueError("Amount must be a positive number")
            
            if not isinstance(from_currency, str) or not isinstance(to_currency, str):
                raise ValueError("Currency codes must be strings")
            
            from_currency = from_currency.upper()
            to_currency = to_currency.upper()
            
            # If currencies are the same, return the same amount
            if from_currency == to_currency:
                return round(amount, 2)
            
            # Get exchange rates
            rates = self._get_exchange_rates()
            
            # Validate currencies
            if from_currency not in rates or to_currency not in rates:
                raise ValueError(f"Invalid currency code. Available currencies: {', '.join(rates.keys())}")
            
            # Convert the amount
            if from_currency != 'USD':
                amount_in_usd = amount / rates[from_currency]
            else:
                amount_in_usd = amount
                
            converted_amount = amount_in_usd * rates[to_currency]
            
            # Apply HTG adjustment if converting TO HTG (5% increase)
            if to_currency == 'HTG':
                adjustment = converted_amount * (HTG_ADJUSTMENT_PERCENTAGE / 100)
                converted_amount += adjustment
                logger.info(f"Applied {HTG_ADJUSTMENT_PERCENTAGE}% adjustment to HTG conversion")
            
            # Round to 2 decimal places
            return round(converted_amount, 2)
            
        except (CurrencyConverterError, ValueError) as e:
            logger.error(f"Currency conversion error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in currency conversion: {str(e)}")
            raise CurrencyConverterError(f"Unexpected error: {str(e)}")

# Create a singleton instance
converter = CurrencyConverter()

def convert_currency(amount: float, from_currency: str, to_currency: str) -> float:
    """
    Convenience function to convert currency using the singleton converter instance.
    
    Args:
        amount (float): The amount to convert
        from_currency (str): The source currency code (e.g., 'USD', 'EUR')
        to_currency (str): The target currency code (e.g., 'USD', 'EUR')
    
    Returns:
        float: The converted amount
    """
    return converter.convert(amount, from_currency, to_currency)

# Example usage:
if __name__ == "__main__":
    try:
        # Convert 100 USD to HTG
        result = convert_currency(100, "USD", "HTG")
        print(f"100 USD = {result} HTG")
        
        # Convert 13000 HTG to USD
        result = convert_currency(13000, "HTG", "USD")
        print(f"13000 HTG = {result} USD")
        
        # Convert HTG to HTG (should return same amount)
        result = convert_currency(13000, "HTG", "HTG")
        print(f"13000 HTG = {result} HTG")
    except (CurrencyConverterError, ValueError) as e:
        print(f"Error: {e}")
