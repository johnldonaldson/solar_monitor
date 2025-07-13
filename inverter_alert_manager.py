#!/usr/bin/env python3
"""
Intelligent Inverter Alerting System
Handles sunset-aware alerting for offline/missing inverters
"""

import json
import os
import smtplib
import subprocess
from datetime import datetime
from email.mime.text import MIMEText


def calculate_sunset_time(latitude=37.7749, longitude=-122.4194):
    """Calculate sunset time for given coordinates"""
    try:
        from datetime import date
        import math
        
        today = date.today()
        n = today.timetuple().tm_yday
        
        # Solar declination
        solar_declination = 23.45 * math.sin(math.radians(360 * (284 + n) / 365))
        
        # Hour angle
        lat_rad = math.radians(latitude)
        decl_rad = math.radians(solar_declination)
        
        cos_hour_angle = -math.tan(lat_rad) * math.tan(decl_rad)
        
        # Check for polar day/night
        if cos_hour_angle > 1:
            return datetime.combine(today, datetime.min.time().replace(hour=17))
        elif cos_hour_angle < -1:
            return datetime.combine(today, datetime.min.time().replace(hour=21))
        
        hour_angle = math.degrees(math.acos(cos_hour_angle))
        sunset_hour = 12 + hour_angle / 15
        
        sunset_hours = int(sunset_hour)
        sunset_minutes = int((sunset_hour - sunset_hours) * 60)
        
        sunset_time = datetime.combine(
            today, 
            datetime.min.time().replace(hour=sunset_hours, minute=sunset_minutes)
        )
        
        return sunset_time
        
    except Exception as e:
        print(f"⚠️ Sunset calculation error: {e}, using default 6 PM")
        return datetime.combine(date.today(), datetime.min.time().replace(hour=18))


