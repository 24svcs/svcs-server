from django.urls import path, include
from rest_framework_nested import routers
from core.views import LanguageViewSet, UserViewSet, UserInvitationViewSet
from organization.views import OrganizationViewSet, MemberViewSet, InvitationViewSet
from human_resources.views import (
    DepartmentModelViewset, 
    PositionModelViewset, 
    EmployeeModelViewset, 
    AttendanceModelViewset, 
    EmployeeAttendanceStatsViewSet,
)
from finance.views import (
    ClientModelViewset,
    InvoiceViewSet,
    PaymentViewSet,
    MakeInvoicePaymentViewSet,
    BulkInvoiceItemViewSet,
    RecurringInvoiceViewSet,
    ClientAddressViewSet,
    StripePaymentViewSet,
    StripeWebhookView
)

from api.views import (
    notify_customers_view, 
    refine_attendance_records_view, 
    generate_attendance_reports_view, 
    send_email, 
    send_invite_email,
    buy
)

# Main router for non-nested routes
router = routers.DefaultRouter()
router.register('languages', LanguageViewSet, basename='languages')
router.register(r'organizations', OrganizationViewSet, basename='organizations')
router.register('users', UserViewSet, basename='users')
router.register('make-invoice-payments', MakeInvoicePaymentViewSet, basename='make-invoice-payments')

# Nested routers
user_invitation_router = routers.NestedDefaultRouter(router, r'users', lookup='user')
user_invitation_router.register(r'invitations', UserInvitationViewSet, basename='invitation')

member_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
member_router.register(r'members', MemberViewSet, basename='member')

invitation_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
invitation_router.register(r'invitations', InvitationViewSet, basename='invitation')

department_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
department_router.register(r'departments', DepartmentModelViewset, basename='department')

position_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
position_router.register(r'positions', PositionModelViewset, basename='position')

employee_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
employee_router.register(r'employees', EmployeeModelViewset, basename='employee')

attendance_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
attendance_router.register(r'attendances', AttendanceModelViewset, basename='attendance')

employee_attendance_stats_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
employee_attendance_stats_router.register(r'employee-attendance-stats', EmployeeAttendanceStatsViewSet, basename='employee-attendance-stats')

client_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
client_router.register('clients', ClientModelViewset, basename='client')

invoice_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
invoice_router.register('invoices', InvoiceViewSet, basename='invoice')

payment_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
payment_router.register('payments', PaymentViewSet, basename='payment')

# Stripe payments router
stripe_payment_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
stripe_payment_router.register('stripe-payments', StripePaymentViewSet, basename='stripe-payment')

# New router for bulk invoice items, nested under both organization and invoice
bulk_items_router = routers.NestedSimpleRouter(invoice_router, r'invoices', lookup='invoice')
bulk_items_router.register(r'bulk-items', BulkInvoiceItemViewSet, basename='bulk-invoice-items')

recurring_invoice_router = routers.NestedDefaultRouter(router, r'organizations', lookup='organization')
recurring_invoice_router.register('recurring-invoices', RecurringInvoiceViewSet, basename='recurring-invoice')

client_address_router = routers.NestedDefaultRouter(client_router, r'clients', lookup='client')
client_address_router.register('addresses', ClientAddressViewSet, basename='client-address')


urlpatterns = [
    path(r'', include(router.urls)),
    path(r'', include(member_router.urls)),
    path(r'', include(invitation_router.urls)),
    path(r'', include(department_router.urls)),
    path(r'', include(position_router.urls)),
    path(r'', include(employee_router.urls)),
    path(r'', include(attendance_router.urls)),
    path(r'', include(employee_attendance_stats_router.urls)),
    path(r'', include(user_invitation_router.urls)),
    path(r'', include(client_router.urls)),
    path(r'', include(invoice_router.urls)),
    path(r'', include(payment_router.urls)),
    path(r'', include(stripe_payment_router.urls)),
    path(r'', include(bulk_items_router.urls)),
    path(r'', include(recurring_invoice_router.urls)),
    path(r'', include(client_address_router.urls)),
    path(r'notify-customers/', notify_customers_view, name='notify-customers'),
    path(r'refine-attendance-records/', refine_attendance_records_view, name='refine-attendance-records'),
    path(r'generate-attendance-reports/', generate_attendance_reports_view, name='generate-attendance-reports'),
    path(r'send-email/', send_email, name='send-email'),
    path(r'send-invite-email/', send_invite_email, name='send-invite-email'),
    path(r'buy/', buy, name='buy'),
    path(r'stripe-webhook/', StripeWebhookView.as_view(), name='stripe-webhook'),
]