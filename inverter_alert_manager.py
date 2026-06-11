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
from datetime import datetime, timedelta
import math
from pathlib import Path
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
        self.production_history_file = Path('inverter_production_history.json')
        
        # Initialize timing intelligence for smart alerting
        try:
            from intelligent_inverter_timing import create_timing_intelligence_integration
            self.timing_intelligence = create_timing_intelligence_integration()
            print("✅ Timing intelligence loaded for smart alerting")
        except Exception as e:
            print(f"⚠️ Could not load timing intelligence: {e}")
            self.timing_intelligence = None
        
        # Initialize weather monitor for rain-based alert suspension
        try:
            from simple_weather_monitor import SimpleWeatherMonitor
            self.weather_monitor = SimpleWeatherMonitor()
            print("✅ Simple weather monitor loaded for rain-based suspension")
        except Exception as e:
            print(f"⚠️ Could not load weather monitor: {e}")
            self.weather_monitor = None

    def _parse_time_for_today(self, time_str, current_time):
        """Convert HH:MM string into today's datetime"""
        if not time_str:
            return None
        try:
            hour, minute = map(int, time_str.split(':')[:2])
            return current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
        except (ValueError, AttributeError):
            return None

    def _compute_dynamic_expectation(self, total_inverters, wake_time, sleep_time, current_time):
        """Use learned wake/sleep times with grace periods to set expectations"""
        ramp_up = timedelta(minutes=45)
        ramp_down = timedelta(minutes=45)
        pre_wake_buffer = timedelta(minutes=15)

        wake_dt = self._parse_time_for_today(wake_time, current_time)
        sleep_dt = self._parse_time_for_today(sleep_time, current_time)

        if not wake_dt:
            return total_inverters, 'fallback', 'No learned wake time'

        if current_time < wake_dt - pre_wake_buffer:
            return 0, 'night', f'Before wake window ({wake_time})'

        if current_time < wake_dt:
            return 0, 'pre_wake', f'Approaching wake window ({wake_time})'

        if current_time <= wake_dt + ramp_up:
            progress = (current_time - wake_dt).total_seconds() / ramp_up.total_seconds()
            progress = max(0.0, min(1.0, progress))
            expected = max(0, min(total_inverters, math.ceil(total_inverters * progress)))
            detail = f'Ramping up after {wake_time}'
            return expected, 'ramp_up', detail

        if sleep_dt and current_time >= sleep_dt:
            if current_time <= sleep_dt + ramp_down:
                progress = (current_time - sleep_dt).total_seconds() / ramp_down.total_seconds()
                progress = max(0.0, min(1.0, progress))
                remaining = max(0, min(total_inverters, math.floor(total_inverters * (1 - progress))))
                detail = f'Ramping down after {sleep_time}'
                return remaining, 'ramp_down', detail
            return 0, 'night', f'After sleep window ({sleep_time})'

        return total_inverters, 'daytime', f'Productive window ({wake_time} - {sleep_time or "unset"})'

    def _fallback_expectation_for_array(self, array_name, current_time):
        """Provide conservative expectations when no learned patterns exist"""
        hour = current_time.hour
        if array_name == 'east':
            if hour < 6 or hour >= 18:
                return 0, 'night', 'Fallback night window'
            if 6 <= hour < 7:
                return 0, 'pre_wake', 'East fallback pre-dawn'
            if 7 <= hour < 8:
                return 6, 'ramp_up', 'East fallback ramping up'
            if 8 <= hour < 15:
                return 12, 'daytime', 'East fallback daytime expectation'
            if 15 <= hour < 17:
                return 6, 'ramp_down', 'East fallback winding down'
            return 0, 'night', 'East fallback evening shutdown'

        if array_name == 'south':
            if hour < 8 or hour >= 20:
                return 0, 'night', 'Fallback night window'
            if 8 <= hour < 9:
                return 5, 'ramp_up', 'South fallback ramping up'
            if 9 <= hour < 17:
                return 13, 'daytime', 'South fallback daytime expectation'
            if 17 <= hour < 19:
                return 8, 'ramp_down', 'South fallback winding down'
            return 0, 'night', 'South fallback evening shutdown'

        return 0, 'unknown', 'No fallback data'

    def _load_recent_production_history(self, days):
        """Fetch recent inverter production records for history-based alerts."""
        try:
            if not self.production_history_file.exists():
                return []

            with self.production_history_file.open('r', encoding='utf-8') as handle:
                data = json.load(handle)

            records = data.get('records', [])
            records.sort(key=lambda item: item.get('date', ''))
            return records[-days:]

        except Exception as error:
            print(f"⚠️ Could not load production history: {error}")
            return []

    def generate_underperformer_alerts(self, production_summary, alert_config,
                                       alert_state):
        """Alert when an inverter records zero production for the day."""
        try:
            entries = []
            if production_summary:
                entries = [
                    entry for entry in production_summary.get('entries', [])
                    if entry.get('serial')
                ]
            if not entries:
                return []

            current_time = datetime.now()
            summary_date = production_summary.get('date') or (
                current_time.date().isoformat()
            )

            today_str = current_time.date().isoformat()
            sunset_buffer = alert_config.get('sunset_buffer_minutes', 60)
            sunset_time = calculate_sunset_time()

            if summary_date == today_str:
                cutoff = sunset_time + timedelta(minutes=sunset_buffer)
                if current_time < cutoff:
                    return []

            if alert_state.get('zero_day_last_alert_date') == summary_date:
                return []

            zero_serials = [
                entry['serial']
                for entry in entries
                if entry.get('active_minutes', 0) == 0
            ]
            zero_count = len(zero_serials)
            total_inverters = len(entries)

            if zero_count == 0:
                return []

            if zero_count == total_inverters and total_inverters > 0:
                message = (
                    "CRITICAL: No inverter produced energy on "
                    f"{summary_date}. Entire system recorded zero output."
                )
            else:
                preview = ", ".join(zero_serials[:6])
                if zero_count > 6:
                    preview += f" +{zero_count - 6} more"
                message = (
                    "CRITICAL: "
                    f"{zero_count} inverter(s) produced zero energy on "
                    f"{summary_date}: {preview}."
                )

            alert_state['zero_day_last_alert_date'] = summary_date

            return [{
                'type': 'zero_day_inverters',
                'severity': 'CRITICAL',
                'message': message,
                'timestamp': current_time.isoformat(),
                'zero_serials': zero_serials,
                'summary_date': summary_date,
                'total_inverters_evaluated': total_inverters
            }]

        except Exception as error:
            print(f"⚠️ Zero-day alert evaluation failed: {error}")
            return []
    
    def get_expected_active_inverters(self, current_time):
        """Return expected counts and context for east/south arrays"""
        default_context = {
            'east_stage': 'fallback',
            'south_stage': 'fallback',
            'east_detail': 'No timing intelligence available',
            'south_detail': 'No timing intelligence available'
        }

        if not self.timing_intelligence:
            hour = current_time.hour
            if 6 <= hour <= 8:
                return (12, 0, "Early morning (fallback)", default_context)
            if 9 <= hour <= 16:
                return (12, 13, "Midday (fallback)", default_context)
            if 17 <= hour <= 19:
                return (0, 13, "Late day (fallback)", default_context)
            return (0, 0, "Night/dawn (fallback)", default_context)

        try:
            insights = self.timing_intelligence['get_insights']()
            array_groups = insights.get('array_groups', {})

            context = {
                'east_stage': 'unknown',
                'south_stage': 'unknown',
                'east_detail': '',
                'south_detail': ''
            }

            east_data = array_groups.get('east_facing', {})
            has_east_patterns = (
                east_data.get('typical_wake_time')
                and east_data.get('count', 0) > 0
            )
            if has_east_patterns:
                expected_east, east_stage, east_detail = (
                    self._compute_dynamic_expectation(
                        12,
                        east_data.get('typical_wake_time'),
                        east_data.get('typical_sleep_time'),
                        current_time
                    )
                )
            else:
                expected_east, east_stage, east_detail = (
                    self._fallback_expectation_for_array('east', current_time)
                )
            context['east_stage'] = east_stage
            context['east_detail'] = east_detail

            south_data = array_groups.get('south_facing', {})
            has_south_patterns = (
                south_data.get('typical_wake_time')
                and south_data.get('count', 0) > 0
            )
            if has_south_patterns:
                expected_south, south_stage, south_detail = (
                    self._compute_dynamic_expectation(
                        13,
                        south_data.get('typical_wake_time'),
                        south_data.get('typical_sleep_time'),
                        current_time
                    )
                )
            else:
                expected_south, south_stage, south_detail = (
                    self._fallback_expectation_for_array('south', current_time)
                )
            context['south_stage'] = south_stage
            context['south_detail'] = south_detail

            details = []
            if east_detail:
                details.append(f"East: {east_detail}")
            if south_detail:
                details.append(f"South: {south_detail}")
            reasoning = (
                " | ".join(details) if details else "No learned patterns"
            )

            return (expected_east, expected_south, reasoning, context)

        except Exception as exc:
            print(f"⚠️ Error getting timing expectations: {exc}")
            hour = current_time.hour
            if 6 <= hour <= 8:
                return (12, 0, "Early morning fallback", default_context)
            if 9 <= hour <= 16:
                return (12, 13, "Midday fallback", default_context)
            if 17 <= hour <= 19:
                return (0, 13, "Late day fallback", default_context)
            return (0, 0, "Night fallback", default_context)
    
    def classify_inverter_by_serial(self, serial):
        """Classify an inverter as east or south facing."""
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
        
    def generate_offline_inverter_alerts(self, detailed_stats, alert_config,
                                         alert_state):
        """Alert when the full array is offline across multiple polls."""
        try:
            if not detailed_stats:
                print("⚠️ No inverter stats available; skipping array check")
                return []

            current_time = datetime.now()
            start_hour = alert_config.get('daylight_start_hour', 7)
            if current_time.hour < start_hour:
                alert_state['system_down_count'] = 0
                return []

            sunset_time = calculate_sunset_time()
            sunset_buffer = alert_config.get('sunset_buffer_minutes', 60)
            cutoff = sunset_time - timedelta(minutes=sunset_buffer)
            if current_time >= cutoff:
                alert_state['system_down_count'] = 0
                return []

            threshold = alert_config.get('active_power_threshold', 0.05)
            interval_limit = alert_config.get('array_down_intervals', 3)
            interval_minutes = alert_config.get('polling_interval_minutes', 15)

            inverters = [
                stat for stat in detailed_stats if stat.get('serial')
            ]
            total_inverters = len(inverters)
            active_now = [
                stat for stat in inverters
                if stat.get('current_power', 0.0) > threshold
            ]

            if active_now:
                alert_state['system_down_count'] = 0
                alert_state['system_seen_active'] = True
                return []

            seen_active = alert_state.get('system_seen_active')
            if not seen_active:
                seen_active = any(
                    stat.get('current_power', 0.0) > threshold
                    or stat.get('max_power', 0.0) > threshold
                    or stat.get('ever_active')
                    for stat in inverters
                )
                alert_state['system_seen_active'] = seen_active

            if not alert_state.get('system_seen_active'):
                print("⏳ Waiting for first production before tracking outages")
                return []

            streak = alert_state.get('system_down_count', 0) + 1
            alert_state['system_down_count'] = streak
            print(f"⚠️ Entire array offline for {streak} interval(s)")

            if streak < interval_limit:
                return []

            down_minutes = streak * interval_minutes
            message = (
                "CRITICAL: Entire solar array offline for "
                f"{streak} consecutive polling intervals "
                f"({down_minutes} minutes)."
            )

            alert_state['system_down_count'] = interval_limit

            return [{
                'type': 'system_down',
                'severity': 'CRITICAL',
                'message': message,
                'timestamp': current_time.isoformat(),
                'consecutive_intervals': streak,
                'interval_minutes': interval_minutes,
                'total_inverters_reported': total_inverters
            }]

        except Exception as error:
            print(f"❌ Error evaluating array-down alerts: {error}")
            return []
    
    def should_send_alert(self, alert, last_alerts_sent):
        """Apply rate limiting before sending an alert."""
        try:
            alert_type = alert.get('type')
            current_time = datetime.now()
            
            # Check if we've sent this type of alert recently
            if alert_type in last_alerts_sent:
                last_iso = last_alerts_sent[alert_type]
                last_sent = datetime.fromisoformat(last_iso)
                seconds_since_last = (current_time - last_sent).total_seconds()
                minutes_since_last = seconds_since_last / 60

                # Critical: 30 min, Warning: 120 min
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
            # Locate config — search DATA_DIR / cwd / module dir
            email_config_path = None
            search_dirs = [os.getcwd(), os.path.dirname(__file__)]
            data_dir = os.environ.get('DATA_DIR')
            if data_dir:
                search_dirs.insert(0, data_dir)
            for d in search_dirs:
                candidate = os.path.join(d, 'email_config.json')
                if os.path.exists(candidate):
                    email_config_path = candidate
                    break

            if email_config_path is None:
                return {'success': False, 'error': 'Email not configured'}

            with open(email_config_path, 'r') as f:
                config = json.load(f)
            
            # Create email
            msg = MIMEText(detailed_msg)
            timestamp = datetime.now().strftime('%H:%M')
            msg['Subject'] = f'🚨 {severity}: Solar System Alert - {timestamp}'
            
            # Prefer friendly display name when available
            display_name = config.get('display_name', 'Solar Monitor')
            from_email = config['smtp_username']
            msg['From'] = f"{display_name} <{from_email}>"
            msg['To'] = config['email']
            
            # Send email
            smtp_host = config['smtp_server']
            smtp_port = int(config['smtp_port'])
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(config['smtp_username'], config['smtp_password'])
            server.send_message(msg)
            server.quit()
            
            print(f"📧 Alert email sent: {alert_msg}")
            return {'success': True}
            
        except Exception as e:
            print(f"❌ Failed to send alert email: {e}")
            return {'success': False, 'error': str(e)}
    
    def _send_imessage_via_ssh(self, phone, short_msg, config):
        """Send iMessage by SSHing to a Mac and running osascript there."""
        try:
            import paramiko
        except ImportError:
            return {'success': False, 'error': 'paramiko not installed; run: pip install paramiko'}

        ssh_host = config['ssh_host']
        ssh_user = config.get('ssh_user', 'admin')
        ssh_port = int(config.get('ssh_port', 22))
        ssh_key_path = config.get('ssh_key_path')
        ssh_password = config.get('ssh_password')

        # Escape single quotes inside the message so osascript doesn't break
        safe_msg = short_msg.replace('"', '\\"')

        script = (
            'tell application "Messages"\n'
            '    set targetService to 1st service whose service type = iMessage\n'
            f'    set targetBuddy to buddy "{phone}" of targetService\n'
            f'    send "{safe_msg}" to targetBuddy\n'
            'end tell'
        )
        command = f"osascript -e '{script.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'"
        # Use heredoc to avoid quoting issues with complex scripts
        command = f'osascript << \'APPLESCRIPT\'\n{script}\nAPPLESCRIPT'

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            connect_kwargs = {
                'hostname': ssh_host,
                'port': ssh_port,
                'username': ssh_user,
                'timeout': 15,
            }
            if ssh_key_path:
                connect_kwargs['key_filename'] = ssh_key_path
            elif ssh_password:
                connect_kwargs['password'] = ssh_password
            else:
                return {'success': False, 'error': 'No SSH auth method (key or password) configured'}

            client.connect(**connect_kwargs)
            _stdin, stdout, stderr = client.exec_command(command)
            exit_code = stdout.channel.recv_exit_status()
            err_output = stderr.read().decode().strip()

            if exit_code == 0:
                print(f"📱 iMessage sent via SSH ({ssh_user}@{ssh_host}): {short_msg}")
                return {'success': True}
            else:
                print(f"❌ SSH osascript failed (exit {exit_code}): {err_output}")
                return {'success': False, 'error': err_output}
        finally:
            client.close()

    def send_alert_imessage(self, alert_msg, severity):
        """Send alert via iMessage.

        When ``ssh_enabled`` is true in imessage_config.json the message is
        delivered by SSHing to the configured Mac host and running osascript
        there.  This is required when the monitor runs inside a Docker
        container (Linux) which cannot invoke osascript locally.
        """
        try:
            # Locate config file — search DATA_DIR / cwd as well as the module dir
            config_path = None
            search_dirs = [os.getcwd(), os.path.dirname(__file__)]
            data_dir = os.environ.get('DATA_DIR')
            if data_dir:
                search_dirs.insert(0, data_dir)
            for d in search_dirs:
                candidate = os.path.join(d, 'imessage_config.json')
                if os.path.exists(candidate):
                    config_path = candidate
                    break

            if config_path is None:
                return {'success': False, 'error': 'iMessage not configured'}

            with open(config_path, 'r') as f:
                config = json.load(f)

            if not config.get('imessage_enabled', False):
                return {'success': False, 'error': 'iMessage disabled'}

            phone = config['imessage_phone']

            # Build short message (iMessage has a practical length limit)
            short_msg = f"🚨 {severity}: {alert_msg[:100]}"
            if len(alert_msg) > 100:
                short_msg += "..."

            # --- SSH path (Docker / remote) -----------------------------------
            if config.get('ssh_enabled', False):
                return self._send_imessage_via_ssh(phone, short_msg, config)

            # --- Local path (native macOS) ------------------------------------
            safe_msg = short_msg.replace('"', '\\"')
            script = (
                'tell application "Messages"\n'
                '    set targetService to 1st service whose service type = iMessage\n'
                f'    set targetBuddy to buddy "{phone}" of targetService\n'
                f'    send "{safe_msg}" to targetBuddy\n'
                'end tell'
            )

            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True,
                text=True,
                timeout=15,
            )

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
        """Send an inverter alert using enabled delivery methods."""
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
    
    def _send_weather_suspension_alert(self, alert_config, weather_status):
        """Send one-time alert about weather-based suspension"""
        try:
            alert_state = self.load_alert_state()
            
            # Check if we've recently sent a suspension alert
            last_sent = alert_state.get('last_weather_suspension_alert')
            if last_sent:
                last_time = datetime.fromisoformat(last_sent)
                if datetime.now() - last_time < timedelta(hours=4):
                    return  # Don't spam weather suspension alerts
            
            weather_summary = weather_status.get('summary', 'Rain detected')
            
            suspension_alert = {
                'type': 'weather_suspension',
                'severity': 'INFO',
                'message': (
                    f"Solar alerts suspended due to rain. "
                    f"Current conditions: {weather_summary}. "
                    "Alerts will resume when weather clears."
                ),
                'timestamp': datetime.now().isoformat(),
                'weather_summary': weather_summary
            }
            
            # Determine delivery methods
            delivery_methods = []
            if alert_config.get('email_alerts_enabled', True):
                delivery_methods.append('email')
            if alert_config.get('imessage_alerts_enabled', True):
                delivery_methods.append('imessage')
            
            if delivery_methods:
                print("🌧️ Sending weather suspension notification")
                results = self.send_inverter_alert(
                    suspension_alert,
                    delivery_methods
                )
                
                # Update alert state
                success_count = sum(
                    1 for method, result in results if result.get('success')
                )
                if success_count > 0:
                    alert_state['last_weather_suspension_alert'] = (
                        datetime.now().isoformat()
                    )
                    self.save_alert_state(alert_state)
                    
        except Exception as e:
            print(f"⚠️ Error sending weather suspension alert: {e}")
    
    def check_and_send_alerts(self, detailed_stats, production_summary=None):
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
            
            # Check weather conditions for alert suspension
            if self.weather_monitor:
                weather_status = self.weather_monitor.get_weather_status()
                if weather_status.get('should_suspend_alerts', False):
                    # Send one-time rain alert if we haven't recently
                    self._send_weather_suspension_alert(
                        alert_config,
                        weather_status
                    )
                    print("🌧️ Alerts suspended due to rain")
                    return            # Load alert state
            alert_state = self.load_alert_state()
            
            # Generate alerts from instantaneous status and multi-day history
            pending_alerts = []
            pending_alerts.extend(
                self.generate_offline_inverter_alerts(
                    detailed_stats,
                    alert_config,
                    alert_state
                )
            )
            pending_alerts.extend(
                self.generate_underperformer_alerts(
                    production_summary,
                    alert_config,
                    alert_state
                )
            )
            
            if not pending_alerts:
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
            alert_state.setdefault('last_alerts_sent', {})
            last_sent = alert_state['last_alerts_sent']

            for alert in pending_alerts:
                if self.should_send_alert(alert, last_sent):
                    print(
                        "🚨 Sending {severity} alert: {message}".format(
                            severity=alert['severity'],
                            message=alert['message']
                        )
                    )

                    results = self.send_inverter_alert(alert, delivery_methods)
                    
                    # Update alert state if successful
                    success_count = sum(
                        1
                        for method, result in results
                        if result.get('success')
                    )
                    if success_count > 0:
                        last_sent[alert['type']] = datetime.now().isoformat()
                        alert_state['alert_count'] = (
                            alert_state.get('alert_count', 0) + 1
                        )

                        success_message = (
                            "✅ Alert sent via {success}/{total} methods".format(
                                success=success_count,
                                total=len(results)
                            )
                        )
                        print(success_message)
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
    sample_state = {
        'last_alerts_sent': {},
        'system_seen_active': True,
        'system_down_count': 0
    }
    alerts = manager.generate_offline_inverter_alerts(
        sample_stats,
        sample_config,
        sample_state
    )
    
    print(f"Generated {len(alerts)} alerts:")
    for alert in alerts:
        print(f"  {alert['severity']}: {alert['message']}")
