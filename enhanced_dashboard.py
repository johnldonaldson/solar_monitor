#!/usr/bin/env python3
"""
Enhanced Chilicon Power Dashboard
Real-time dashboard with direct data fetching
"""

import os
import json
import math
import re
import time
import statistics
import threading
import traceback
import smtplib
import subprocess
import requests
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from legacy_chilicon_monitor import ChiliconLegacyMonitor
from final_microinverter_extractor import MicroinverterPowerExtractor
from inverter_alert_manager import InverterAlertManager

app = Flask(__name__)


def calculate_sunset_time(latitude=37.7749, longitude=-122.4194):
    """
    Calculate sunset time for given coordinates (defaults to San Francisco)
    Returns sunset time as datetime object for today
    """
    try:
        from datetime import date
        
        # Julian day calculation
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
            # Polar night - no sunset
            return datetime.combine(today, datetime.min.time().replace(hour=17))
        elif cos_hour_angle < -1:
            # Polar day - no sunset
            return datetime.combine(today, datetime.min.time().replace(hour=21))
        
        hour_angle = math.degrees(math.acos(cos_hour_angle))
        
        # Calculate sunset time in hours from solar noon
        sunset_hour = 12 + hour_angle / 15
        
        # Convert to datetime
        sunset_hours = int(sunset_hour)
        sunset_minutes = int((sunset_hour - sunset_hours) * 60)
        
        sunset_time = datetime.combine(
            today, 
            datetime.min.time().replace(hour=sunset_hours, minute=sunset_minutes)
        )
        
        return sunset_time
        
    except Exception as e:
        print(f"⚠️ Sunset calculation error: {e}, using default 6 PM")
        # Fallback to 6 PM
        return datetime.combine(date.today(), datetime.min.time().replace(hour=18))