class InverterAlertManager:
    def __init__(self):
        self.alert_state_file = 'alert_state.json'
        
    def generate_offline_inverter_alerts(self, detailed_stats, alert_config):
        """Generate intelligent alerts for offline/missing inverters with sunset awareness"""
        try:
            alerts = []
            current_time = datetime.now()
            
            # Get sunset time and check if we're near/after sunset
            sunset_time = calculate_sunset_time()
            minutes_until_sunset = (sunset_time - current_time).total_seconds() / 60
            minutes_since_sunset = (current_time - sunset_time).total_seconds() / 60
            
            # Don't alert for missing inverters if it's near/after sunset
            sunset_buffer_minutes = alert_config.get('sunset_buffer_minutes', 60)
            
            if minutes_until_sunset <= sunset_buffer_minutes or minutes_since_sunset >= 0:
                # We're in the sunset window - normal for inverters to be offline
                return []
            
            # Only alert during productive daylight hours (8 AM - sunset buffer)
            hour = current_time.hour
            if hour < 8 or hour > 18:  # Basic daylight hours check
                return []
            
            # Count active vs total inverters
            active_inverters = len([s for s in detailed_stats if s['current_power'] > 0.01])
            total_system_inverters = 25  # Known system total
            detected_inverters = len(detailed_stats)
            missing_inverters = total_system_inverters - detected_inverters
            offline_inverters = detected_inverters - active_inverters
            
            # Configuration thresholds
            min_active_threshold = alert_config.get('min_active_inverters', 20)
            max_offline_threshold = alert_config.get('max_offline_inverters', 3)
            
            # Generate alerts based on severity
            if active_inverters < min_active_threshold:
                severity = "CRITICAL" if active_inverters < 18 else "WARNING"
                alert_msg = (f"{severity}: Only {active_inverters}/{total_system_inverters} "
                           f"inverters active during daylight hours")
                alerts.append({
                    'type': 'low_active_count',
                    'severity': severity,
                    'message': alert_msg,
                    'active_count': active_inverters,
                    'total_count': total_system_inverters,
                    'timestamp': current_time.isoformat()
                })
            
            if missing_inverters > 0:
                alert_msg = (f"WARNING: {missing_inverters} inverters not detected/reporting "
                           f"(only {detected_inverters}/25 found)")
                alerts.append({
                    'type': 'missing_inverters',
                    'severity': 'WARNING',
                    'message': alert_msg,
                    'missing_count': missing_inverters,
                    'detected_count': detected_inverters,
                    'timestamp': current_time.isoformat()
                })
            
            if offline_inverters > max_offline_threshold:
                # List specific offline inverters
                offline_serials = [s['serial'] for s in detailed_stats 
                                 if s['current_power'] <= 0.01]
                alert_msg = (f"WARNING: {offline_inverters} detected inverters offline: "
                           f"{', '.join(offline_serials[:5])}")
                if len(offline_serials) > 5:
                    alert_msg += f" and {len(offline_serials) - 5} more"
                    
                alerts.append({
                    'type': 'offline_inverters',
                    'severity': 'WARNING',
                    'message': alert_msg,
                    'offline_count': offline_inverters,
                    'offline_serials': offline_serials,
                    'timestamp': current_time.isoformat()
                })
            
            # Add timing context to alerts
            if alerts:
                timing_context = f"Alert generated at {current_time.strftime('%H:%M')} "
                timing_context += f"({minutes_until_sunset:.0f} min until sunset)"
                
                for alert in alerts:
                    alert['timing_context'] = timing_context
                    alert['sunset_buffer_minutes'] = sunset_buffer_minutes
            
            return alerts
            
        except Exception as e:
            print(f"❌ Error generating offline inverter alerts: {e}")
            return []
    
    def should_send_alert(self, alert, last_alerts_sent):
        """Determine if we should send an alert (rate limiting and deduplication)"""
        try:
            alert_type = alert.get('type')
            current_time = datetime.now()
            
            # Check if we've sent this type of alert recently
            if alert_type in last_alerts_sent:
                last_sent = datetime.fromisoformat(last_alerts_sent[alert_type])
                minutes_since_last = (current_time - last_sent).total_seconds() / 60
                
                # Don't spam - only send critical alerts every 30 min, warnings every 2 hours
                if alert.get('severity') == 'CRITICAL':
                    min_interval = 30
                else:
                    min_interval = 120
                
                if minutes_since_last < min_interval:
                    return False
            
            return True
            
        except Exception as e:
            print(f"❌ Error checking alert rate limiting: {e}")
            return True  # Default to sending if error
    
    def send_alert_email(self, alert_msg, detailed_msg, severity):
        """Send alert via email using existing email configuration"""
        try:
            # Load email config
            if not os.path.exists('email_config.json'):
                return {'success': False, 'error': 'Email not configured'}
                
            with open('email_config.json', 'r') as f:
                config = json.load(f)
            
            # Create email
            msg = MIMEText(detailed_msg)
            msg['Subject'] = f'🚨 {severity}: Solar System Alert - {datetime.now().strftime("%H:%M")}'
            msg['From'] = config['smtp_username']
            msg['To'] = config['email']
            
            # Send email
            server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
            server.starttls()
            server.login(config['smtp_username'], config['smtp_password'])
            server.send_message(msg)
            server.quit()
            
            print(f"📧 Alert email sent: {alert_msg}")
            return {'success': True}
            
        except Exception as e:
            print(f"❌ Failed to send alert email: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_alert_imessage(self, alert_msg, severity):
        """Send alert via iMessage using existing iMessage configuration"""
        try:
            # Load iMessage config
            if not os.path.exists('imessage_config.json'):
                return {'success': False, 'error': 'iMessage not configured'}
                
            with open('imessage_config.json', 'r') as f:
                config = json.load(f)
            
            if not config.get('imessage_enabled', False):
                return {'success': False, 'error': 'iMessage disabled'}
            
            phone = config['imessage_phone']
            
            # Create short message for iMessage
            short_msg = f"🚨 {severity}: {alert_msg[:100]}"
            if len(alert_msg) > 100:
                short_msg += "..."
            
            # Send via osascript (macOS only)
            script = f'''tell application "Messages"
                set targetService to 1st service whose service type = iMessage
                set targetBuddy to buddy "{phone}" of targetService
                send "{short_msg}" to targetBuddy
            end tell'''
            
            result = subprocess.run(['osascript', '-e', script], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print(f"📱 Alert iMessage sent: {short_msg}")
                return {'success': True}
            else:
                print(f"❌ iMessage failed: {result.stderr}")
                return {'success': False, 'error': result.stderr}
                
        except Exception as e:
            print(f"❌ Failed to send alert iMessage: {e}")
            return {'success': False, 'error': str(e)}
    
    def send_inverter_alert(self, alert, delivery_methods):
        """Send an inverter alert via configured methods (email, iMessage, or both)"""
        try:
            alert_msg = alert['message']
            severity = alert.get('severity', 'INFO')
            timing = alert.get('timing_context', '')
            
            # Create detailed alert message
            detailed_msg = f"""🚨 {severity} - Chilicon Solar System Alert

{alert_msg}

🕐 {timing}
🏠 System: 25 Inverter Solar Array
🌐 Dashboard: http://localhost:5002
⚙️ Admin Panel: http://localhost:5002/admin

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            
            results = []
            
            # Send email if configured
            if 'email' in delivery_methods:
                email_result = self.send_alert_email(alert_msg, detailed_msg, severity)
                results.append(('email', email_result))
            
            # Send iMessage if configured  
            if 'imessage' in delivery_methods:
                imessage_result = self.send_alert_imessage(alert_msg, severity)
                results.append(('imessage', imessage_result))
            
            return results
            
        except Exception as e:
            print(f"❌ Error sending inverter alert: {e}")
            return [('error', {'success': False, 'error': str(e)})]
    
    def load_alert_state(self):
        """Load alert state (last sent times, etc.)"""
        try:
            if os.path.exists(self.alert_state_file):
                with open(self.alert_state_file, 'r') as f:
                    return json.load(f)
            return {'last_alerts_sent': {}, 'alert_count': 0}
        except Exception as e:
            print(f"⚠️ Could not load alert state: {e}")
            return {'last_alerts_sent': {}, 'alert_count': 0}
    
    def save_alert_state(self, state):
        """Save alert state"""
        try:
            with open(self.alert_state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save alert state: {e}")
    
    def check_and_send_alerts(self, detailed_stats):
        """Main method to check for issues and send alerts if needed"""
        try:
            # Load configurations
            try:
                with open('alert_config.json', 'r') as f:
                    alert_config = json.load(f)
            except:
                print("⚠️ Alert config not found, using defaults")
                alert_config = {}
            
            # Check if alerts are enabled
            if not alert_config.get('inverter_alerts_enabled', True):
                return
            
            # Load alert state
            alert_state = self.load_alert_state()
            
            # Generate alerts
            alerts = self.generate_offline_inverter_alerts(detailed_stats, alert_config)
            
            if not alerts:
                return  # No alerts needed
            
            # Determine delivery methods
            delivery_methods = []
            if alert_config.get('email_alerts_enabled', True):
                delivery_methods.append('email')
            if alert_config.get('imessage_alerts_enabled', True):
                delivery_methods.append('imessage')
            
            if not delivery_methods:
                print("⚠️ No alert delivery methods enabled")
                return
            
            # Send alerts that haven't been sent recently
            for alert in alerts:
                if self.should_send_alert(alert, alert_state['last_alerts_sent']):
                    print(f"🚨 Sending {alert['severity']} alert: {alert['message']}")
                    
                    results = self.send_inverter_alert(alert, delivery_methods)
                    
                    # Update alert state if successful
                    success_count = sum(1 for method, result in results if result.get('success'))
                    if success_count > 0:
                        alert_state['last_alerts_sent'][alert['type']] = datetime.now().isoformat()
                        alert_state['alert_count'] = alert_state.get('alert_count', 0) + 1
                        
                        print(f"✅ Alert sent via {success_count}/{len(results)} methods")
                    else:
                        print("❌ All alert delivery methods failed")
                else:
                    print(f"⏭️  Skipping recent alert: {alert['type']}")
            
            # Save updated alert state
            self.save_alert_state(alert_state)
            
        except Exception as e:
            print(f"❌ Error in check_and_send_alerts: {e}")
            import traceback
            traceback.print_exc()


# Test the alerting system
if __name__ == "__main__":
    print("🧪 Testing Inverter Alert Manager")
    
    # Create sample data for testing
    sample_stats = [
        {'serial': '90F00170', 'current_power': 0.180},
        {'serial': '90F00173', 'current_power': 0.175},
        {'serial': '90F00179', 'current_power': 0.0},    # Offline
        {'serial': '90F00188', 'current_power': 0.172},
        {'serial': '90F0015C', 'current_power': 0.0},    # Offline
        # Only 5 inverters detected (20 missing)
    ]
    
    sample_config = {
        'inverter_alerts_enabled': True,
        'min_active_inverters': 20,
        'max_offline_inverters': 3,
        'sunset_buffer_minutes': 60,
        'email_alerts_enabled': True,
        'imessage_alerts_enabled': False
    }
    
    manager = InverterAlertManager()
    alerts = manager.generate_offline_inverter_alerts(sample_stats, sample_config)
    
    print(f"Generated {len(alerts)} alerts:")
    for alert in alerts:
        print(f"  {alert['severity']}: {alert['message']}")
