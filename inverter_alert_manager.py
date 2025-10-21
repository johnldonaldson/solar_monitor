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
import statistics
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

    def generate_underperformer_alerts(self, production_summary, alert_config):
        """Identify consistently weak inverters using recent daily production history."""
        window_days = alert_config.get('underperformer_history_days', 7)
        ratio_threshold = alert_config.get('underperformer_ratio_threshold', 0.5)
        critical_ratio = alert_config.get('underperformer_critical_ratio', 0.25)
        min_days = alert_config.get('underperformer_min_days', 3)
        zero_threshold = alert_config.get('underperformer_zero_kwh', 0.05)
        zero_day_threshold = alert_config.get('underperformer_zero_day_threshold', 2)
        min_median_kwh = alert_config.get('underperformer_min_median_kwh', 0.3)

        history_records = self._load_recent_production_history(window_days)

        # Merge the current day's summary (if provided) into the evaluation window
        if production_summary and production_summary.get('entries'):
            summary_date = production_summary.get('date')
            if not summary_date:
                summary_date = datetime.now().date().isoformat()

            snapshot = {
                'date': summary_date,
                'entries': production_summary.get('entries', []),
                'total_inverter_hours': production_summary.get('total_inverter_hours', 0.0),
                'average_inverter_hours': production_summary.get('average_inverter_hours', 0.0),
                'total_inverter_energy_kwh': production_summary.get('total_inverter_energy_kwh', 0.0)
            }

            history_records = [
                record for record in history_records
                if record.get('date') != summary_date
            ]
            history_records.append(snapshot)
            history_records.sort(key=lambda item: item.get('date', ''))
            history_records = history_records[-window_days:]

        inverter_samples = {}
        valid_days = []

        for record in history_records:
            entries = record.get('entries', [])
            energies = [
                entry.get('energy_kwh', 0.0) for entry in entries
                if entry.get('energy_kwh') is not None
            ]
            if not energies:
                continue

            median_energy = statistics.median(energies)
            if median_energy < min_median_kwh:
                continue

            record_date = record.get('date')
            valid_days.append(record_date)

            for entry in entries:
                serial = entry.get('serial')
                if not serial:
                    continue

                energy_kwh = entry.get('energy_kwh', 0.0)
                ratio = (energy_kwh / median_energy) if median_energy else 0.0
                inverter_samples.setdefault(serial, []).append({
                    'date': record_date,
                    'energy_kwh': round(energy_kwh, 3),
                    'median_energy_kwh': round(median_energy, 3),
                    'ratio': round(ratio, 3)
                })

        if not valid_days:
            return []

        underperformer_alerts = []

        for serial, samples in inverter_samples.items():
            if len(samples) < min_days:
                continue

            zero_days = [s for s in samples if s['energy_kwh'] <= zero_threshold]
            low_days = [s for s in samples if s['ratio'] < ratio_threshold and s['energy_kwh'] > zero_threshold]

            if len(zero_days) < zero_day_threshold and len(low_days) < min_days:
                continue

            avg_ratio = round(
                sum(s['ratio'] for s in samples) / len(samples),
                3
            )
            avg_energy = round(
                sum(s['energy_kwh'] for s in samples) / len(samples),
                3
            )

            severity = 'CRITICAL' if (
                avg_ratio <= critical_ratio or len(zero_days) >= zero_day_threshold
            ) else 'WARNING'

            summary_line = (
                f"{severity}: Inverter {serial} averaging {avg_ratio * 100:.0f}% "
                f"of fleet median ({avg_energy:.2f} kWh/day) across {len(samples)} days"
            )

            underperformer_alerts.append({
                'type': f'underperformer_{serial}',
                'severity': severity,
                'message': summary_line,
                'timestamp': datetime.now().isoformat(),
                'history_window_days': len(valid_days),
                'low_days': len(low_days),
                'zero_days': len(zero_days),
                'samples_analyzed': samples,
                'analysis_days': valid_days,
                'ratio_threshold': ratio_threshold,
                'zero_threshold': zero_threshold
            })

        if underperformer_alerts:
            alert_count = len(underperformer_alerts)
            print(f"📉 Identified {alert_count} persistent underperformers")

        return underperformer_alerts
    
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
                east_data.get('typical_wake_time') and east_data.get('count', 0) > 0
            )
            if has_east_patterns:
                expected_east, east_stage, east_detail = self._compute_dynamic_expectation(
                    12,
                    east_data.get('typical_wake_time'),
                    east_data.get('typical_sleep_time'),
                    current_time
                )
            else:
                expected_east, east_stage, east_detail = self._fallback_expectation_for_array(
                    'east', current_time
                )
            context['east_stage'] = east_stage
            context['east_detail'] = east_detail

            south_data = array_groups.get('south_facing', {})
            has_south_patterns = (
                south_data.get('typical_wake_time') and south_data.get('count', 0) > 0
            )
            if has_south_patterns:
                expected_south, south_stage, south_detail = self._compute_dynamic_expectation(
                    13,
                    south_data.get('typical_wake_time'),
                    south_data.get('typical_sleep_time'),
                    current_time
                )
            else:
                expected_south, south_stage, south_detail = self._fallback_expectation_for_array(
                    'south', current_time
                )
            context['south_stage'] = south_stage
            context['south_detail'] = south_detail

            details = []
            if east_detail:
                details.append(f"East: {east_detail}")
            if south_detail:
                details.append(f"South: {south_detail}")
            reasoning = " | ".join(details) if details else "No learned patterns"

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
            expected_east, expected_south, reasoning, expectation_context = (
                self.get_expected_active_inverters(current_time)
            )
            east_stage = expectation_context.get('east_stage', 'unknown')
            south_stage = expectation_context.get('south_stage', 'unknown')
            expected_total = expected_east + expected_south
            
            print(f"🧠 Intelligent expectations: East={expected_east}, South={expected_south} ({reasoning})")
            print(f"   🛈 Stages -> East: {east_stage}, South: {south_stage}")
            
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
            
            ramp_stages = {'pre_wake', 'ramp_up', 'ramp_down', 'night'}
            east_ready = expected_east > 0 and east_stage not in ramp_stages
            south_ready = expected_south > 0 and south_stage not in ramp_stages

            # 2. Check east array against expectations (only if we expect it to be active)
            if east_ready:
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
            if south_ready:
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
            stage_ready = (
                (expected_east > 0 and east_stage not in ramp_stages)
                or (expected_south > 0 and south_stage not in ramp_stages)
            )
            if expected_total > 0 and stage_ready and expected_total >= 3:
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
                timing_context = (
                    f"Alert generated at {current_time.strftime('%H:%M')} "
                    f"({minutes_until_sunset:.0f} min until sunset). "
                    f"East stage: {east_stage}, South stage: {south_stage}. {reasoning}"
                )
                
                for alert_item in alerts:
                    alert_item['timing_context'] = timing_context
                    alert_item['sunset_buffer_minutes'] = sunset_buffer_minutes
                    alert_item['expected_east'] = expected_east
                    alert_item['expected_south'] = expected_south
                    alert_item['actual_east'] = east_active
                    alert_item['actual_south'] = south_active
                    alert_item['east_stage'] = east_stage
                    alert_item['south_stage'] = south_stage
                    alert_item['east_detail'] = expectation_context.get('east_detail')
                    alert_item['south_detail'] = expectation_context.get('south_detail')
            
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
            
            # Load alert state
            alert_state = self.load_alert_state()
            
            # Generate alerts from instantaneous status and multi-day history
            pending_alerts = []
            pending_alerts.extend(
                self.generate_offline_inverter_alerts(detailed_stats, alert_config)
            )
            pending_alerts.extend(
                self.generate_underperformer_alerts(production_summary, alert_config)
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
            for alert in pending_alerts:
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