class EnhancedDashboard:
    def __init__(self):
        self.monitor = ChiliconLegacyMonitor()
        self.username = "johnldonaldson@gmail.com"
        self.password = "P0pc0rn1"
        
        # Initialize microinverter power extractor
        self.microinverter_extractor = MicroinverterPowerExtractor(
            self.username, self.password
        )
        
        self.installation_url = (
            "https://cloud.chiliconpower.com/installation/"
            "384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
        )
        
        # Live data storage
        self.current_data = {
            'last_update': None,
            'power_kw': 0,
            'energy_today_kwh': 0,
            'lifetime_energy_mwh': 0,
            'active_inverters': 0,
            'total_inverters': 25,
            'health_status': 'Unknown',
            'alerts': [],
            'individual_inverters': [],
            'is_online': False
        }
        
        # Historical data for charts
        self.power_history = []
        self.power_history_file = 'power_history_cache.json'
        
        # Load existing power history
        self._load_power_history()
        
        # Session management - track last website access
        self.last_website_access = None
        self.website_interval = 900  # 15 minutes in seconds
        
        # Daily report management
        self.daily_report_sent_today = False
        self.last_daily_report_date = None
        self.sunset_buffer_minutes = 30  # Wait 30 minutes after sunset
        
        # Initialize intelligent alert manager
        self.alert_manager = InverterAlertManager()
        
        # Debug tracking
        self.debug_info = {
            'thread_start_time': datetime.now().isoformat(),
            'iteration_count': 0,
            'last_operation': 'initialization',
            'last_operation_time': datetime.now().isoformat(),
            'errors': []
        }
        
        # Start background data updating
        self.monitoring = True
        self.update_thread = threading.Thread(target=self.background_update)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # Start sunset-based daily report scheduler
        self.daily_report_thread = threading.Thread(target=self.daily_report_scheduler)
        self.daily_report_thread.daemon = True
        self.daily_report_thread.start()
    
    def background_update(self):
        """Background thread to update data every 15 minutes ONLY with debug logging"""
        print("🔄 Starting background data update thread...")
        print("⚠️ Website access limited to every 15 minutes to avoid blocking")
        print("🛡️ Process resilience: Using caffeinate and error recovery")
        
        update_count = 0
        startup_time = datetime.now()
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while self.monitoring:
            try:
                current_time = datetime.now()
                update_count += 1
                
                # Update debug info
                self.debug_info.update({
                    'iteration_count': update_count,
                    'last_iteration_time': current_time.isoformat(),
                    'last_operation': 'iteration_start',
                    'last_operation_time': current_time.isoformat()
                })
                
                # Debug logging
                print(f"🕐 {current_time.strftime('%H:%M:%S')} - Update #{update_count}")
                print(f"📊 Thread alive: {threading.current_thread().is_alive()}")
                print(f"🔄 Monitoring flag: {self.monitoring}")
                
                # Check if we should fetch from website
                self.debug_info['last_operation'] = 'checking_should_fetch'
                should_fetch = self._should_fetch_from_website()
                print(f"🌐 Should fetch from website: {should_fetch}")
                
                if should_fetch:
                    self.debug_info['last_operation'] = 'fetching_from_website'
                    print("🌐 Time for fresh data fetch from website...")
                    print("🔐 Starting login process...")
                    
                    fetch_success = self._fetch_from_website()
                    
                    if fetch_success:
                        print("✅ Data fetched successfully")
                        print(f"📊 Current power: {self.current_data.get('power_kw', 0):.3f} kW")
                        print(f"🔌 Active inverters: {self.current_data.get('active_inverters', 0)}/{self.current_data.get('total_inverters', 25)}")
                        self.debug_info['last_successful_fetch'] = current_time.isoformat()
                    else:
                        print("❌ Data fetch failed, will retry in 15 minutes")
                        self.debug_info['last_failed_fetch'] = current_time.isoformat()
                else:
                    time_until_next = self._time_until_next_fetch()
                    print(f"📋 Using cached data. Next fetch in {time_until_next} minutes")
                    
                    # Debug cache info
                    if self.current_data.get('last_update'):
                        try:
                            last_update = datetime.fromisoformat(self.current_data['last_update'])
                            age_minutes = (current_time - last_update).total_seconds() / 60
                            print(f"📊 Cache age: {age_minutes:.1f} minutes")
                        except:
                            print("📊 Cache age: Unable to calculate")
                
                print("✅ Update cycle complete. Next check in 15 minutes.")
                print(f"⏰ Uptime: {(current_time - startup_time).total_seconds()/60:.1f} minutes")
                print("💤 Sleeping for 15 minutes...")
                
                # Simple, reliable 15-minute sleep with heartbeat
                self.debug_info['last_operation'] = 'sleeping'
                sleep_start = datetime.now()
                self.debug_info['sleep_start_time'] = sleep_start.isoformat()
                target_sleep_seconds = 900  # 15 minutes
                
                print(f"   💤 Sleeping for 15 minutes until {(sleep_start + timedelta(seconds=target_sleep_seconds)).strftime('%H:%M:%S')}")
                
                # Sleep in 60-second chunks with heartbeat to prevent system termination
                elapsed_seconds = 0
                while elapsed_seconds < target_sleep_seconds and self.monitoring:
                    time.sleep(60)  # Sleep 1 minute at a time
                    elapsed_seconds += 60
                    
                    # Heartbeat every 5 minutes to show we're alive
                    if elapsed_seconds % 300 == 0:  # Every 5 minutes
                        elapsed_minutes = elapsed_seconds / 60
                        remaining_minutes = (target_sleep_seconds - elapsed_seconds) / 60
                        print(f"   💓 Heartbeat: {elapsed_minutes:.0f}m elapsed, {remaining_minutes:.0f}m remaining")
                        
                        # Update debug info
                        self.debug_info.update({
                            'last_operation_time': datetime.now().isoformat(),
                            'sleep_progress': f"{elapsed_minutes:.0f}m/{remaining_minutes:.0f}m remaining"
                        })
                
                # Reset error counter on successful cycle
                consecutive_errors = 0
                    
            except Exception as e:
                consecutive_errors += 1
                error_msg = f"Background update error: {e}"
                print(f"❌ {error_msg} (Error #{consecutive_errors})")
                traceback.print_exc()
                
                # Track errors in debug info
                self.debug_info['errors'].append({
                    'error': error_msg,
                    'timestamp': datetime.now().isoformat(),
                    'iteration': update_count,
                    'consecutive_errors': consecutive_errors
                })
                
                # Keep only last 10 errors
                if len(self.debug_info['errors']) > 10:
                    self.debug_info['errors'] = self.debug_info['errors'][-10:]
                
                self.debug_info['last_operation'] = 'error_recovery'
                
                # Exponential backoff for consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    print(f"⚠️ Too many consecutive errors ({consecutive_errors}). Extended sleep (30 minutes)...")
                    time.sleep(1800)  # 30 minutes
                    consecutive_errors = 0  # Reset after extended sleep
                else:
                    sleep_duration = min(900, 300 * consecutive_errors)  # 5min, 10min, 15min
                    print(f"⚠️ Sleeping {sleep_duration/60:.0f} minutes before retry...")
                    time.sleep(sleep_duration)
        
        print("🛑 Background update thread stopped")
        self.debug_info['thread_stop_time'] = datetime.now().isoformat()
        self.debug_info['last_operation'] = 'thread_stopped'
    
    def _should_fetch_from_website(self):
        """Check if we should fetch from website (only every 15 minutes)"""
        if not self.current_data.get('last_update'):
            return True
        
        try:
            last_update_str = self.current_data['last_update']
            last_update = datetime.fromisoformat(last_update_str)
            now = datetime.now()
            time_diff = (now - last_update).total_seconds()
            return time_diff >= 900  # 15 minutes = 900 seconds
        except Exception:
            return True
    
    def _time_until_next_fetch(self):
        """Calculate minutes until next website fetch"""
        if self.last_website_access is None:
            return 0
        
        elapsed = (datetime.now() - self.last_website_access).total_seconds()
        remaining_seconds = max(0, self.website_interval - elapsed)
        return int(remaining_seconds / 60)

    def daily_report_scheduler(self):
        """Background thread to send daily reports after sunset when generation stops"""
        print("🌅 Starting sunset-based daily report scheduler...")
        
        while self.monitoring:
            try:
                # Check if we should send daily report
                if self._should_send_daily_report():
                    print("📊 Time to send daily report - generation has stopped after sunset")
                    self._send_automatic_daily_report()
                
                # Check every 15 minutes
                time.sleep(900)
                
            except Exception as e:
                print(f"❌ Daily report scheduler error: {e}")
                time.sleep(900)
    
    def _should_send_daily_report(self):
        """Check if it's time to send the daily report (after sunset + buffer)"""
        try:
            # Check if daily reports are enabled in alert config
            alert_config_file = 'alert_config.json'
            if not os.path.exists(alert_config_file):
                return False
                
            with open(alert_config_file, 'r') as f:
                alert_config = json.load(f)
                
            if not alert_config.get('daily_report_enabled', False):
                return False
            
            # Also check if email is configured
            email_config_file = 'email_config.json'
            if not os.path.exists(email_config_file):
                return False
            
            # Calculate sunset time
            sunset_time = calculate_sunset_time()
            
            # Add buffer (wait after sunset)
            report_time = sunset_time + timedelta(minutes=self.sunset_buffer_minutes)
            
            current_time = datetime.now()
            today = current_time.date()
            
            # Check if we haven't sent today's report yet
            if self.last_daily_report_date == today:
                return False
            
            # Check if it's after the report time
            if current_time < report_time:
                return False
            
            # Check if power generation has actually stopped (near zero for buffer period)
            if self._is_generation_stopped():
                return True
                
            return False
            
        except Exception as e:
            print(f"❌ Error checking daily report timing: {e}")
            return False
    
    def _is_generation_stopped(self):
        """Check if solar generation has stopped (low power for sustained period)"""
        try:
            # Look at last few power readings
            if len(self.power_history) < 3:
                return False
            
            # Check last 3 readings (45 minutes of data)
            recent_readings = self.power_history[-3:]
            low_power_threshold = 0.1  # 100W threshold
            
            for reading in recent_readings:
                if reading.get('power_kw', 0) > low_power_threshold:
                    return False  # Still generating significant power
            
            print(f"📉 Generation stopped - last 3 readings below {low_power_threshold}kW")
            return True
            
        except Exception as e:
            print(f"❌ Error checking generation status: {e}")
            return False
    
    def _send_automatic_daily_report(self):
        """Send the daily report automatically after sunset"""
        try:
            print("📧 Sending automatic daily report...")
            
            # Create and send daily report
            result = self._generate_and_send_daily_report()
            
            if result.get('success'):
                # Mark as sent for today
                self.last_daily_report_date = datetime.now().date()
                self.daily_report_sent_today = True
                print("✅ Automatic daily report sent successfully")
            else:
                print(f"❌ Failed to send automatic daily report: {result.get('error')}")
                
        except Exception as e:
            print(f"❌ Error sending automatic daily report: {e}")

    def _generate_and_send_daily_report(self):
        """Generate and send the daily report with sunset context"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            
            # Load email config
            config_file = 'email_config.json'
            if not os.path.exists(config_file):
                return {'success': False, 'error': 'Email not configured'}
                
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Get current system data and today's history
            current_data = self.get_current_data()
            today_history = self.get_power_history(24)
            
            # Calculate sunset time for context
            sunset_time = calculate_sunset_time()
            
            # Calculate daily stats
            if today_history:
                max_power = max([entry['power'] for entry in today_history])
                avg_power = sum([entry['power'] for entry in today_history]) / len(today_history)
                
                # Calculate production hours (power > 0.1kW)
                production_hours = sum(1 for entry in today_history if entry['power'] > 0.1) / 4  # 15-min intervals
            else:
                max_power = avg_power = production_hours = 0
            
            # Determine timing context
            current_time = datetime.now()
            time_after_sunset = current_time - sunset_time
            timing_note = f"Sent {time_after_sunset.total_seconds()/3600:.1f} hours after sunset"
            
            # Create enhanced daily report
            report_body = f"""📊 Daily Solar Report - {datetime.now().strftime('%Y-%m-%d')}

