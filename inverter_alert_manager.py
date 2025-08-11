#!/usr/bin/env python3
"""
Intelligent Inverter Alerting System
Handles sunset-aware alerting for offline/missing inverters
Enhanced with timing intelligence to prevent false alerts
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
        # Initialize timing intelligence for smart alerting
        try:
            from intelligent_inverter_timing import create_timing_intelligence_integration
            self.timing_intelligence = create_timing_intelligence_integration()
            print("✅ Timing intelligence loaded for smart alerting")
        except Exception as e:
            print(f"⚠️ Could not load timing intelligence: {e}")
            self.timing_intelligence = None
    
    def get_expected_active_inverters(self, current_time):
        """
        Get the expected number of active inverters based on timing intelligence
        Returns tuple: (expected_east, expected_south, reasoning)
        """
        if not self.timing_intelligence:
            # Fallback to simple time-based expectations
            hour = current_time.hour
            if 6 <= hour <= 8:
                return (12, 0, "Early morning - only east array expected")
            elif 9 <= hour <= 16:
                return (12, 13, "Midday - both arrays expected active")
            elif 17 <= hour <= 19:
                return (0, 13, "Late day - only south array expected")
            else:
                return (0, 0, "Night/dawn - no arrays expected active")
        
        try:
            # Get current timing insights
            insights = self.timing_intelligence['get_insights']()
            current_hour = current_time.hour
            
            # Default expectations
            expected_east = 0
            expected_south = 0
            reasoning = ""
            
            # Check learned patterns for each array
            array_groups = insights.get('array_groups', {})
            
            # East array analysis
            east_data = array_groups.get('east_facing', {})
            has_east_patterns = east_data.get('typical_wake_time') and east_data.get('count', 0) > 0
            
            if has_east_patterns:
                try:
                    wake_hour = int(east_data['typical_wake_time'].split(':')[0])
                    sleep_hour = int(east_data.get('typical_sleep_time', '18:00').split(':')[0])
                    if wake_hour <= current_hour <= sleep_hour:
                        expected_east = 12
                except (ValueError, IndexError):
                    pass
            
            # South array analysis  
            south_data = array_groups.get('south_facing', {})
            has_south_patterns = south_data.get('typical_wake_time') and south_data.get('count', 0) > 0
            
            if has_south_patterns:
                try:
                    wake_hour = int(south_data['typical_wake_time'].split(':')[0])
                    sleep_hour = int(south_data.get('typical_sleep_time', '19:00').split(':')[0])
                    if wake_hour <= current_hour <= sleep_hour:
                        expected_south = 13
                except (ValueError, IndexError):
                    pass
            
            # If no learned patterns available, use intelligent fallback based on time
            if not has_east_patterns and not has_south_patterns:
                # Intelligent fallback based on typical solar patterns
                if 6 <= current_hour <= 8:
                    expected_east = 12  # East wakes first
                    expected_south = 0
                    reasoning = "Early morning - east array expected (no learned patterns)"
                elif 9 <= current_hour <= 16:
                    expected_east = 12  # Both active during midday
                    expected_south = 13
                    reasoning = "Midday - both arrays expected (no learned patterns)"
                elif 17 <= current_hour <= 19:
                    expected_east = 0  # East may shut down first
                    expected_south = 13
                    reasoning = "Late day - south array expected (no learned patterns)"
                else:
                    expected_east = 0
                    expected_south = 0
                    reasoning = "Night/dawn - no arrays expected (no learned patterns)"
            else:
                # Generate reasoning based on learned patterns
                if expected_east > 0 and expected_south > 0:
                    reasoning = "Both arrays should be active (learned patterns)"
                elif expected_east > 0:
                    reasoning = "Only east array should be active (learned patterns)"
                elif expected_south > 0:
                    reasoning = "Only south array should be active (learned patterns)"
                else:
                    reasoning = "No arrays expected active (learned patterns)"
            
            return (expected_east, expected_south, reasoning)
            
        except Exception as e:
            print(f"⚠️ Error getting timing expectations: {e}")
            # Fallback to simple logic
            hour = current_time.hour
            if 6 <= hour <= 8:
                return (12, 0, "Early morning fallback")
            elif 9 <= hour <= 16:
                return (12, 13, "Midday fallback")
            elif 17 <= hour <= 19:
                return (0, 13, "Late day fallback")
            else:
                return (0, 0, "Night fallback")
    
    def classify_inverter_by_serial(self, serial):
        """Classify an inverter as east or south facing based on known arrays"""
        # Known array classifications
        east_array = {
            '41300712', '90F001AD', '90F001DA', '90F00174', '90F0017D',
            '716007E7', '90F00170', '90F00173', '90F00188', '90F0015C',
            'C1300529', '90F00199'
        }
        
        south_array = {
            '90F0017B', '7160127B', '90F00167', '90F001B1', '90F00185',
            '90F001B6', '90F00180', '90F0017A', '90F0017F', '90F001AF',
            '90F00187', '90F0017E', '90F00175'
        }
        
        if serial in east_array:
            return 'east'
        elif serial in south_array:
            return 'south'
        else:
            return 'unknown'
        
    def generate_offline_inverter_alerts(self, detailed_stats, alert_config):
        """
        Generate intelligent alerts for offline/missing inverters with timing intelligence
        Prevents false alerts when inverters are naturally offline due to array orientation
        """
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
                print(f"🌅 Skipping alerts: {minutes_until_sunset:.0f}min to sunset (buffer: {sunset_buffer_minutes}min)")
                return []
            
            # Only alert during productive daylight hours (7 AM - sunset buffer)
            hour = current_time.hour
            if hour < 7 or hour > 19:  # Basic daylight hours check
                print(f"🌙 Skipping alerts: Outside daylight hours ({hour}:00)")
                return []
            
            # Get intelligent expectations based on timing patterns
            expected_east, expected_south, reasoning = self.get_expected_active_inverters(current_time)
            expected_total = expected_east + expected_south
            
            print(f"🧠 Intelligent expectations: East={expected_east}, South={expected_south} ({reasoning})")
            
            # Classify current inverters by array
            east_active = 0
            south_active = 0
            east_offline = []
            south_offline = []
            unknown_inverters = []
            
            for inverter in detailed_stats:
                array_type = self.classify_inverter_by_serial(inverter['serial'])
                is_active = inverter['current_power'] > 0.01
                
                if array_type == 'east':
                    if is_active:
                        east_active += 1
                    else:
                        east_offline.append(inverter['serial'])
                elif array_type == 'south':
                    if is_active:
                        south_active += 1
                    else:
                        south_offline.append(inverter['serial'])
                else:
                    unknown_inverters.append(inverter['serial'])
                    if is_active:
                        # Count unknown as contributing to totals
                        if expected_east > 0:
                            east_active += 1
                        elif expected_south > 0:
                            south_active += 1
            
            total_active = east_active + south_active
            total_detected = len(detailed_stats)
            
            print(f"📊 Current status: East={east_active}/{expected_east}, South={south_active}/{expected_south}")
            
            # Generate smart alerts based on expectations vs reality
            
            # 1. Check for missing inverters (fewer detected than expected)
            expected_detected = 25  # Total system size
            if total_detected < expected_detected:
                missing_count = expected_detected - total_detected
                alert_msg = (f"CRITICAL: {missing_count} inverters not reporting "
                           f"(only {total_detected}/25 detected)")
                alerts.append({
                    'type': 'missing_inverters',
                    'severity': 'CRITICAL',
                    'message': alert_msg,
                    'missing_count': missing_count,
                    'detected_count': total_detected,
                    'timestamp': current_time.isoformat(),
                    'reasoning': 'Physical inverters not responding'
                })
            
            # 2. Check east array against expectations (only if we expect it to be active)
            if expected_east > 0:
                east_missing = max(0, expected_east - east_active)
                if east_missing >= 3:  # Threshold for east array alerts
                    severity = "CRITICAL" if east_missing >= 6 else "WARNING"
                    alert_msg = (f"{severity}: East array underperforming - "
                               f"only {east_active}/{expected_east} active")
                    if east_offline:
                        alert_msg += f". Offline: {', '.join(east_offline[:3])}"
                        if len(east_offline) > 3:
                            alert_msg += f" +{len(east_offline) - 3} more"
                    
                    alerts.append({
                        'type': 'east_array_underperform',
                        'severity': severity,
                        'message': alert_msg,
                        'expected': expected_east,
                        'actual': east_active,
                        'offline_serials': east_offline,
                        'timestamp': current_time.isoformat(),
                        'reasoning': f'East array expected active at {hour}:00 but underperforming'
                    })
            
            # 3. Check south array against expectations (only if we expect it to be active)
            if expected_south > 0:
                south_missing = max(0, expected_south - south_active)
                if south_missing >= 3:  # Threshold for south array alerts
                    severity = "CRITICAL" if south_missing >= 7 else "WARNING"
                    alert_msg = (f"{severity}: South array underperforming - "
                               f"only {south_active}/{expected_south} active")
                    if south_offline:
                        alert_msg += f". Offline: {', '.join(south_offline[:3])}"
                        if len(south_offline) > 3:
                            alert_msg += f" +{len(south_offline) - 3} more"
                    
                    alerts.append({
                        'type': 'south_array_underperform',
                        'severity': severity,
                        'message': alert_msg,
                        'expected': expected_south,
                        'actual': south_active,
                        'offline_serials': south_offline,
                        'timestamp': current_time.isoformat(),
                        'reasoning': f'South array expected active at {hour}:00 but underperforming'
                    })
            
            # 4. Check for overall system underperformance (backup check)
            if expected_total > 0:
                performance_ratio = total_active / expected_total
                if performance_ratio < 0.8:  # Less than 80% of expected
                    severity = "CRITICAL" if performance_ratio < 0.6 else "WARNING"
                    alert_msg = (f"{severity}: System underperforming - "
                               f"only {total_active}/{expected_total} inverters active "
                               f"({performance_ratio:.1%} of expected)")
                    
                    alerts.append({
                        'type': 'system_underperform',
                        'severity': severity,
                        'message': alert_msg,
                        'expected_total': expected_total,
                        'actual_total': total_active,
                        'performance_ratio': performance_ratio,
                        'timestamp': current_time.isoformat(),
                        'reasoning': reasoning
                    })
            
            # Add timing context to all alerts
            if alerts:
                timing_context = (f"Alert generated at {current_time.strftime('%H:%M')} "
                                f"({minutes_until_sunset:.0f} min until sunset). {reasoning}")
                
                for alert_item in alerts:
                    alert_item['timing_context'] = timing_context
                    alert_item['sunset_buffer_minutes'] = sunset_buffer_minutes
                    alert_item['expected_east'] = expected_east
                    alert_item['expected_south'] = expected_south
                    alert_item['actual_east'] = east_active
                    alert_item['actual_south'] = south_active
            
            if not alerts:
                print("✅ No alerts needed - system performing within intelligent expectations")
            
            return alerts
            
        except Exception as e:
            print(f"❌ Error generating intelligent alerts: {e}")
            import traceback
            traceback.print_exc()
            return []
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
            
            # Use display name if available, otherwise fall back to smtp_username
            display_name = config.get('display_name', 'Solar Monitor')
            from_email = config['smtp_username']
            msg['From'] = f"{display_name} <{from_email}>"
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
🌐 Dashboard: http://solar_monitor:5002
⚙️ Admin Panel: http://solar_monitor:5002/admin

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
