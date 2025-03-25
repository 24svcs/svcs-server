
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework import  filters
from core.pagination import DefaultPagination
from core.serializers import PermissionSerializer
from core.serializers import LanguageSerializer
from core.models import Permission
from core.models import Language
import pytz

    
class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = DefaultPagination
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer

    @api_view(['PUT'])
    @permission_classes([IsAuthenticated])
    def update_user_timezone(request):
        """
        Update the authenticated user's timezone preference
        """
        timezone_str = request.data.get('timezone')
        
        if not timezone_str:
            return Response(
                {"error": "Timezone is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate the timezone
        try:
            pytz.timezone(timezone_str)
        except pytz.exceptions.UnknownTimeZoneError:
            return Response(
                {"error": f"Invalid timezone: {timezone_str}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update the user's timezone
        request.user.timezone = timezone_str
        request.user.save()
        
        return Response({"timezone": timezone_str}, status=status.HTTP_200_OK)
    
    
    
    
    
class LanguageViewSet(viewsets.ReadOnlyModelViewSet):
    pagination_class = DefaultPagination
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    search_fields = ['name__istartswith']
    serializer_class = PermissionSerializer
    queryset = Language.objects.all().order_by('name')
    serializer_class = LanguageSerializer