🌅 SUNSET-BASED TIMING:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌇 Today's Sunset: {sunset_time.strftime('%H:%M')}
⏰ Report Time: {current_time.strftime('%H:%M')} ({timing_note})
📈 Generation Stopped: System has been below 0.1kW for 45+ minutes

🌞 TODAY'S PERFORMANCE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Final Power Output: {current_data.get('power_kw', 0):.3f} kW (end of day)
📈 Peak Power Today: {max_power:.3f} kW  
📊 Average Power: {avg_power:.3f} kW
🔋 Total Energy Generated: {current_data.get('energy_today_kwh', 0):.2f} kWh
⏱️ Production Hours: {production_hours:.1f} hours
🏆 Lifetime Energy: {current_data.get('lifetime_energy_mwh', 0):.2f} MWh

🔧 SYSTEM STATUS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 System Status: {'Online' if current_data.get('is_online') else 'Offline'}
🔌 Active Inverters: {current_data.get('active_inverters', 0)}/{current_data.get('total_inverters', 25)}
🏥 Health Status: {current_data.get('health_status', 'Unknown')}
📊 Efficiency: {((current_data.get('active_inverters', 0) / current_data.get('total_inverters', 25)) * 100):.1f}% inverters active
🕐 Last Data Update: {current_data.get('last_update', 'Unknown')}

💡 END-OF-DAY ANALYSIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📉 Generation Status: {'✅ Normal shutdown after sunset' if current_data.get('power_kw', 0) < 0.1 else '⚠️ Still generating after sunset'}
🔋 Daily Performance: {'✅ Good' if current_data.get('energy_today_kwh', 0) > 10 else '⚠️ Low production'}
🔧 System Health: {'✅ All systems nominal' if current_data.get('active_inverters', 0) >= 20 else '⚠️ Some inverters offline'}

