#!/usr/bin/env python3
"""
Simple Email Test for Chilicon Alerts
Test email functionality independently
"""

import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime


def test_email_direct():
    """Test email sending directly"""
    print("📧 DIRECT EMAIL TEST")
    print("=" * 30)
    
    # Load configuration
    try:
        with open('alert_config.json', 'r') as f:
            config = json.load(f)
        print("✅ Configuration loaded")
    except FileNotFoundError:
        print("❌ No alert_config.json found. Run: python alert_config.py")
        return False
    
    if not config.get('email_enabled', False):
        print("❌ Email alerts disabled in configuration")
        print("   Edit alert_config.json and set 'email_enabled': true")
        return False
    
    print(f"📤 From: {config['email_address']}")
    print(f"📥 To: {', '.join(config['alert_recipients'])}")
    print(f"🌐 Server: {config['smtp_server']}:{config['smtp_port']}")
    
    try:
        # Create test message
        msg = MIMEMultipart()
        msg['From'] = config['email_address']
        msg['Subject'] = f"🧪 Chilicon Email Test - {datetime.now().strftime('%H:%M')}"
        
        body = f"""
🔌 CHILICON EMAIL TEST

✅ This is a test email from your Chilicon monitoring system.

📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🧪 Test Type: Direct SMTP Test
🤖 Source: Email Test Script

If you received this email, your alert system is working correctly!

Next steps:
1. Run the full alert test: python test_alerts.py
2. Start monitoring service: python complete_monitor_service.py

---
Chilicon Power Monitoring System
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send to each recipient
        success_count = 0
        for recipient in config['alert_recipients']:
            try:
                print(f"\n📧 Sending to {recipient}...")
                
                msg['To'] = recipient
                
                # Connect to SMTP server
                print("🔗 Connecting to SMTP server...")
                server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
                
                print("🔐 Starting TLS...")
                server.starttls()
                
                print("🔑 Logging in...")
                server.login(config['email_address'], config['email_password'])
                
                print("📤 Sending email...")
                server.send_message(msg)
                server.quit()
                
                print(f"✅ Email sent successfully to {recipient}")
                success_count += 1
                
            except smtplib.SMTPAuthenticationError as e:
                print(f"❌ Authentication failed: {e}")
                print("💡 For Gmail, make sure you're using an 'App Password'")
                print("   Generate one at: https://myaccount.google.com/apppasswords")
                
            except smtplib.SMTPException as e:
                print(f"❌ SMTP error: {e}")
                
            except Exception as e:
                print(f"❌ Failed to send to {recipient}: {e}")
        
        print(f"\n📊 Result: {success_count}/{len(config['alert_recipients'])} emails sent")
        return success_count > 0
        
    except Exception as e:
        print(f"❌ Email test failed: {e}")
        return False


def diagnose_email_config():
    """Diagnose email configuration issues"""
    print("\n🔍 EMAIL CONFIGURATION DIAGNOSIS")
    print("=" * 40)
    
    try:
        with open('alert_config.json', 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print("❌ No alert_config.json found")
        print("💡 Run: python alert_config.py")
        return
    
    # Check required fields
    required_fields = [
        'smtp_server', 'smtp_port', 'email_address', 
        'email_password', 'alert_recipients', 'email_enabled'
    ]
    
    print("📋 Configuration Check:")
    all_good = True
    for field in required_fields:
        if field in config and config[field]:
            status = "✅"
        else:
            status = "❌"
            all_good = False
        
        if field == 'email_password':
            value = "***HIDDEN***" if config.get(field) else "NOT SET"
        else:
            value = config.get(field, "NOT SET")
        
        print(f"   {status} {field}: {value}")
    
    # Check email address format
    email = config.get('email_address', '')
    if '@' in email and '.' in email:
        print("   ✅ Email format looks valid")
    else:
        print("   ❌ Email format invalid")
        all_good = False
    
    # Check recipients
    recipients = config.get('alert_recipients', [])
    if isinstance(recipients, list) and len(recipients) > 0:
        print(f"   ✅ {len(recipients)} recipient(s) configured")
    else:
        print("   ❌ No recipients configured")
        all_good = False
    
    # Gmail-specific checks
    if 'gmail.com' in config.get('smtp_server', ''):
        print("\n📧 Gmail-specific checks:")
        if config.get('smtp_port') == 587:
            print("   ✅ Port 587 (correct for Gmail)")
        else:
            print("   ⚠️  Port should be 587 for Gmail")
        
        print("   💡 For Gmail, ensure you're using an 'App Password':")
        print("      1. Enable 2-factor authentication")
        print("      2. Generate app password at: https://myaccount.google.com/apppasswords")
        print("      3. Use the app password (not your regular password)")
    
    print(f"\n🎯 Overall configuration: {'✅ Good' if all_good else '❌ Issues found'}")


def main():
    """Main testing function"""
    print("📧 CHILICON EMAIL TESTING TOOL")
    print("=" * 40)
    print("1. 🧪 Test Email Sending")
    print("2. 🔍 Diagnose Configuration")
    print("3. ⚙️  Show Configuration")
    print("4. 📝 Configuration Tips")
    print("5. ❌ Exit")
    
    while True:
        choice = input("\nSelect option (1-5): ").strip()
        
        if choice == '1':
            test_email_direct()
        
        elif choice == '2':
            diagnose_email_config()
        
        elif choice == '3':
            try:
                with open('alert_config.json', 'r') as f:
                    config = json.load(f)
                
                print("\n⚙️  CURRENT CONFIGURATION:")
                for key, value in config.items():
                    if key == 'email_password':
                        display_value = "***HIDDEN***"
                    else:
                        display_value = value
                    print(f"   {key}: {display_value}")
                        
            except FileNotFoundError:
                print("❌ No configuration file found")
        
        elif choice == '4':
            print("\n📝 EMAIL CONFIGURATION TIPS:")
            print("=" * 30)
            print("🔧 Gmail Setup:")
            print("   1. Use smtp.gmail.com, port 587")
            print("   2. Enable 2-factor authentication")
            print("   3. Generate App Password at: https://myaccount.google.com/apppasswords")
            print("   4. Use App Password (not regular password)")
            print()
            print("🔧 Other Email Providers:")
            print("   • Outlook: smtp-mail.outlook.com:587")
            print("   • Yahoo: smtp.mail.yahoo.com:587")
            print("   • Custom: Check your provider's SMTP settings")
            print()
            print("⚠️  Common Issues:")
            print("   • Wrong password (use App Password for Gmail)")
            print("   • 2FA not enabled (required for Gmail)")
            print("   • Wrong SMTP server or port")
            print("   • Firewall blocking SMTP")
        
        elif choice == '5':
            print("👋 Email testing completed!")
            break
        
        else:
            print("❌ Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
