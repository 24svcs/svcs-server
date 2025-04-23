import logging
import resend
logger = logging.getLogger(__name__)

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