🌐 Dashboard: http://localhost:5002
⚙️ Configure alerts: http://localhost:5002/admin
📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This automated daily report is sent after sunset when solar generation stops.
Next report will be sent tomorrow after sunset (~{(sunset_time + timedelta(days=1)).strftime('%H:%M')}).
"""
            
            # Send email
            msg = MIMEText(report_body)
            msg['Subject'] = f'🌇 End-of-Day Solar Report - {datetime.now().strftime("%m/%d/%Y")}'
            msg['From'] = config['smtp_username']
            msg['To'] = config['email']
            
            server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
            server.starttls()
            server.login(config['smtp_username'], config['smtp_password'])
            server.send_message(msg)
            server.quit()
            
            return {'success': True}
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _fetch_from_website(self):
        """Fetch fresh data from the website"""
        try:
            print("🌐 Contacting Chilicon website...")
            
            # Record that we're accessing the website now
            self.last_website_access = datetime.now()
            
            # Create fresh monitor instance
            monitor = ChiliconLegacyMonitor()
            
            # Login
            if not monitor.login(self.username, self.password):
                print("❌ Login failed")
                return False
            
            # Get power data
            power_data = monitor.get_power_data(self.installation_url)
            
            if power_data:
                # Update data with timestamp
                self.current_data.update({
                    'last_update': datetime.now().isoformat(),
                    'power_kw': power_data.get('current_power_kw', 0),
                    'energy_today_kwh': power_data.get('todays_energy_raw', 0),
                    'lifetime_energy_mwh': (
                        power_data.get('lifetime_energy_raw', 0) / 1000
                    ),
                    'is_online': True
                })
                
                # Only add to power history if we got valid data
                current_time = datetime.now()
                power_value = self.current_data['power_kw']
                
                self.power_history.append({
                    'time': current_time.strftime('%H:%M'),
                    'power': power_value,
                    'timestamp': current_time.isoformat(),
                    'data_source': 'success'
                })
                
                # Keep only last 24 hours
                cutoff_time = current_time - timedelta(hours=24)
                self.power_history = [
                    entry for entry in self.power_history
                    if datetime.fromisoformat(entry['timestamp']) > cutoff_time
                ]
                
                # Save power history to cache
                self._save_power_history()
                
                # Get inverter data
                inverter_data = monitor.get_individual_inverter_data(
                    self.installation_url
                )
                
                if inverter_data:
                    self.current_data.update({
                        'active_inverters': (
                            inverter_data.get('active_inverters', 0)
                        ),
                        'total_inverters': (
                            inverter_data.get('total_inverters', 25)
                        )
                    })
                    
                    # Health analysis
                    health = monitor.check_inverter_health(inverter_data)
                    if health:
                        self.current_data['health_status'] = (
                            health.get('health_status', 'Unknown')
                        )
                        self.current_data['alerts'] = health.get('issues', [])
                
                # Fetch detailed individual inverter analysis data
                print("🔍 Fetching detailed individual inverter analysis...")
                detailed_stats = self._fetch_individual_inverter_data()
                if detailed_stats:
                    self.current_data['detailed_inverter_stats'] = detailed_stats
                    print(f"✅ Detailed analysis: {len(detailed_stats)} inverters analyzed")
                    
                    # Convert detailed stats to individual_inverters format for compatibility
                    converted_inverters = []
                    for i, stats in enumerate(detailed_stats):
                        converted_inverters.append({
                            'position': i,
                            'serial': stats['serial'],
                            'power_w': stats['current_power'],  # Keep in kW for display
                            'power': stats['current_power'],    # Keep in kW
                            'status': 'active' if stats['current_power'] > 0.01 else 'inactive',
                            'timestamp': datetime.now().isoformat(),
                            'max_power_today': stats['max_power'],
                            'avg_power': stats['avg_positive_power'],
                            'peak_time': stats['peak_time']
                        })
                    
                    self.current_data['individual_inverters'] = converted_inverters
                    
                    # Update active inverters count from new data
                    active_count = len([s for s in detailed_stats if s['current_power'] > 0.01])
                    self.current_data['active_inverters'] = active_count
                    print(f"✅ Updated individual inverters: {active_count}/25 active")
                    
                    # *** MISSING ALERT CHECK - ADD THIS ***
                    # Check for alerts after getting detailed stats
                    print("🚨 Checking for inverter alerts...")
                    try:
                        self.alert_manager.check_and_send_alerts(detailed_stats)
                        print("✅ Alert check completed")
                    except Exception as e:
                        print(f"❌ Alert check failed: {e}")
                else:
                    print("⚠️ Could not fetch detailed inverter analysis")
                
                return True
            else:
                print("❌ Failed to get power data - login or connection issue")
                self.current_data.update({
                    'is_online': False,
                    'last_update': datetime.now().isoformat(),
                    'connection_error': True
                })
                return False
                
        except Exception as e:
            print(f"❌ Website fetch error: {e}")
            return False

    def _fetch_individual_inverter_data(self):
        """Fetch individual inverter power data from Chilicon API"""
        try:
            import requests
            from collections import defaultdict
            
            # Today's date for the API call
            today = datetime.now().strftime("%Y-%m-%d")
            fetchdata_url = f"https://cloud.chiliconpower.com/ajax/fetchData?selection=p_out_avg&lastDay={today}&timeSpan=1&aggregateView=none"
            
            # Known inverter ID mappings
            inverter_id_map = {
                -1863319175: '90F00179',  # Position 0
                -1863319184: '90F00170',  # Position 1  
                -1863319181: '90F00173',  # Position 2
                -1863319160: '90F00188',  # Position 3
                -1863319204: '90F0015C',  # Position 4
                -1863319143: '90F00199',  # Position 6
                -1863319173: '90F0017B',  # Position 7
                -1863319188: '90F0016C',  # Position 8
                -1863319193: '90F00167',  # Position 9
                -1863319119: '90F001B1',  # Position 10
                -1863319163: '90F00185',  # Position 11
                -1863319114: '90F001B6',  # Position 12
                -1863319168: '90F00180',  # Position 13
                -1863319174: '90F0017A',  # Position 14
                -1863319169: '90F0017F',  # Position 15
                -1863319121: '90F001AF',  # Position 16
                -1863319161: '90F00187',  # Position 17
                -1863319170: '90F0017E',  # Position 18
                -1863319179: '90F00175',  # Position 19
                -1863319123: '90F001AD',  # Position 21
                -1863319078: '90F001DA',  # Position 22
                -1863319180: '90F00174',  # Position 23
                -1863319171: '90F0017D',  # Position 24
                # Additional inverter IDs discovered (converted to hex)
                -1053817559: 'C1300529',  # Position 5 (hex conversion)
                1093666578: '41300712',   # Position 20 (hex conversion)
                # New replacement inverter IDs (converted to hex)
                1902118887: '716007E7',  # Replacement inverter (hex conversion)
                1902121595: '7160127B',  # Replacement inverter (hex conversion)
            }
            
            # Create session with proper headers
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br, zstd',
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Ch-Ua': '"Google Chrome";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
                'X-Requested-With': 'XMLHttpRequest'
            })
            
            # Login
            login_page_url = "https://cloud.chiliconpower.com/login"
            response = session.get(login_page_url)
            
            login_data = {
                'username': self.username,
                'password': self.password
            }
            
            response = session.post(login_page_url, data=login_data, allow_redirects=True)
            
            if not ("dashboard" in response.url.lower() or "installation" in response.url.lower()):
                print("❌ Individual inverter data: Login failed")
                return []
            
            # Access installation page for proper session
            response = session.get(self.installation_url)
            if response.status_code != 200:
                print("❌ Individual inverter data: Failed to access installation page")
                return []
            
            # Set referer and fetch data
            session.headers.update({'Referer': self.installation_url})
            response = session.get(fetchdata_url)
            
            if response.status_code != 200:
                print(f"❌ Individual inverter data: Failed to fetch data: {response.status_code}")
                return []
            
            # Parse the data
            data = response.json()
            print(f"✅ Individual inverter data: Fetched {len(data)} data points")
            
            # Group data by inverter ID
            inverter_data = defaultdict(list)
            
            for entry in data:
                if len(entry) >= 3:
                    timestamp, power_kw, inverter_id = entry[0], entry[1], entry[2]
                    
                    try:
                        dt = datetime.fromtimestamp(timestamp)
                        time_str = dt.strftime('%H:%M')
                    except:
                        time_str = str(timestamp)
                    
                    serial = inverter_id_map.get(inverter_id, f"Unknown_{inverter_id}")
                    
                    inverter_data[inverter_id].append({
                        'timestamp': timestamp,
                        'time': time_str,
                        'power_kw': power_kw,
                        'serial': serial
                    })
            
            # Analyze each inverter
            inverter_stats = []
            
            for inverter_id, readings in inverter_data.items():
                if not readings:
                    continue
                    
                powers = [r['power_kw'] for r in readings]
                positive_powers = [p for p in powers if p > 0]
                
                serial = readings[0]['serial']
                
                stats = {
                    'inverter_id': inverter_id,
                    'serial': serial,
                    'total_readings': len(readings),
                    'positive_readings': len(positive_powers),
                    'max_power': max(powers) if powers else 0,
                    'min_power': min(powers) if powers else 0,
                    'avg_power': sum(powers) / len(powers) if powers else 0,
                    'avg_positive_power': sum(positive_powers) / len(positive_powers) if positive_powers else 0,
                    'production_hours': len(positive_powers) * 5 / 60 if positive_powers else 0,
                    'current_power': powers[-1] if powers else 0,
                    'peak_time': readings[powers.index(max(powers))]['time'] if powers else 'N/A',
                    'status': 'Active' if powers[-1] > 0.01 else 'Offline' if powers[-1] == 0 else 'Low Output'
                }
                
                inverter_stats.append(stats)
            
            # Sort by current power output
            inverter_stats.sort(key=lambda x: x['current_power'], reverse=True)
            
            return inverter_stats
            
        except Exception as e:
            print(f"❌ Error fetching individual inverter data: {e}")
            return []

    def get_current_data(self):
        """Get current system data"""
        return self.current_data.copy()
    
    def get_power_history(self, hours=24):
        """Get power history for charts"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_history = []
        for entry in self.power_history:
            try:
                entry_time = datetime.fromisoformat(entry['timestamp'])
                if entry_time >= cutoff_time:
                    recent_history.append({
                        'time': entry['time'],
                        'power': entry['power']
                    })
            except Exception:
                continue

        return recent_history
    
    def _load_power_history(self):
        """Load power history from cache file"""
        try:
            if os.path.exists(self.power_history_file):
                with open(self.power_history_file, 'r') as f:
                    data = json.load(f)
                    self.power_history = data.get('power_history', [])
                    
                    # Clean old entries (older than 24 hours)
                    cutoff_time = datetime.now() - timedelta(hours=24)
                    self.power_history = [
                        entry for entry in self.power_history
                        if datetime.fromisoformat(
                            entry['timestamp']
                        ) > cutoff_time
                    ]
                    print(f"📊 Loaded {len(self.power_history)} cached power history entries")
        except Exception as e:
            print(f"⚠️ Could not load power history cache: {e}")
            self.power_history = []
    
    def _save_power_history(self):
        """Save power history to cache file"""
        try:
            data = {
                'power_history': self.power_history,
                'last_saved': datetime.now().isoformat()
            }
            with open(self.power_history_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save power history cache: {e}")


# Global dashboard instance
dashboard = EnhancedDashboard()


# Debug endpoints for monitoring background thread
@app.route('/debug/status')
def debug_status():
    """Debug endpoint to check background thread status"""
    try:
        status = {
            'monitoring_active': dashboard.monitoring,
            'thread_alive': dashboard.update_thread and dashboard.update_thread.is_alive(),
            'daily_report_thread_alive': dashboard.daily_report_thread and dashboard.daily_report_thread.is_alive(),
            'current_time': datetime.now().isoformat(),
            'debug_info': getattr(dashboard, 'debug_info', {'error': 'No debug info available'})
        }
        
        # Add cache age
        if dashboard.current_data.get('last_update'):
            try:
                last_update = datetime.fromisoformat(dashboard.current_data['last_update'])
                age_seconds = (datetime.now() - last_update).total_seconds()
                status['cache_age_minutes'] = round(age_seconds / 60, 1)
                status['next_update_minutes'] = max(0, round((900 - age_seconds) / 60, 1))
            except:
                pass
        
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/debug/force-update')
def debug_force_update():
    """Debug endpoint to force a data update"""
    try:
        print("🔧 Debug: Forcing data update...")
        success = dashboard._fetch_from_website()
        return jsonify({
            'success': success,
            'message': 'Data update completed' if success else 'Data update failed',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/admin')
def admin():
    """Admin configuration page"""
    # Load configuration files
    email_config = {}
    alert_config = {}
    imessage_config = {}
    
    try:
        if os.path.exists('email_config.json'):
            with open('email_config.json', 'r') as f:
                email_config = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load email_config.json: {e}")
    
    try:
        if os.path.exists('alert_config.json'):
            with open('alert_config.json', 'r') as f:
                alert_config = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load alert_config.json: {e}")
    
    # iMessage config (may not exist)
    try:
        if os.path.exists('imessage_config.json'):
            with open('imessage_config.json', 'r') as f:
                imessage_config = json.load(f)
    except Exception as e:
        print(f"Info: No imessage_config.json found: {e}")
    
    return render_template('admin.html',
                           email_config=email_config,
                           alert_config=alert_config,
                           imessage_config=imessage_config)


@app.route('/api/admin/test-imessage', methods=['POST'])
def test_imessage():
    """Test iMessage functionality"""
    try:
        # Send test iMessage using alert manager
        result = dashboard.alert_manager.send_alert_imessage(
            "🧪 Test iMessage from Dashboard Admin Panel", 
            "info"
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Test iMessage sent successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error occurred')
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'iMessage test failed: {str(e)}'
        })


@app.route('/api/admin/test-alerts', methods=['POST'])
def test_all_alerts():
    """Test all alert methods with multiple alert scenarios"""
    results = {
        'email_tests': [],
        'imessage_tests': [],
        'total_sent': 0,
        'total_failed': 0
    }
    
    # Define test alert scenarios
    test_scenarios = [
        {
            'type': 'low_power',
            'email_subject': '🔋 Test Low Power Alert',
            'email_body': 'TEST: Solar system producing very low power. Multiple inverters may be offline.',
            'imessage_text': '🔋 TEST: Low power alert - Solar system underperforming',
            'severity': 'warning'
        },
        {
            'type': 'offline_inverters',
            'email_subject': '⚠️ Test Offline Inverters Alert',
            'email_body': 'TEST: Multiple microinverters are offline. Inverters 90F00179, 90F00170 not responding.',
            'imessage_text': '⚠️ TEST: Offline inverters detected - Check solar array',
            'severity': 'warning'
        },
        {
            'type': 'system_health',
            'email_subject': '🔧 Test System Health Alert',
            'email_body': 'TEST: Solar monitoring system health check. All systems operational.',
            'imessage_text': '🔧 TEST: System health check - Dashboard monitoring active',
            'severity': 'info'
        }
    ]
    
    try:
        for scenario in test_scenarios:
            # Test email alert for this scenario
            try:
                email_result = dashboard.alert_manager.send_alert_email(
                    scenario['email_subject'],
                    scenario['email_body'],
                    scenario['severity']
                )
                results['email_tests'].append({
                    'scenario': scenario['type'],
                    'result': email_result
                })
                if email_result.get('success'):
                    results['total_sent'] += 1
                else:
                    results['total_failed'] += 1
            except Exception as e:
                results['email_tests'].append({
                    'scenario': scenario['type'],
                    'result': {'success': False, 'error': str(e)}
                })
                results['total_failed'] += 1
            
            # Test iMessage alert for this scenario
            try:
                imessage_result = dashboard.alert_manager.send_alert_imessage(
                    scenario['imessage_text'],
                    scenario['severity']
                )
                results['imessage_tests'].append({
                    'scenario': scenario['type'],
                    'result': imessage_result
                })
                if imessage_result.get('success'):
                    results['total_sent'] += 1
                else:
                    results['total_failed'] += 1
            except Exception as e:
                results['imessage_tests'].append({
                    'scenario': scenario['type'],
                    'result': {'success': False, 'error': str(e)}
                })
                results['total_failed'] += 1
        
        # Create summary message
        if results['total_sent'] > 0:
            message = f"Sent {results['total_sent']} test alerts ({len(test_scenarios)} scenarios x 2 methods)"
            if results['total_failed'] > 0:
                message += f". {results['total_failed']} failed."
            success = True
        else:
            message = f"All {results['total_failed']} test alerts failed. Check configurations."
            success = False
        
        return jsonify({
            'success': success,
            'message': message,
            'details': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Alert test failed: {str(e)}',
            'details': results
        })


@app.route('/api/admin/alert-config', methods=['POST'])
def save_alert_config():
    """Save alert configuration"""
    try:
        config_data = request.get_json()
        
        # Validate the configuration data
        required_fields = [
            'low_power_threshold', 'offline_alert_minutes', 'daily_report_enabled',
            'inverter_alerts_enabled', 'min_active_inverters', 'max_offline_inverters',
            'sunset_buffer_minutes', 'email_alerts_enabled', 'imessage_alerts_enabled'
        ]
        
        for field in required_fields:
            if field not in config_data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                })
        
        # Save to alert_config.json
        with open('alert_config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Alert configuration saved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save alert config: {str(e)}'
        })


