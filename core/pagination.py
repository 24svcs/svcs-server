from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class DefaultPagination(PageNumberPagination):
    page_size = 10
    # page_size_query_param = 'page_size'
    # max_page_size = 100
    
    def get_paginated_response(self, data):
        """
        Return a paginated response with an extended format that preserves
        both the original data structure and adds pagination information.
        """
        # If data is a dict with other report information, preserve it
        if isinstance(data, dict):
            # Keep the original structure but make sure we paginate the appropriate list
            employee_stats = data.get('employee_statistics', [])
            
            # Build response with pagination metadata
            response_data = {
                **data,  # Keep all original data
                'pagination': {
                    'count': self.page.paginator.count,
                    'next': self.get_next_link(),
                    'previous': self.get_previous_link(),
                    'page_size': self.page_size,
                    'current_page': self.page.number,
                    'total_pages': self.page.paginator.num_pages,
                }
            }
            return Response(response_data)
        
        # Standard paginated response for simple lists
        return Response({
            'count': self.page.paginator.count,
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            'results': data
        })