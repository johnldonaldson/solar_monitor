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
        self.power_history_file = 'power_history_cache.json'
        
        # Load existing power history
        self._load_power_history()
        
        # Session management - track last website access
        self.last_website_access = None
        self.website_interval = 900  # 15 minutes in seconds
        
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
                    
                    # Individual inverters with mapped hex serials (all 25)
                    inverter_map = inverter_data.get('inverter_map', [])
                    mapped_inverters = self._map_inverter_serials(inverter_map)
                    self.current_data['individual_inverters'] = (
                        mapped_inverters
                    )
                
                power_kw = self.current_data['power_kw']
                active_inv = self.current_data['active_inverters']
                total_inv = self.current_data['total_inverters']
                print(f"✅ Website data: {power_kw:.3f} kW, "
                      f"{active_inv}/{total_inv} inverters")
                print("⏰ Next website access in 15 minutes")
                
                return True
            else:
                print("❌ Failed to get power data")
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