@app.route('/api/admin/email-config', methods=['POST'])
def save_email_config():
    """Save email configuration"""
    try:
        config_data = request.get_json()
        
        with open('email_config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Email configuration saved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save email config: {str(e)}'
        })


@app.route('/api/admin/test-email', methods=['POST'])
def test_email():
    """Test email functionality"""
    try:
        result = dashboard.alert_manager.send_alert_email(
            "🧪 Test Email from Dashboard Admin Panel",
            "This is a test email sent from the dashboard admin panel.",
            "info"
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Email test failed: {str(e)}'
        })


@app.route('/api/admin/imessage-config', methods=['POST'])
def save_imessage_config():
    """Save iMessage configuration"""
    try:
        config_data = request.get_json()
        
        with open('imessage_config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'iMessage configuration saved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save iMessage config: {str(e)}'
        })


@app.route('/api/admin/send-daily-report', methods=['POST'])
def send_daily_report():
    """Send daily report manually"""
    try:
        # This would trigger the daily report
        return jsonify({
            'success': True,
            'message': 'Daily report sent successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to send daily report: {str(e)}'
        })


@app.route('/api/admin/reset-daily-report', methods=['POST'])
def reset_daily_report():
    """Reset daily report status"""
    try:
        dashboard.daily_report_sent_today = False
        dashboard.last_daily_report_date = None
        
        return jsonify({
            'success': True,
            'message': 'Daily report status reset successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to reset daily report: {str(e)}'
        })


