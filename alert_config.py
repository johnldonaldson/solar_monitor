#!/usr/bin/env python3
"""
Chilicon Alert Configuration and Test
Configure email alerts for the monitoring system
"""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def configure_email_alerts():
    """Configure email alert settings"""
    print("🔧 Chilicon Alert Configuration")
    print("=" * 40)
    
    config = {}
    
    # Get email settings
    print("\n📧 Email Settings:")
    print("Note: For Gmail, use an 'App Password' instead of your regular password")
    print("Generate one at: https://myaccount.google.com/apppasswords")
    
    config['smtp_server'] = input("SMTP Server (e.g., smtp.gmail.com): ").strip()
    config['smtp_port'] = int(input("SMTP Port (587 for Gmail): ").strip() or "587")
    config['email_address'] = input("Your email address: ").strip()
    config['email_password'] = input("Email password (or app password): ").strip()
    
    recipients = input("Alert recipients (comma-separated): ").strip()
    config['alert_recipients'] = [r.strip() for r in recipients.split(',')]
    
    # Alert thresholds
    print("\n⚠️ Alert Thresholds:")
    config['min_power_daylight'] = float(
        input("Min power during daylight (kW) [0.5]: ").strip() or "0.5"
    )
    config['max_inactive_inverters'] = int(
        input("Max inactive inverters [2]: ").strip() or "2"
    )
    config['power_drop_threshold'] = float(
        input("Power drop alert threshold (kW) [1.0]: ").strip() or "1.0"
    )
    config['alert_cooldown_minutes'] = int(
        input("Alert cooldown minutes [60]: ").strip() or "60"
    )
    
    # Enable/disable alerts
    config['email_enabled'] = input(
        "Enable email alerts? (y/n) [y]: "
    ).strip().lower() != 'n'
    
    # Save configuration
    with open('alert_config.json', 'w') as f:
        json.dump(config, f, indent=2)
    
    print("\n✅ Configuration saved to alert_config.json")
    
    # Test email
    if config['email_enabled'] and input("\n🧪 Test email alert? (y/n): ").lower() == 'y':
        test_email_alert(config)
    
    return config

def test_email_alert(config=None):
    """Test email alert functionality"""
    if not config:
        try:
            with open('alert_config.json', 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            print("❌ No configuration found. Run configuration first.")
            return
    
    try:
        print("📧 Sending test email...")
        
        # Create test message
        msg = MIMEMultipart()
        msg['From'] = config['email_address']
        msg['To'] = ', '.join(config['alert_recipients'])
        msg['Subject'] = "🔌 Chilicon Monitor Test Alert"
        
        body = f"""
This is a test alert from your Chilicon Power monitoring system.

📅 Test Time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
🔧 System: Chilicon Solar Array Monitor
✅ Status: Email alerts are working correctly!

If you received this email, your alert system is properly configured.

---
Chilicon Automated Monitoring System
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP(config['smtp_server'], config['smtp_port'])
        server.starttls()
        server.login(config['email_address'], config['email_password'])
        server.send_message(msg)
        server.quit()
        
        print("✅ Test email sent successfully!")
        
    except Exception as e:
        print(f"❌ Email test failed: {e}")
        print("\nTroubleshooting tips:")
        print("- For Gmail, use an 'App Password' instead of your regular password")
        print("- Enable 2-factor authentication and generate an app password")
        print("- Check your SMTP server and port settings")

def create_service_script():
    """Create a system service script for continuous monitoring"""
    service_script = '''#!/bin/bash
# Chilicon Monitor Service Script
# Place this in /usr/local/bin/chilicon-monitor.sh

cd /Users/johndona/Git_Repositories/JesusCalling
python3 automated_monitor.py
'''
    
    with open('chilicon-monitor.sh', 'w') as f:
        f.write(service_script)
    
    print("🔧 Service script created: chilicon-monitor.sh")
    print("\nTo run as a background service:")
    print("1. chmod +x chilicon-monitor.sh")
    print("2. nohup ./chilicon-monitor.sh &")
    print("3. Or use screen: screen -S chilicon python3 automated_monitor.py")

def main():
    """Main configuration menu"""
    print("🔌 Chilicon Monitoring Setup")
    print("=" * 30)
    print("1. Configure email alerts")
    print("2. Test email alerts")
    print("3. Create service script")
    print("4. Exit")
    
    while True:
        choice = input("\nSelect option (1-4): ").strip()
        
        if choice == "1":
            configure_email_alerts()
        elif choice == "2":
            test_email_alert()
        elif choice == "3":
            create_service_script()
        elif choice == "4":
            print("👋 Goodbye!")
            break
        else:
            print("Invalid option. Please choose 1-4.")

if __name__ == "__main__":
    main()
