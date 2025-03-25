

from rest_framework.views import exception_handler

def custom_error_handler(exc, context):
    response = exception_handler(exc, context)
    
    if response is not None and hasattr(exc, 'detail'):
        if isinstance(exc.detail, dict):
            # Construct a single error message like "email field is required."
            field, messages = next(iter(exc.detail.items()))
            error_message = f"({field}) field error -  {messages[0].lower()}" if messages else "Validation error"
            response.data = {"error": error_message}
        else:
            # For non-field errors, return a general error message
            response.data = {"error": str(exc.detail[0]) if isinstance(exc.detail, list) else str(exc.detail)}
    
    return response