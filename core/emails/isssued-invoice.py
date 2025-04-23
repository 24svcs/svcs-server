
from django.conf import settings
import resend

from api.views import send_email_with_resend
resend.api_key = settings.RESEND_API_KEY
from django.http import JsonResponse
from django.conf import settings
import resend
import os
import logging
logger = logging.getLogger(__name__)




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