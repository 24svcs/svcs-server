from django.http import HttpResponse
from .jobs.tasks import notify_customers
from .jobs.refine_attendance_record import refine_attendance_records
from .jobs.generate_attendance_report import generate_attendance_reports
from django.http import JsonResponse
from django.conf import settings
import resend
import os
import logging
from django.shortcuts import redirect
from django_moncash.utils import init_payment



# Configure logging
logger = logging.getLogger(__name__)

# Initialize Resend with API key from settings
resend.api_key = settings.RESEND_API_KEY

def send_email_with_resend(to_emails, subject, html_content, from_email="Acme <onboarding@resend.dev>"):
    """
    Send an email using the Resend API
    
    Args:
        to_emails (list): List of recipient email addresses
        subject (str): Email subject
        html_content (str): HTML content for the email body
        from_email (str): Sender email address (with optional name)
        
    Returns:
        dict: Response from the Resend API or error information
    """
    try:
        params = {
            "from": from_email,
            "to": to_emails if isinstance(to_emails, list) else [to_emails],
            "subject": subject,
            "html": html_content,
        }
        
        response = resend.Emails.send(params)
        logger.info(f"Email sent successfully to {to_emails}")
        return {"success": True, "data": response}
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        return {"success": False, "error": str(e)}

def send_invite_email(request):
    try:
        # Read the HTML template
        template_path = os.path.join(os.path.dirname(__file__), 'emails/invite-email.html')
        
        if not os.path.exists(template_path):
            logger.error(f"Email template not found at: {template_path}")
            return JsonResponse({
                "status": "error", 
                "message": "Email template not found"
            }, status=500)
        
        with open(template_path, 'r') as file:
            html_content = file.read()
        
        # In production, you would get these values from request parameters
        # For example: recipient_name = request.GET.get('recipient_name')
        recipient_name = "John Doe"
        inviter_name = "Jane Smith"
        team_name = "24SVCS Team"
        invite_link = "https://app.24svcs.com/invite/abc123"
        
        html_content = html_content.replace('Jamie Smith', recipient_name)
        html_content = html_content.replace('Alex Johnson', inviter_name)
        html_content = html_content.replace('Design Collective', team_name)
        html_content = html_content.replace('https://app.example.com/invite/team123', invite_link)
        
        # Send the email
        email_result = send_email_with_resend(
            to_emails=["24svcs@gmail.com"],
            subject=f"You've been invited to join {team_name}",
            html_content=html_content,
            from_email="24SVCS <onboarding@resend.dev>"
        )
        
        if not email_result.get("success", False):
            return JsonResponse({
                "status": "error", 
                "message": "Failed to send email", 
                "error": email_result.get("error")
            }, status=500)
        
        return JsonResponse({
            "status": "success", 
            "message": "Invitation email sent successfully",
            "email_id": email_result.get("data", {}).get("id", "")
        })
    
    except Exception as e:
        logger.exception("Error sending invitation email")
        return JsonResponse({
            "status": "error", 
            "message": f"An unexpected error occurred: {str(e)}"
        }, status=500)

def send_email(request):
    email_response = send_email_with_resend(
        to_emails=["24svcs@gmail.com"],
        subject="Hello from Resend",
        html_content="<strong>Hello from 24svcs!</strong>"
    )
    print(email_response)
    return JsonResponse({"status": "ok", "email_id": email_response.get("id", "")})

def notify_customers_view(request):
    notify_customers.delay('Hello, world!')
    return HttpResponse('Notification sent')

def refine_attendance_records_view(request):
    refine_attendance_records.delay()
    return HttpResponse('Attendance records refined')

def generate_attendance_reports_view(request):
    generate_attendance_reports.delay()
    return HttpResponse('Attendance reports generated')

def buy(request):

        """ 
        params:

            request,                  # django views request
            amount: float,            # amount to pay
            return_url: str = None,   # custom return_url, default to current view
            order_id: str = None,     # unique order_id, default uuidV4
            meta_data: dict = None    # meta_data associated to the request
        """
        payment = init_payment(request,50)
        

        print(payment)

        return redirect(payment['payment_url'])