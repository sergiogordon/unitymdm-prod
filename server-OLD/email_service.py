"""
Email Service using Replit Mail Integration
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Check if Replit Mail is available
try:
    from replitmail import send_mail
    REPLIT_MAIL_AVAILABLE = True
except ImportError:
    REPLIT_MAIL_AVAILABLE = False
    logger.warning("Replit Mail not available. Email functionality disabled.")

async def send_password_reset_email(
    to_email: str, 
    username: str, 
    reset_token: str
) -> bool:
    """
    Send password reset email using Replit Mail
    """
    if not REPLIT_MAIL_AVAILABLE:
        logger.error("Cannot send email: Replit Mail not available")
        return False
    
    try:
        # Get the base URL from environment or use default
        base_url = os.getenv("FRONTEND_URL", "https://your-mdm.vercel.app")
        reset_url = f"{base_url}/reset-password?token={reset_token}"
        
        # Create HTML email content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background-color: #f9f9f9;
                    border-radius: 10px;
                    padding: 30px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .logo {{
                    font-size: 28px;
                    font-weight: bold;
                    color: #007AFF;
                }}
                .content {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 25px;
                    margin-bottom: 20px;
                }}
                .button {{
                    display: inline-block;
                    padding: 12px 30px;
                    background-color: #007AFF;
                    color: white !important;
                    text-decoration: none;
                    border-radius: 6px;
                    font-weight: 600;
                    margin: 20px 0;
                }}
                .button:hover {{
                    background-color: #0056b3;
                }}
                .footer {{
                    text-align: center;
                    color: #666;
                    font-size: 14px;
                    margin-top: 30px;
                }}
                .warning {{
                    background-color: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 10px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                code {{
                    background-color: #f4f4f4;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-family: 'Courier New', monospace;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">🛡️ MDM System</div>
                </div>
                
                <div class="content">
                    <h2>Password Reset Request</h2>
                    <p>Hello <strong>{username}</strong>,</p>
                    <p>We received a request to reset your password for your MDM System account.</p>
                    
                    <div style="text-align: center;">
                        <a href="{reset_url}" class="button">Reset Password</a>
                    </div>
                    
                    <p>Or copy and paste this link into your browser:</p>
                    <p><code style="word-break: break-all;">{reset_url}</code></p>
                    
                    <div class="warning">
                        <strong>⚠️ Security Notice:</strong><br>
                        • This link will expire in 1 hour<br>
                        • If you didn't request this, please ignore this email<br>
                        • Never share this link with anyone
                    </div>
                </div>
                
                <div class="footer">
                    <p>This is an automated message from MDM System.</p>
                    <p>© 2024 MDM System. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text fallback
        text_content = f"""
Password Reset Request

Hello {username},

We received a request to reset your password for your MDM System account.

Click the link below to reset your password:
{reset_url}

This link will expire in 1 hour.

Security Notice:
- If you didn't request this, please ignore this email
- Never share this link with anyone

This is an automated message from MDM System.
        """
        
        # Send email using Replit Mail
        send_mail(
            to_email=to_email,
            subject="MDM System - Password Reset Request",
            content=html_content,
            text_content=text_content
        )
        
        logger.info(f"Password reset email sent to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send password reset email: {e}")
        return False

async def send_password_reset_confirmation(
    to_email: str,
    username: str
) -> bool:
    """
    Send password reset confirmation email
    """
    if not REPLIT_MAIL_AVAILABLE:
        logger.error("Cannot send email: Replit Mail not available")
        return False
    
    try:
        # Create HTML email content
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .container {{
                    background-color: #f9f9f9;
                    border-radius: 10px;
                    padding: 30px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    margin-bottom: 30px;
                }}
                .logo {{
                    font-size: 28px;
                    font-weight: bold;
                    color: #28a745;
                }}
                .content {{
                    background-color: white;
                    border-radius: 8px;
                    padding: 25px;
                }}
                .success {{
                    background-color: #d4edda;
                    border-left: 4px solid #28a745;
                    padding: 10px;
                    margin: 20px 0;
                    border-radius: 4px;
                }}
                .footer {{
                    text-align: center;
                    color: #666;
                    font-size: 14px;
                    margin-top: 30px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <div class="logo">✅ Password Reset Successful</div>
                </div>
                
                <div class="content">
                    <h2>Your password has been reset</h2>
                    <p>Hello <strong>{username}</strong>,</p>
                    
                    <div class="success">
                        <strong>✅ Success!</strong><br>
                        Your password has been successfully reset.
                    </div>
                    
                    <p>You can now log in to your MDM System account with your new password.</p>
                    
                    <h3>Security Tips:</h3>
                    <ul>
                        <li>Use a strong, unique password</li>
                        <li>Enable two-factor authentication if available</li>
                        <li>Never share your password with anyone</li>
                        <li>If you didn't make this change, contact support immediately</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>This is an automated security notification from MDM System.</p>
                    <p>© 2024 MDM System. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text fallback
        text_content = f"""
Password Reset Successful

Hello {username},

Your password has been successfully reset.

You can now log in to your MDM System account with your new password.

Security Tips:
- Use a strong, unique password
- Enable two-factor authentication if available
- Never share your password with anyone
- If you didn't make this change, contact support immediately

This is an automated security notification from MDM System.
        """
        
        # Send email using Replit Mail
        send_mail(
            to_email=to_email,
            subject="MDM System - Password Reset Successful",
            content=html_content,
            text_content=text_content
        )
        
        logger.info(f"Password reset confirmation sent to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send confirmation email: {e}")
        return False

async def send_device_alert_email(
    to_email: str,
    device_id: str,
    alert_type: str,
    details: str
) -> bool:
    """
    Send device alert email notification
    """
    if not REPLIT_MAIL_AVAILABLE:
        logger.error("Cannot send email: Replit Mail not available")
        return False
    
    try:
        # Determine alert severity and color
        if alert_type in ["offline", "critical"]:
            color = "#dc3545"
            emoji = "🔴"
        elif alert_type == "warning":
            color = "#ffc107"
            emoji = "⚠️"
        else:
            color = "#007AFF"
            emoji = "ℹ️"
        
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .alert-box {{
                    border: 2px solid {color};
                    border-radius: 8px;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .alert-header {{
                    color: {color};
                    font-size: 24px;
                    font-weight: bold;
                    margin-bottom: 15px;
                }}
                .device-info {{
                    background-color: white;
                    padding: 15px;
                    border-radius: 6px;
                    margin: 15px 0;
                }}
                .footer {{
                    text-align: center;
                    color: #666;
                    font-size: 14px;
                    margin-top: 30px;
                }}
            </style>
        </head>
        <body>
            <div class="alert-box">
                <div class="alert-header">
                    {emoji} Device Alert: {alert_type.upper()}
                </div>
                
                <div class="device-info">
                    <strong>Device ID:</strong> {device_id}<br>
                    <strong>Alert Type:</strong> {alert_type}<br>
                    <strong>Details:</strong> {details}
                </div>
                
                <p>Please check the MDM dashboard for more information and to take appropriate action.</p>
            </div>
            
            <div class="footer">
                <p>MDM System Alert Notification</p>
            </div>
        </body>
        </html>
        """
        
        send_mail(
            to_email=to_email,
            subject=f"MDM Alert: {alert_type} - Device {device_id}",
            content=html_content
        )
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
        return False