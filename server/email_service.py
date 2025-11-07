"""
Email service using Replit Mail for password reset functionality
Integration: replitmail
"""

import os
import json
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

class ReplitMailService:
    """Service for sending emails using Replit Mail API"""
    
    def __init__(self):
        self.api_url = "https://connectors.replit.com/api/v2/mailer/send"
        self.auth_token = None
        self.is_available = False
        
        try:
            self.auth_token = self._get_auth_token()
            self.is_available = True
            print("[EMAIL SERVICE] Initialized successfully")
        except Exception as e:
            print(f"[EMAIL SERVICE] Not available: {str(e)}")
            print("[EMAIL SERVICE] Email functionality will be disabled")
    
    def _get_auth_token(self) -> str:
        """Get authentication token from Replit environment"""
        repl_identity = os.getenv("REPL_IDENTITY")
        web_repl_renewal = os.getenv("WEB_REPL_RENEWAL")
        
        if repl_identity:
            return f"repl {repl_identity}"
        elif web_repl_renewal:
            return f"depl {web_repl_renewal}"
        else:
            raise ValueError("No Replit authentication token found. Email service requires REPL_IDENTITY or WEB_REPL_RENEWAL environment variable.")
    
    async def send_email(
        self,
        to: str | List[str],
        subject: str,
        text: Optional[str] = None,
        html: Optional[str] = None,
        cc: Optional[str | List[str]] = None
    ) -> Dict[str, Any]:
        """
        Send an email using Replit Mail
        
        Args:
            to: Recipient email address(es)
            subject: Email subject
            text: Plain text body
            html: HTML body
            cc: CC recipient email address(es)
        
        Returns:
            Response from the email service
        """
        if not self.is_available or not self.auth_token:
            raise Exception("Email service is not available. Missing Replit authentication tokens.")
        
        payload = {
            "to": to,
            "subject": subject,
            "text": text,
            "html": html
        }
        
        if cc:
            payload["cc"] = cc
        
        headers = {
            "Content-Type": "application/json",
            "X_REPLIT_TOKEN": self.auth_token
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30.0
            )
            
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                raise Exception(f"Failed to send email: {error_data.get('message', 'Unknown error')}")
            
            return response.json()
    
    async def send_password_reset_email(
        self,
        to_email: str,
        reset_token: str,
        username: str,
        base_url: str
    ) -> Dict[str, Any]:
        """
        Send a password reset email with a formatted template
        
        Args:
            to_email: Recipient email
            reset_token: Password reset token
            username: User's username
            base_url: Base URL of the application
        
        Returns:
            Response from the email service
        """
        if not self.is_available:
            raise Exception("Email service is not available in this environment")
        
        reset_link = f"{base_url}/reset-password?token={reset_token}"
        
        # HTML template with modern styling
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Password Reset - UNITYmdm</title>
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; 
                     line-height: 1.6; 
                     color: #333; 
                     max-width: 600px; 
                     margin: 0 auto; 
                     padding: 20px;
                     background-color: #f5f5f5;">
            <div style="background-color: white; 
                        padding: 30px; 
                        border-radius: 10px; 
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #1a1a1a; font-size: 24px; margin: 0;">UNITYmdm</h1>
                    <p style="color: #666; font-size: 14px; margin: 5px 0;">Mobile Device Management</p>
                </div>
                
                <h2 style="color: #1a1a1a; font-size: 20px; margin-bottom: 15px;">Password Reset Request</h2>
                
                <p style="color: #666; margin-bottom: 20px;">
                    Hello <strong>{username}</strong>,
                </p>
                
                <p style="color: #666; margin-bottom: 25px;">
                    We received a request to reset your password. Click the button below to create a new password:
                </p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_link}" 
                       style="display: inline-block; 
                              padding: 12px 30px; 
                              background-color: #000; 
                              color: white; 
                              text-decoration: none; 
                              border-radius: 6px; 
                              font-weight: 500;
                              font-size: 14px;">
                        Reset Password
                    </a>
                </div>
                
                <p style="color: #999; font-size: 13px; margin-top: 25px; padding-top: 20px; border-top: 1px solid #eee;">
                    <strong>Security Notice:</strong><br>
                    • This link will expire in 1 hour<br>
                    • If you didn't request this reset, please ignore this email<br>
                    • Your password won't change until you complete the reset process
                </p>
                
                <p style="color: #999; font-size: 12px; margin-top: 20px;">
                    If the button doesn't work, copy and paste this link into your browser:<br>
                    <span style="color: #0066cc; word-break: break-all;">{reset_link}</span>
                </p>
            </div>
            
            <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                © {datetime.now(timezone.utc).year} UNITYmdm. All rights reserved.
            </div>
        </body>
        </html>
        """
        
        # Plain text version
        text_content = f"""
Password Reset Request - UNITYmdm

Hello {username},

We received a request to reset your password for your UNITYmdm account.

To reset your password, please visit the following link:
{reset_link}

This link will expire in 1 hour.

Security Notice:
• If you didn't request this reset, please ignore this email
• Your password won't change until you complete the reset process

If you're having trouble with the link, copy and paste it into your browser.

Best regards,
UNITYmdm Team
        """
        
        return await self.send_email(
            to=to_email,
            subject="Password Reset Request - UNITYmdm",
            text=text_content,
            html=html_content
        )
    
    async def send_password_reset_success_email(
        self,
        to_email: str,
        username: str
    ) -> Dict[str, Any]:
        """
        Send a confirmation email after successful password reset
        
        Args:
            to_email: Recipient email
            username: User's username
        
        Returns:
            Response from the email service
        """
        if not self.is_available:
            raise Exception("Email service is not available in this environment")
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                     line-height: 1.6; 
                     color: #333; 
                     max-width: 600px; 
                     margin: 0 auto; 
                     padding: 20px;">
            <div style="background-color: white; 
                        padding: 30px; 
                        border-radius: 10px; 
                        border: 1px solid #e0e0e0;">
                <h1 style="color: #1a1a1a; font-size: 24px; margin-bottom: 20px;">Password Successfully Reset</h1>
                
                <p style="color: #666;">
                    Hello <strong>{username}</strong>,
                </p>
                
                <p style="color: #666;">
                    Your password has been successfully reset. You can now log in with your new password.
                </p>
                
                <p style="color: #999; font-size: 13px; margin-top: 25px; padding-top: 20px; border-top: 1px solid #eee;">
                    If you didn't make this change, please contact your administrator immediately.
                </p>
            </div>
        </body>
        </html>
        """
        
        text_content = f"""
Password Successfully Reset - UNITYmdm

Hello {username},

Your password has been successfully reset. You can now log in with your new password.

If you didn't make this change, please contact your administrator immediately.

Best regards,
UNITYmdm Team
        """
        
        return await self.send_email(
            to=to_email,
            subject="Password Reset Successful - UNITYmdm",
            text=text_content,
            html=html_content
        )

# Singleton instance
email_service = ReplitMailService()