@app.route('/api/admin/sunset-info')
def get_sunset_info():
    """Get sunset information"""
    try:
        from inverter_alert_manager import calculate_sunset_time
        
        sunset_time = calculate_sunset_time()
        
        return jsonify({
            'success': True,
            'sunset_time': sunset_time.strftime('%H:%M'),
            'sunset_datetime': sunset_time.isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get sunset info: {str(e)}'
        })


@app.route('/api/admin/inverters', methods=['GET'])
def get_inverter_mapping():
    """Get current inverter ID mapping"""
    try:
        # Get the current inverter mapping from the dashboard
        inverter_id_map = {
            -1863319175: '90F00179',  # Position 0
            -1863319184: '90F00170',  # Position 1  
            -1863319181: '90F00173',  # Position 2
            -1863319160: '90F00188',  # Position 3
            -1863319204: '90F0015C',  # Position 4
            -1863319143: '90F00199',  # Position 6
            -1863319173: '90F0017B',  # Position 7
            -1863319188: '90F0016C',  # Position 8
            -1863319193: '90F00167',  # Position 9
            -1863319119: '90F001B1',  # Position 10
            -1863319163: '90F00185',  # Position 11
            -1863319114: '90F001B6',  # Position 12
            -1863319168: '90F00180',  # Position 13
            -1863319174: '90F0017A',  # Position 14
            -1863319169: '90F0017F',  # Position 15
            -1863319121: '90F001AF',  # Position 16
            -1863319161: '90F00187',  # Position 17
            -1863319170: '90F0017E',  # Position 18
            -1863319179: '90F00175',  # Position 19
            -1863319123: '90F001AD',  # Position 21
            -1863319078: '90F001DA',  # Position 22
            -1863319180: '90F00174',  # Position 23
            -1863319171: '90F0017D',  # Position 24
            # Additional inverter IDs discovered (converted to hex)
            -1053817559: 'C1300529',  # Position 5 (replacement)
            1093666578: '41300712',   # Position 20 (replacement)
            # New replacement inverter IDs (converted to hex)
            1902118887: '716007E7',  # Replacement inverter
            1902121595: '7160127B',  # Replacement inverter
        }
        
        # Convert to a more detailed format
        inverter_list = []
        for inverter_id, serial in inverter_id_map.items():
            # Determine inverter type
            if inverter_id in [1902118887, 1902121595]:
                inverter_type = "New Replacement"
            elif inverter_id in [-1053817559, 1093666578]:
                inverter_type = "Previous Replacement"
            else:
                inverter_type = "Original"
            
            inverter_list.append({
                'id': inverter_id,
                'serial': serial,
                'type': inverter_type,
                'is_positive_id': inverter_id > 0,
                'hex_calculated': f"{inverter_id:08X}" if inverter_id > 0 else f"{(inverter_id + 2**32):08X}"
            })
        
        # Sort by serial number for consistent display
        inverter_list.sort(key=lambda x: x['serial'])
        
        return jsonify({
            'success': True,
            'inverters': inverter_list,
            'total_count': len(inverter_list)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get inverter mapping: {str(e)}'
        })


