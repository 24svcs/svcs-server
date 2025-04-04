from django.shortcuts import render
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from .serializers import Client, ClientSerializer
from rest_framework.permissions import IsAuthenticated


class ClientModelViewset(ModelViewSet):
    
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        
        return Client.objects.select_related('address').filter(organization_id=self.kwargs['organization_pk'])
    
    
    serializer_class = ClientSerializer
    
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['organization_id'] = self.kwargs['organization_pk']
        return context
