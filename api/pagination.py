from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class DefaultPagination(PageNumberPagination):
    page_size = 10
    
    def get_page_number(self, request, paginator):
        """
        Override to handle invalid page numbers by returning page 1
        """
        page_number = request.query_params.get(self.page_query_param, 1)
        if page_number in self.last_page_strings:
            page_number = paginator.num_pages
        try:
            page_number = int(page_number)
            if page_number < 1:
                return 1
            if page_number > paginator.num_pages and paginator.num_pages > 0:
                return 1
            return page_number
        except (TypeError, ValueError):
            return 1
    
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