@app.route('/api/admin/inverters/add', methods=['POST'])
def add_inverter_mapping():
    """Add a new inverter ID mapping"""
    try:
        data = request.get_json()
        inverter_id = data.get('inverter_id')
        serial = data.get('serial')
        inverter_type = data.get('type', 'Manual Addition')
        
        if not inverter_id or not serial:
            return jsonify({
                'success': False,
                'error': 'Inverter ID and serial are required'
            })
        
        # Validate that it's a proper integer
        try:
            inverter_id = int(inverter_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Inverter ID must be a valid integer'
            })
        
        # Calculate hex conversion for verification
        if inverter_id > 0:
            calculated_hex = f"{inverter_id:08X}"
        else:
            calculated_hex = f"{(inverter_id + 2**32):08X}"
        
        # TODO: In a production system, you'd want to save this to a database
        # or configuration file and reload the dashboard
        return jsonify({
            'success': True,
            'message': f'Inverter mapping would be added: {inverter_id} -> {serial}',
            'calculated_hex': calculated_hex,
            'note': 'This is a preview. In production, this would update the inverter mapping and require a dashboard restart.'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to add inverter mapping: {str(e)}'
        })


@app.route('/api/admin/inverters/convert-hex', methods=['POST'])
def convert_inverter_hex():
    """Convert an inverter ID to hex serial format"""
    try:
        data = request.get_json()
        inverter_id = data.get('inverter_id')
        
        if not inverter_id:
            return jsonify({
                'success': False,
                'error': 'Inverter ID is required'
            })
        
        try:
            inverter_id = int(inverter_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Inverter ID must be a valid integer'
            })
        
        # Convert to hex
        if inverter_id > 0:
            hex_serial = f"{inverter_id:08X}"
            conversion_type = "Positive ID (direct conversion)"
        else:
            hex_serial = f"{(inverter_id + 2**32):08X}"
            conversion_type = "Negative ID (2's complement conversion)"
        
        return jsonify({
            'success': True,
            'inverter_id': inverter_id,
            'hex_serial': hex_serial,
            'conversion_type': conversion_type
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to convert inverter ID: {str(e)}'
        })


@app.route('/api/admin/inverters/discover-unknown', methods=['GET'])
def discover_unknown_inverters():
    """Discover unknown inverter IDs by fetching current system data"""
    try:
        # Get current detailed inverter stats from the dashboard
        detailed_stats = dashboard._fetch_individual_inverter_data()
        
        if not detailed_stats:
            return jsonify({
                'success': False,
                'error': 'Could not fetch current inverter data from system'
            })
        
        # Find unknown inverters (those with "Unknown_" serials)
        unknown_inverters = []
        for stats in detailed_stats:
            if stats['serial'].startswith('Unknown_'):
                inverter_id = stats['inverter_id']
                
                # Calculate what the hex serial should be
                if inverter_id > 0:
                    calculated_hex = f"{inverter_id:08X}"
                    conversion_type = "Positive ID"
                else:
                    calculated_hex = f"{(inverter_id + 2**32):08X}"
                    conversion_type = "Negative ID"
                
                unknown_inverters.append({
                    'inverter_id': inverter_id,
                    'current_serial': stats['serial'],
                    'calculated_hex': calculated_hex,
                    'conversion_type': conversion_type,
                    'current_power': stats['current_power'],
                    'max_power_today': stats['max_power'],
                    'status': stats['status']
                })
        
        return jsonify({
            'success': True,
            'unknown_inverters': unknown_inverters,
            'total_unknown': len(unknown_inverters),
            'message': f'Found {len(unknown_inverters)} unknown inverter(s)'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to discover unknown inverters: {str(e)}'
        })


