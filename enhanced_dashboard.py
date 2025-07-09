#!/usr/bin/env python3
"""
Enhanced Chilicon Power Dashboard
Real-time dashboard with direct data fetching
"""

import time
import threading
import json
import os
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from legacy_chilicon_monitor import ChiliconLegacyMonitor
from final_microinverter_extractor import MicroinverterPowerExtractor
from inverter_alert_manager import InverterAlertManager
import math

app = Flask(__name__)


def calculate_sunset_time(latitude=37.7749, longitude=-122.4194):
    """
    Calculate sunset time for given coordinates (defaults to San Francisco)
    Returns sunset time as datetime object for today
    """
    try:
        from datetime import date
        import math
        
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
        """Background thread to update data every 15 minutes ONLY"""
        print("🔄 Starting background data update thread...")
        print("⚠️ Website access limited to every 15 minutes to avoid blocking")
        update_count = 0
        while self.monitoring:
            try:
                current_time = datetime.now().strftime('%H:%M:%S')
                update_count += 1
                print(f"🕐 {current_time} - Update #{update_count}")
                
                # Only fetch data if it's time (first time or after 15 minutes)
                if self._should_fetch_from_website():
                    print("🌐 Time for fresh data fetch from website...")
                    if self._fetch_from_website():
                        print("✅ Data fetched successfully")
                    else:
                        print("❌ Data fetch failed, will retry in 15 minutes")
                else:
                    time_until_next = self._time_until_next_fetch()
                    print(f"📋 Using cached data. Next fetch in {time_until_next} minutes")
                
                print("✅ Update cycle complete. Next check in 15 minutes.")
                time.sleep(900)  # Sleep 15 minutes (900 seconds)
            except Exception as e:
                print(f"❌ Background update error: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(900)
    
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

🌐 Dashboard: http://localhost:5001
⚙️ Configure alerts: http://localhost:5001/admin
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
                # This prevents false zero readings during login failures
                current_time = datetime.now()
                power_value = self.current_data['power_kw']
                
                # Only record if we have a successful data fetch
                # Don't record zeros during system login failures
                self.power_history.append({
                    'time': current_time.strftime('%H:%M'),
                    'power': power_value,
                    'timestamp': current_time.isoformat(),
                    'data_source': 'success'  # Mark as successful data fetch
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
                print("� Fetching detailed individual inverter analysis...")
                detailed_stats = self._fetch_individual_inverter_data()
                if detailed_stats:
                    self.current_data['detailed_inverter_stats'] = (
                        detailed_stats
                    )
                    print(f"✅ Detailed analysis: {len(detailed_stats)} "
                          f"inverters analyzed")
                    
                    # Convert detailed stats to individual_inverters format for compatibility
                    # Keep power values in kW (don't multiply by 1000)
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
                     # Recalculate health status using accurate detailed data
                    # Use total inverters from system (25) not just detailed stats count
                    total_inverters = self.current_data.get('total_inverters', 25)
                    updated_inverter_data = {
                        'total_inverters': total_inverters,
                        'active_inverters': active_count,
                        'inactive_inverters': (
                            total_inverters - active_count
                        ),
                        'underperforming_count': 0,  # Calculated by health check
                        'individual_powers': (
                            [s['current_power'] for s in detailed_stats]
                        ),
                        'producing_powers': [
                            s['current_power'] for s in detailed_stats
                            if s['current_power'] > 0.01
                        ]
                    }
                    
                    # Update health status with accurate data
                    health = monitor.check_inverter_health(updated_inverter_data)
                    if health:
                        self.current_data['health_status'] = (
                            health.get('health_status', 'Unknown')
                        )
                        self.current_data['alerts'] = health.get('issues', [])
                        activity_rate = (
                            (active_count / total_inverters) * 100 
                            if total_inverters > 0 else 0
                        )
                        status = health.get('health_status', 'Unknown')
                        print(f"🏥 Health Status: {status} "
                              f"({active_count}/{total_inverters} active = "
                              f"{activity_rate:.1f}%)")
                    
                    print(f"✅ Updated individual inverters with detailed data: "
                          f"{active_count}/25 active")
                    
                    # Check for alerts after updating inverter data
                    try:
                        self.alert_manager.check_and_send_alerts(detailed_stats)
                    except Exception as e:
                        print(f"⚠️ Alert checking failed: {e}")
                else:
                    print("⚠️ Could not fetch detailed inverter analysis")
                    # Only use legacy data as absolute fallback
                    print("🔄 Attempting legacy data extraction as fallback...")
                    individual_power_data = (
                        self.microinverter_extractor.extract_individual_power()
                    )
                    
                    if individual_power_data:
                        detailed_inverters = (
                            self.microinverter_extractor
                            .get_detailed_inverter_data()
                        )
                        self.current_data['individual_inverters'] = detailed_inverters
                        self.current_data['active_inverters'] = individual_power_data['active_inverters']
                        print("⚠️ Using legacy fallback data")
                    else:
                        print("❌ Both detailed and legacy data fetch failed")
                
                power_kw = self.current_data['power_kw']
                active_inv = self.current_data['active_inverters']
                total_inv = self.current_data['total_inverters']
                print(f"✅ Website data: {power_kw:.3f} kW, "
                      f"{active_inv}/{total_inv} inverters")
                print("⏰ Next website access in 15 minutes")
                
                return True
            else:
                print("❌ Failed to get power data - login or connection issue")
                # Mark system as temporarily offline but don't record zero power
                self.current_data.update({
                    'is_online': False,
                    'last_update': datetime.now().isoformat(),
                    'connection_error': True
                })
                # Do NOT add power history entry for failed connections
                # This prevents false zero readings in the power graph
                return False
                
        except Exception as e:
            print(f"❌ Website fetch error: {e}")
            return False
    
    def _map_inverter_serials(self, inverter_map):
        """Map inverter positions to actual hex serial numbers"""
        # Mapping from position to actual hex serial numbers
        position_to_serial = {
            0: '90F00179',   # ID: -1863319175
            1: '90F00170',   # ID: -1863319184
            2: '90F00173',   # ID: -1863319181
            3: '90F00188',   # ID: -1863319160
            4: '90F0015C',   # ID: -1863319204
            5: 'Unknown_6',  # No mapping available
            6: '90F00199',   # ID: -1863319143
            7: '90F0017B',   # ID: -1863319173
            8: '90F0016C',   # ID: -1863319188
            9: '90F00167',   # ID: -1863319193
            10: '90F001B1',  # ID: -1863319119
            11: '90F00185',  # ID: -1863319163
            12: '90F001B6',  # ID: -1863319114
            13: '90F00180',  # ID: -1863319168
            14: '90F0017A',  # ID: -1863319174
            15: '90F0017F',  # ID: -1863319169
            16: '90F001AF',  # ID: -1863319121
            17: '90F00187',  # ID: -1863319161
            18: '90F0017E',  # ID: -1863319170
            19: '90F00175',  # ID: -1863319179
            20: 'Unknown_21',  # No mapping available
            21: '90F001AD',  # ID: -1863319123
            22: '90F001DA',  # ID: -1863319078
            23: '90F00174',  # ID: -1863319180
            24: '90F0017D',  # ID: -1863319171
        }
        
        # Update the inverter map with actual serial numbers
        mapped_inverters = []
        for inverter in inverter_map:
            position = inverter.get('index', -1)
            actual_serial = position_to_serial.get(
                position, inverter.get('serial', 'Unknown')
            )
            
            # Create updated inverter entry
            mapped_inverter = {
                'index': position,
                'serial': actual_serial,
                'power_w': inverter.get('power_w', 0),
                'status': inverter.get('status', 'Unknown')
            }
            mapped_inverters.append(mapped_inverter)
        
        return mapped_inverters

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
                    print(f"📊 Loaded {len(self.power_history)} cached "
                          f"power history entries")
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
    
    def clean_false_zero_readings(self):
        """Remove false zero power readings caused by login failures"""
        print("🧹 Cleaning false zero power readings...")
        
        # Load current history
        self._load_power_history()
        
        original_count = len(self.power_history)
        
        # Filter out suspicious zero readings during daylight hours
        cleaned_history = []
        for entry in self.power_history:
            try:
                # Parse timestamp
                timestamp = datetime.fromisoformat(entry['timestamp'])
                hour = timestamp.hour
                power = entry.get('power', 0)
                
                # Check if this is a suspicious zero reading
                # (zero power during daylight hours 8 AM - 6 PM)
                is_suspicious_zero = (
                    power == 0.0 and 
                    8 <= hour <= 18 and  # Daylight hours
                    entry.get('data_source') != 'success'  # Not marked as successful
                )
                
                if not is_suspicious_zero:
                    cleaned_history.append(entry)
                else:
                    print(f"   🗑️  Removing suspicious zero reading at {entry['time']} ({power} kW)")
                    
            except (ValueError, KeyError) as e:
                # Keep entry if we can't parse it
                print(f"   ⚠️  Keeping unparseable entry: {e}")
                cleaned_history.append(entry)
        
        # Update history
        self.power_history = cleaned_history
        removed_count = original_count - len(cleaned_history)
        
        print(f"✅ Cleaned {removed_count} false zero readings")
        print(f"📊 Power history: {len(self.power_history)} entries remaining")
        
        # Save cleaned history
        self._save_power_history()
        
        return removed_count
    
    def daily_report_scheduler(self):
        """Background thread to send daily reports based on sunset time"""
        print("🌅 Starting daily report scheduler...")
        while self.monitoring:
            try:
                # Check if we already sent the report today
                if self.daily_report_sent_today:
                    # Sleep until tomorrow
                    time_until_midnight = (
                        datetime.combine(datetime.now().date() + timedelta(days=1), datetime.min.time()) -
                        datetime.now()
                    ).total_seconds()
                    print(f"⏳ Waiting for midnight to reset daily report flag ({time_until_midnight/60:.1f} minutes)")
                    time.sleep(time_until_midnight)
                    self.daily_report_sent_today = False
                    continue
                
                # Calculate sunset time for today
                sunset_time = calculate_sunset_time()
                sunset_time = sunset_time.replace(tzinfo=None)  # Remove timezone info for comparison
                
                # Current time
                now = datetime.now()
                
                # Check if it's time to send the report (30 minutes after sunset)
                report_time = sunset_time + timedelta(minutes=self.sunset_buffer_minutes)
                
                if now >= report_time and now.date() == sunset_time.date():
                    print("🌇 Sending daily report based on sunset time...")
                    self.send_daily_report()
                    self.daily_report_sent_today = True
                else:
                    # Sleep until the next check (e.g., 10 minutes)
                    time_until_next_check = (report_time - now).total_seconds()
                    if time_until_next_check > 0:
                        print(f"⏳ Waiting for next report check ({time_until_next_check/60:.1f} minutes)")
                        time.sleep(min(time_until_next_check, 3600))  # Check again in 10 minutes or less
                    else:
                        # If we missed the time, force send the report and reset the flag
                        print("⚠️ Missed scheduled report time, sending report now")
                        self.send_daily_report()
                        self.daily_report_sent_today = True
            
            except Exception as e:
                print(f"❌ Daily report scheduler error: {e}")
                time.sleep(3600)  # Sleep 1 hour on error
    
    def send_daily_report(self):
        """Send the daily report email"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            
            # Load email config
            config_file = 'email_config.json'
            if not os.path.exists(config_file):
                print("⚠️ Email configuration not found, skipping daily report")
                return
            
            with open(config_file, 'r') as f:
                config = json.load(f)
            
            # Get current system data
            current_data = self.get_current_data()
            
            # Get today's power history
            today_history = self.get_power_history(24)
            
            # Calculate comprehensive daily stats
            if today_history:
                power_values = [entry['power'] for entry in today_history]
                max_power = max(power_values)
                avg_power = sum(power_values) / len(power_values)
                min_power = min(power_values)
                
                # Calculate production hours (power > 0.01 kW)
                production_entries = [p for p in power_values if p > 0.01]
                production_hours = len(production_entries) * 0.25  # Each entry represents ~15 min
                
                # Check if system is currently producing (for sunset detection)
                current_power = current_data.get('power_kw', 0)
                is_currently_producing = current_power > 0.01
                
                # Estimate efficiency
                inverter_efficiency = (current_data.get('active_inverters', 0) / current_data.get('total_inverters', 25)) * 100
            else:
                max_power = avg_power = min_power = 0
                production_hours = 0
                is_currently_producing = False
                inverter_efficiency = 0
            
            # Determine report timing context
            current_hour = datetime.now().hour
            if current_hour >= 20 or current_hour <= 6:
                timing_note = "📅 End-of-day report"
            elif not is_currently_producing and current_hour >= 16:
                timing_note = "🌅 Post-sunset report (solar production complete)"
            else:
                timing_note = "☀️ Mid-day report (solar production ongoing)"
            
            # Generate comprehensive report
            report_body = f"""📊 Daily Solar Report - {datetime.now().strftime('%A, %B %d, %Y')}
{timing_note}

🌞 TODAY'S SOLAR PERFORMANCE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚡ Current Power: {current_data.get('power_kw', 0):.3f} kW
📈 Peak Power Today: {max_power:.3f} kW  
📊 Average Power: {avg_power:.3f} kW
📉 Minimum Power: {min_power:.3f} kW
🔋 Energy Generated Today: {current_data.get('energy_today_kwh', 0):.2f} kWh
⏰ Production Hours: {production_hours:.1f} hours
🏆 Lifetime Energy: {current_data.get('lifetime_energy_mwh', 0):.2f} MWh

🔧 SYSTEM HEALTH & STATUS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🟢 System Status: {'Online' if current_data.get('is_online') else 'Offline'}
🔌 Active Inverters: {current_data.get('active_inverters', 0)}/{current_data.get('total_inverters', 25)}
📊 Inverter Efficiency: {inverter_efficiency:.1f}%
🏥 Health Status: {current_data.get('health_status', 'Unknown')}
🕐 Last Data Update: {current_data.get('last_update', 'Unknown')}

📈 DAILY SUMMARY:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• {'✅ System performed well today' if max_power > 2.0 else '⚠️ Below expected peak performance'}
• {'✅ All inverters operational' if inverter_efficiency > 95 else f'⚠️ {100-inverter_efficiency:.0f}% inverters may need attention'}
• {'🌙 Solar production complete for today' if not is_currently_producing and current_hour >= 16 else '☀️ Solar production ongoing'}

🌐 Dashboard: http://localhost:5001
📧 Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This automated report is sent after solar production ends for the day.
Configure timing and alerts at: http://localhost:5001/admin
"""
            
            # Send email
            msg = MIMEText(report_body)
            report_date = datetime.now().strftime("%m/%d/%Y")
            energy_summary = f"{current_data.get('energy_today_kwh', 0):.1f}kWh"
            msg['Subject'] = f'🌞 Daily Solar Report - {report_date} - {energy_summary} Generated'
            msg['From'] = config['smtp_username']
            msg['To'] = config['email']
            
            print(f"📧 Sending daily report to {config['email']}")
            print(f"📊 Today's stats: {energy_summary}, Peak: {max_power:.2f}kW, {production_hours:.1f}h production")
            
            server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
            server.starttls()
            server.login(config['smtp_username'], config['smtp_password'])
            server.send_message(msg)
            server.quit()
            
            print("✅ Daily report sent successfully!")
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Daily report error: {error_msg}")

    def _fetch_individual_inverter_data(self):
        """Fetch individual inverter power data from Chilicon API"""
        try:
            import requests
            from collections import defaultdict
            import statistics
            
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
                # Additional inverters found in Chilicon data
                1093666578: '41300712',   # New hex format inverter
                -1053817559: '3ECFFAD7',  # Negative ID format
                3241149737: 'C1300529',   # Missing inverter from Chilicon site
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
                    'avg_power': statistics.mean(powers) if powers else 0,
                    'avg_positive_power': statistics.mean(positive_powers) if positive_powers else 0,
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

# Global dashboard instance
dashboard = EnhancedDashboard()


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


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


@app.route('/admin')
def admin():
    """Admin panel for email and alert configuration - server-side rendered"""
    # Load all configs server-side
    email_config = {}
    alert_config = {}
    imessage_config = {}
    
    try:
        if os.path.exists('email_config.json'):
            with open('email_config.json', 'r') as f:
                email_config = json.load(f)
    except Exception as e:
        print(f"Error loading email config: {e}")
    
    try:
        if os.path.exists('alert_config.json'):
            with open('alert_config.json', 'r') as f:
                alert_config = json.load(f)
    except Exception as e:
        print(f"Error loading alert config: {e}")
    
    try:
        if os.path.exists('imessage_config.json'):
            with open('imessage_config.json', 'r') as f:
                imessage_config = json.load(f)
    except Exception as e:
        print(f"Error loading iMessage config: {e}")
    
    # Render template with pre-filled config values
    return render_template('admin.html', 
                         email_config=email_config, 
                         alert_config=alert_config, 
                         imessage_config=imessage_config)


@app.route('/api/admin/email-config', methods=['GET', 'POST'])
def admin_email_config():
    """Get or save email configuration"""
    config_file = 'email_config.json'
    
    if request.method == 'POST':
        try:
            config = request.json
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return jsonify(json.load(f))
            return jsonify({})
        except Exception as e:
            return jsonify({'error': str(e)})


@app.route('/api/admin/alert-config', methods=['GET', 'POST'])
def admin_alert_config():
    """Get or save alert configuration"""
    config_file = 'alert_config.json'
    
    if request.method == 'POST':
        try:
            config = request.json
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return jsonify(json.load(f))
            return jsonify({})
        except Exception as e:
            return jsonify({'error': str(e)})


@app.route('/api/admin/imessage-config', methods=['GET', 'POST'])
def admin_imessage_config():
    """Get or save iMessage configuration"""
    config_file = 'imessage_config.json'
    
    if request.method == 'POST':
        try:
            config = request.json
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    else:
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r') as f:
                    return jsonify(json.load(f))
            return jsonify({})
        except Exception as e:
            return jsonify({'error': str(e)})


@app.route('/api/admin/test-email', methods=['POST'])
def admin_test_email():
    """Send test email"""
    try:
        import smtplib
        from email.mime.text import MIMEText
        
        # Load email config
        config_file = 'email_config.json'
        if not os.path.exists(config_file):
            return jsonify({'success': False, 'error': 'Email not configured'})
            
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        # Validate required fields
        required_fields = ['email', 'smtp_server', 'smtp_port', 'smtp_username', 'smtp_password']
        for field in required_fields:
            if not config.get(field):
                return jsonify({'success': False, 'error': f'Missing {field} in configuration'})
        
        # Send test email
        msg = MIMEText('This is a test email from your Chilicon Dashboard admin panel.')
        msg['Subject'] = 'Chilicon Dashboard Test Email'
        msg['From'] = config['smtp_username']
        msg['To'] = config['email']
        
        print(f"📧 Attempting to send email via {config['smtp_server']}:{config['smtp_port']}")
        
        server = smtplib.SMTP(config['smtp_server'], int(config['smtp_port']))
        server.starttls()
        server.login(config['smtp_username'], config['smtp_password'])
        server.send_message(msg)
        server.quit()
        
        print("✅ Test email sent successfully!")
        return jsonify({'success': True})
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Email error: {error_msg}")
        return jsonify({'success': False, 'error': error_msg})


@app.route('/api/admin/test-alerts', methods=['POST'])
def admin_test_alerts():
    """Send test alerts using the intelligent alerting system with user's delivery preferences"""
    try:
        # Load alert configuration
        alert_config_file = 'alert_config.json'
        if not os.path.exists(alert_config_file):
            return jsonify({'success': False, 'error': 'Alert configuration not found'})
            
        with open(alert_config_file, 'r') as f:
            alert_config = json.load(f)
        
        # Check if alerts are enabled
        if not alert_config.get('inverter_alerts_enabled', True):
            return jsonify({'success': False, 'error': 'Inverter alerts are disabled'})
        
        # Determine delivery methods based on user preferences
        delivery_methods = []
        if alert_config.get('email_alerts_enabled', True):
            delivery_methods.append('email')
        if alert_config.get('imessage_alerts_enabled', True):
            delivery_methods.append('imessage')
        
        if not delivery_methods:
            return jsonify({'success': False, 'error': 'No alert delivery methods enabled'})
        
        # Get current system data for context
        current_data = dashboard.get_current_data()
        
        # Create test alerts using the intelligent alerting system
        test_alerts = [
            {
                'type': 'test_low_active',
                'severity': 'WARNING',
                'message': f"TEST ALERT: Only 18/25 inverters active (below threshold of {alert_config.get('min_active_inverters', 20)})",
                'active_count': 18,
                'total_count': 25,
                'timestamp': datetime.now().isoformat(),
                'timing_context': f"Test alert generated at {datetime.now().strftime('%H:%M')} (manual test)"
            },
            {
                'type': 'test_offline',
                'severity': 'WARNING', 
                'message': f"TEST ALERT: {alert_config.get('max_offline_inverters', 3) + 1} detected inverters offline: 90F00179, 90F0015C, 90F00188, 90F00170",
                'offline_count': alert_config.get('max_offline_inverters', 3) + 1,
                'offline_serials': ['90F00179', '90F0015C', '90F00188', '90F00170'],
                'timestamp': datetime.now().isoformat(),
                'timing_context': f"Test alert generated at {datetime.now().strftime('%H:%M')} (manual test)"
            }
        ]
        
        print(f"� Sending test alerts via: {', '.join(delivery_methods)}")
        
        # Use the intelligent alert manager to send alerts
        results = []
        for alert in test_alerts:
            alert_results = dashboard.alert_manager.send_inverter_alert(alert, delivery_methods)
            results.extend(alert_results)
        
        # Count successful deliveries
        successful_deliveries = []
        failed_deliveries = []
        
        for method, result in results:
            if result.get('success'):
                successful_deliveries.append(method)
            else:
                failed_deliveries.append(f"{method}: {result.get('error', 'Unknown error')}")
        
        # Prepare response
        if successful_deliveries:
            success_msg = f"Test alerts sent successfully via: {', '.join(successful_deliveries)}"
            if failed_deliveries:
                success_msg += f". Failed: {', '.join(failed_deliveries)}"
            
            print(f"✅ {success_msg}")
            return jsonify({'success': True, 'message': success_msg})
        else:
            error_msg = f"All test alerts failed: {', '.join(failed_deliveries)}"
            print(f"❌ {error_msg}")
            return jsonify({'success': False, 'error': error_msg})
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Test alerts error: {error_msg}")
        return jsonify({'success': False, 'error': error_msg})


@app.route('/api/admin/test-imessage', methods=['POST'])
def admin_test_imessage():
    """Send test iMessage"""
    try:
        import subprocess
        
        # Load iMessage config
        config_file = 'imessage_config.json'
        if not os.path.exists(config_file):
            return jsonify({'success': False, 'error': 'iMessage not configured'})
            
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        if not config.get('imessage_enabled'):
            return jsonify({'success': False, 'error': 'iMessage is disabled'})
            
        if not config.get('imessage_phone'):
            return jsonify({'success': False, 'error': 'No phone number configured'})
        
        # Get current system data for context
        current_data = dashboard.get_current_data()
        
        message = f"""🔌 Chilicon Solar Dashboard Test

This is a test message from your solar monitoring system.

Current Status:
⚡ Power: {current_data.get('power_kw', 0):.3f} kW
🔋 Active Inverters: {current_data.get('active_inverters', 0)}/{current_data.get('total_inverters', 25)}
🕐 Time: {datetime.now().strftime('%H:%M:%S')}

System is functioning normally."""
        
        phone = config['imessage_phone']
        
        # Use AppleScript to send iMessage (macOS only)
        applescript = f'''
        tell application "Messages"
            set targetService to 1st service whose service type = iMessage
            set targetBuddy to buddy "{phone}" of targetService
            send "{message}" to targetBuddy
        end tell
        '''
        
        print(f"📱 Sending test iMessage to {phone}")
        
        result = subprocess.run(['osascript', '-e', applescript], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ Test iMessage sent successfully!")
            return jsonify({'success': True})
        else:
            error_msg = result.stderr or "Failed to send iMessage"
            print(f"❌ iMessage error: {error_msg}")
            return jsonify({'success': False, 'error': error_msg})
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ iMessage error: {error_msg}")
        return jsonify({'success': False, 'error': error_msg})


@app.route('/api/admin/send-daily-report', methods=['POST'])
def admin_send_daily_report():
    """Generate and send daily status report"""
    try:
        result = dashboard._generate_and_send_daily_report()
        return jsonify(result)
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Daily report error: {error_msg}")
        return jsonify({'success': False, 'error': error_msg})


@app.route('/api/admin/sunset-info', methods=['GET'])
def admin_sunset_info():
    """Get sunset time and daily report scheduling information"""
    try:
        sunset_time = calculate_sunset_time()
        report_time = sunset_time + timedelta(minutes=dashboard.sunset_buffer_minutes)
        current_time = datetime.now()
        
        # Calculate next report time
        if current_time > report_time:
            # Already passed today's time, next is tomorrow
            tomorrow_sunset = calculate_sunset_time() + timedelta(days=1)
            next_report_time = tomorrow_sunset + timedelta(minutes=dashboard.sunset_buffer_minutes)
        else:
            next_report_time = report_time
        
        return jsonify({
            'today_sunset': sunset_time.strftime('%H:%M'),
            'today_report_time': report_time.strftime('%H:%M'),
            'next_report_time': next_report_time.strftime('%H:%M'),
            'next_report_date': next_report_time.strftime('%Y-%m-%d'),
            'buffer_minutes': dashboard.sunset_buffer_minutes,
            'current_time': current_time.strftime('%H:%M'),
            'report_sent_today': dashboard.daily_report_sent_today
        })
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/admin/reset-daily-report', methods=['POST'])
def admin_reset_daily_report():
    """Reset the daily report flag (for testing/manual correction)"""
    try:
        dashboard.daily_report_sent_today = False
        dashboard.last_daily_report_date = None
        current_date = datetime.now().date()
        return jsonify({
            'success': True, 
            'message': f'Daily report flag reset for {current_date}',
            'current_date': str(current_date),
            'report_sent_today': dashboard.daily_report_sent_today
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/admin/daily-report-status', methods=['GET'])
def admin_daily_report_status():
    """Get current daily report status for debugging"""
    try:
        current_date = datetime.now().date()
        sunset_time = calculate_sunset_time()
        report_time = sunset_time + timedelta(minutes=dashboard.sunset_buffer_minutes)
        
        return jsonify({
            'current_date': str(current_date),
            'current_time': datetime.now().strftime('%H:%M:%S'),
            'report_sent_today': dashboard.daily_report_sent_today,
            'last_daily_report_date': str(dashboard.last_daily_report_date) if dashboard.last_daily_report_date else None,
            'today_sunset': sunset_time.strftime('%H:%M'),
            'today_report_time': report_time.strftime('%H:%M'),
            'is_past_report_time': datetime.now() >= report_time
        })
    except Exception as e:
        return jsonify({'error': str(e)})


def run_dashboard(host='0.0.0.0', port=5000, debug=False):
    """Run the dashboard server"""
    print("🌐 Starting Enhanced Chilicon Dashboard...")
    print(f"📊 Dashboard: http://{host}:{port}")
    print("🔌 Monitoring service active")
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(port=5002, debug=False)
