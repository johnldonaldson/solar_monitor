#!/usr/bin/env python3
"""
Enhanced Chilicon Power Dashboard
Real-time dashboard with direct data fetching
"""

import json
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request
from legacy_chilicon_monitor import ChiliconLegacyMonitor

app = Flask(__name__)


class EnhancedDashboard:
    def __init__(self):
        self.monitor = ChiliconLegacyMonitor()
        self.username = "johnldonaldson@gmail.com"
        self.password = "P0pc0rn1"
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
        
        # Session management
        self.last_login_time = None
        self.login_interval = 900  # 15 minutes in seconds
        self.is_logged_in = False
        
        # Start background data updating
        self.monitoring = True
        self.update_thread = threading.Thread(target=self.background_update)
        self.update_thread.daemon = True
        self.update_thread.start()
    
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
    
    def _should_update(self):
        """Check if enough time has passed since last update"""
        if not self.current_data.get('last_update'):
            return True
        
        try:
            last_update_str = self.current_data['last_update']
            last_update = datetime.fromisoformat(last_update_str)
            now = datetime.now()
            time_diff = (now - last_update).total_seconds()
            return time_diff >= 120  # 2 minutes
        except Exception:
            return True

    def _should_login(self):
        """Check if we need to login (first time or after 15 minutes)"""
        if not self.last_login_time:
            return True
        
        try:
            now = datetime.now()
            time_diff = (now - self.last_login_time).total_seconds()
            return time_diff >= self.login_interval
        except Exception:
            return True

    def _perform_login(self):
        """Perform login and update session status"""
        try:
            # Create a fresh monitor instance for clean session
            self.monitor = ChiliconLegacyMonitor()
            success = self.monitor.login(self.username, self.password)
            
            if success:
                self.last_login_time = datetime.now()
                self.is_logged_in = True
                print(f"🔐 Login successful at {self.last_login_time.strftime('%H:%M:%S')}")
                print(f"⏰ Next login scheduled for {(self.last_login_time + timedelta(seconds=self.login_interval)).strftime('%H:%M:%S')}")
                return True
            else:
                self.is_logged_in = False
                print("❌ Login failed")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            self.is_logged_in = False
            return False

    def fetch_fresh_data(self):
        """Fetch fresh data from Chilicon system using existing session"""
        try:
            print("🔄 Fetching data with existing session...")
            
            # Don't login here - session management handles that
            if not self.is_logged_in:
                print("❌ No valid session available")
                self.current_data['is_online'] = False
                return

            # Get power data using existing session
            power_data = self.monitor.get_power_data(self.installation_url)
            
            if power_data:
                # Update main metrics
                self.current_data.update({
                    'last_update': datetime.now().isoformat(),
                    'power_kw': power_data.get('current_power_kw', 0),
                    'energy_today_kwh': power_data.get('todays_energy_raw', 0),
                    'lifetime_energy_mwh': (
                        power_data.get('lifetime_energy_raw', 0) / 1000
                    ),
                    'is_online': True
                })
                
                # Add to power history
                current_time = datetime.now()
                self.power_history.append({
                    'time': current_time.strftime('%H:%M'),
                    'power': self.current_data['power_kw'],
                    'timestamp': current_time.isoformat()
                })
                
                # Keep only last 24 hours
                cutoff_time = current_time - timedelta(hours=24)
                self.power_history = [
                    entry for entry in self.power_history
                    if datetime.fromisoformat(entry['timestamp']) > cutoff_time
                ]
                
                # Get inverter data
                inverter_data = self.monitor.get_individual_inverter_data(
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
                    health = self.monitor.check_inverter_health(inverter_data)
                    if health:
                        self.current_data['health_status'] = (
                            health.get('health_status', 'Unknown')
                        )
                        self.current_data['alerts'] = health.get('issues', [])
                    
                    # Individual inverters (first 10 for display)
                    inverter_map = inverter_data.get('inverter_map', [])
                    self.current_data['individual_inverters'] = (
                        inverter_map[:10]
                    )
                
                power_kw = self.current_data['power_kw']
                active_inv = self.current_data['active_inverters']
                total_inv = self.current_data['total_inverters']
                print(f"✅ Data updated: {power_kw:.3f} kW, "
                      f"{active_inv}/{total_inv} inverters")
                
            else:
                # Data fetch failed - might be session expired
                print("❌ Failed to get power data - session may have expired")
                self.current_data['is_online'] = False
                self.is_logged_in = False  # Force re-login on next cycle
                
        except Exception as e:
            print(f"❌ Data fetch error: {e}")
            self.current_data['is_online'] = False
            # Don't force re-login on every error, just mark as offline
    
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
        if not self.current_data.get('last_update'):
            return 0
        
        try:
            last_update_str = self.current_data['last_update']
            last_update = datetime.fromisoformat(last_update_str)
            now = datetime.now()
            time_since = (now - last_update).total_seconds()
            time_until = max(0, 900 - time_since)  # 15 minutes
            return round(time_until / 60, 1)  # Return in minutes
        except Exception:
            return 0
    
    def _fetch_from_website(self):
        """Actually fetch data from the Chilicon website"""
        try:
            print("🌐 Contacting Chilicon website...")
            
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
                
                # Add to power history
                current_time = datetime.now()
                self.power_history.append({
                    'time': current_time.strftime('%H:%M'),
                    'power': self.current_data['power_kw'],
                    'timestamp': current_time.isoformat()
                })
                
                # Keep only last 24 hours
                cutoff_time = current_time - timedelta(hours=24)
                self.power_history = [
                    entry for entry in self.power_history
                    if datetime.fromisoformat(entry['timestamp']) > cutoff_time
                ]
                
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
                    
                    # Individual inverters (first 10 for display)
                    inverter_map = inverter_data.get('inverter_map', [])
                    self.current_data['individual_inverters'] = (
                        inverter_map[:10]
                    )
                
                power_kw = self.current_data['power_kw']
                active_inv = self.current_data['active_inverters']
                total_inv = self.current_data['total_inverters']
                print(f"✅ Website data: {power_kw:.3f} kW, "
                      f"{active_inv}/{total_inv} inverters")
                print(f"⏰ Next fetch scheduled in 15 minutes")
                
                return True
            else:
                print("❌ Failed to get power data")
                return False
                
        except Exception as e:
            print(f"❌ Website fetch error: {e}")
            return False

    # ...existing code...
    


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


def run_dashboard(host='0.0.0.0', port=5000, debug=False):
    """Run the dashboard server"""
    print("🌐 Starting Enhanced Chilicon Dashboard...")
    print(f"📊 Dashboard: http://{host}:{port}")
    print("🔌 Monitoring service active")
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(port=5001, debug=False)