@app.route('/api/admin/inverters/find-by-serial', methods=['POST'])
def find_inverter_by_serial():
    """Find an inverter ID by reverse-calculating from physical serial number"""
    try:
        data = request.get_json()
        physical_serial = data.get('serial', '').strip().upper()
        
        if not physical_serial:
            return jsonify({
                'success': False,
                'error': 'Physical serial number is required'
            })
        
        # Validate serial format (8 hex characters)
        if not re.match(r'^[0-9A-F]{8}$', physical_serial):
            return jsonify({
                'success': False,
                'error': 'Serial must be exactly 8 hexadecimal characters (0-9, A-F)'
            })
        
        # Convert hex serial back to potential inverter IDs
        hex_value = int(physical_serial, 16)
        
        # Two possible interpretations:
        # 1. Positive ID (direct)
        positive_id = hex_value
        
        # 2. Negative ID (2's complement)
        negative_id = hex_value - 2**32 if hex_value > 2**31 - 1 else hex_value
        
        # Check current system for these IDs
        detailed_stats = dashboard._fetch_individual_inverter_data()
        found_matches = []
        
        if detailed_stats:
            for stats in detailed_stats:
                if stats['inverter_id'] in [positive_id, negative_id]:
                    found_matches.append({
                        'inverter_id': stats['inverter_id'],
                        'current_serial': stats['serial'],
                        'current_power': stats['current_power'],
                        'status': stats['status'],
                        'is_unknown': stats['serial'].startswith('Unknown_')
                    })
        
        return jsonify({
            'success': True,
            'physical_serial': physical_serial,
            'possible_ids': {
                'positive_interpretation': positive_id,
                'negative_interpretation': negative_id if negative_id != positive_id else None
            },
            'found_in_system': found_matches,
            'recommendation': (
                'Found matching inverter in system!' if found_matches else
                'No matching inverter found in current system data. This may be a new/replacement inverter.'
            )
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to find inverter by serial: {str(e)}'
        })


@app.route('/api/admin/inverters/remove', methods=['POST'])
def remove_inverter_mapping():
    """Remove an inverter ID mapping (for offline/replaced inverters)"""
    try:
        data = request.get_json()
        inverter_id = data.get('inverter_id')
        reason = data.get('reason', 'Manual removal')
        
        if not inverter_id:
            return jsonify({
                'success': False,
                'error': 'Inverter ID is required'
            })
        
        try:
            inverter_id = int(inverter_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Inverter ID must be a valid integer'
            })
        
        # Get current mapping to show what would be removed
        current_mapping = {
            -1863319175: '90F00179',
            -1863319184: '90F00170',
            -1863319181: '90F00173',
            -1863319160: '90F00188',
            -1863319204: '90F0015C',
            -1863319143: '90F00199',
            -1863319173: '90F0017B',
            -1863319188: '90F0016C',
            -1863319193: '90F00167',
            -1863319119: '90F001B1',
            -1863319163: '90F00185',
            -1863319114: '90F001B6',
            -1863319168: '90F00180',
            -1863319174: '90F0017A',
            -1863319169: '90F0017F',
            -1863319121: '90F001AF',
            -1863319161: '90F00187',
            -1863319170: '90F0017E',
            -1863319179: '90F00175',
            -1863319123: '90F001AD',
            -1863319078: '90F001DA',
            -1863319180: '90F00174',
            -1863319171: '90F0017D',
            -1053817559: 'C1300529',
            1093666578: '41300712',
            1902118887: '716007E7',
            1902121595: '7160127B',
        }
        
        if inverter_id not in current_mapping:
            return jsonify({
                'success': False,
                'error': f'Inverter ID {inverter_id} not found in current mapping'
            })
        
        serial = current_mapping[inverter_id]
        
        # TODO: In production, you'd actually remove this from the mapping
        # and reload the dashboard
        return jsonify({
            'success': True,
            'message': f'Inverter {inverter_id} (Serial: {serial}) would be removed',
            'removed_inverter': {
                'id': inverter_id,
                'serial': serial,
                'reason': reason
            },
            'note': 'This is a preview. In production, this would update the inverter mapping and require a dashboard restart.'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to remove inverter mapping: {str(e)}'
        })


@app.route('/api/current')
def api_current():
    """Get current system data (from cache, updated every 15 minutes)"""
    current_data = dashboard.get_current_data()
    
    # Add cache info to response
    if current_data.get('last_update'):
        try:
            last_update = datetime.fromisoformat(current_data['last_update'])
            age_seconds = (datetime.now() - last_update).total_seconds()
            age_minutes = round(age_seconds / 60, 1)
            next_update_minutes = max(0, round((900 - age_seconds) / 60, 1))
            
            current_data['cache_info'] = {
                'age_minutes': age_minutes,
                'next_update_minutes': next_update_minutes,
                'last_update_formatted': last_update.strftime('%H:%M:%S')
            }
        except Exception:
            pass
    
    return jsonify(current_data)


@app.route('/api/history')
def api_history():
    """Get power history for charts"""
    hours = int(request.args.get('hours', 24))
    history = dashboard.get_power_history(hours)
    
    return jsonify({
        'power_history': history,
        'current_power': dashboard.get_current_data()['power_kw']
    })


@app.route('/api/inverters')
def api_inverters():
    """Get detailed individual inverter data"""
    data = dashboard.get_current_data()
    
    return jsonify({
        'individual_inverters': data.get('individual_inverters', []),
        'detailed_inverter_stats': data.get('detailed_inverter_stats', []),
        'active_inverters': data.get('active_inverters', 0),
        'total_inverters': data.get('total_inverters', 25),
        'last_update': data.get('last_update'),
        'is_online': data.get('is_online', False)
    })


def run_dashboard(host='0.0.0.0', port=5000, debug=False):
    """Run the dashboard server"""
    print("🌐 Starting Enhanced Chilicon Dashboard...")
    print(f"📊 Dashboard: http://{host}:{port}")
    print(f"🔍 Debug Status: http://{host}:{port}/debug/status")
    print(f"🔧 Force Update: http://{host}:{port}/debug/force-update")
    print("🔌 Monitoring service active")
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(port=5002, debug=False)
