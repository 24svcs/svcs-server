from django.contrib import admin
from django.urls import path, include
from debug_toolbar.toolbar import debug_toolbar_urls
from finance.views import PublicInvoicePaymentView

urlpatterns = [
    path('', include('core.urls')),
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    path('api/', include('api.urls')),
    path('payment/',include('django_moncash.urls')),
    path('create-invoice-payment/<uuid:invoice_uuid>/', PublicInvoicePaymentView.as_view(), name='invoice-payment'),
    
]  + debug_toolbar_urls()
