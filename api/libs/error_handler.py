from rest_framework.views import exception_handler

def custom_error_handler(exc, context):
    response = exception_handler(exc, context)
    
    if response is not None and hasattr(exc, 'detail'):
        if isinstance(exc.detail, dict):
            # Extract the first field error
            try:
                field, messages = next(iter(exc.detail.items()))
                # Handle case where messages is a list or another nested structure
                if isinstance(messages, list) and messages:
                    error_message = f"({field}) field error - {messages[0]}"
                elif isinstance(messages, dict):
                    # Handle nested serializer errors
                    nested_field, nested_messages = next(iter(messages.items()))
                    error_msg = nested_messages[0] if isinstance(nested_messages, list) and nested_messages else str(nested_messages)
                    error_message = f"({field}.{nested_field}) field error - {error_msg}"
                else:
                    error_message = f"({field}) field error - {messages}"
            except (StopIteration, IndexError, KeyError):
                # Fallback for any unexpected error structure
                error_message = "Validation error occurred"
                
            response.data = {"error": error_message}
        elif isinstance(exc.detail, list) and exc.detail:
            # For list errors, use the first error
            response.data = {"error": str(exc.detail[0])}
        else:
            # For other types of errors, convert to string
            response.data = {"error": str(exc.detail)}
    
    return response