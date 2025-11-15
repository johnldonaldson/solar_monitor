#!/usr/bin/env python3
"""
Practical Inverter Failure Monitor
Uses available data to detect potential inverter failures and health issues
"""

from legacy_chilicon_monitor import ChiliconLegacyMonitor
import json
import statistics
from datetime import datetime, timedelta

class InverterFailureMonitor:
    def __init__(self):
        self.monitor = ChiliconLegacyMonitor()
        self.username = "johnldonaldson@gmail.com"
        self.password = "P0pc0rn1"
        self.installation_url = (
            "https://cloud.chiliconpower.com/installation/"
            "384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
        )
        
        # Expected system parameters
        self.total_inverters = 25
        self.rated_power_per_inverter = 280  # Watts (typical for residential)
        self.system_rated_power = self.total_inverters * self.rated_power_per_inverter  # 7000W
        
        # Failure detection thresholds
        self.failure_thresholds = {
            'low_total_power_percent': 70,   # Alert if total < 70% of expected
            'very_low_power_percent': 40,    # Critical if total < 40% of expected
            'power_drop_percent': 30,        # Alert if power drops >30% suddenly
            'no_power_duration_minutes': 60, # Alert if no power for >60 minutes
        }
        
        # Historical data for trend analysis
        self.power_history = []
        self.history_file = 'failure_monitor_history.json'
        self.load_history()
    
    def load_history(self):
        """Load historical power data"""
        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                self.power_history = data.get('power_history', [])
                # Keep only last 7 days
                cutoff = datetime.now() - timedelta(days=7)
                self.power_history = [
                    entry for entry in self.power_history
                    if datetime.fromisoformat(entry['timestamp']) > cutoff
                ]
        except FileNotFoundError:
            self.power_history = []
    
    def save_history(self):
        """Save historical power data"""
        try:
            with open(self.history_file, 'w') as f:
                json.dump({'power_history': self.power_history}, f, indent=2)
        except Exception as e:
            print(f"⚠️ Could not save history: {e}")
    
    def get_current_data(self):
        """Get current system data"""
        if not self.monitor.login(self.username, self.password):
            return None
        
        # Get total power data using the correct legacy endpoint
        # Set proper headers like the legacy monitor
        self.monitor.session.headers.update({
            'Host': 'cloud.chiliconpower.com',
            'Referer': self.installation_url,
            'Connection': 'keep-alive'
        })
        
        today = datetime.now().strftime('%Y-%m-%d')
        ajax_url = f'https://cloud.chiliconpower.com/ajax/fetchOwnerUpdate?today={today}'
        try:
            print("🌐 Fetching AJAX data from legacy endpoint...")
            response = self.monitor.session.get(ajax_url)
            print(f"📡 Response status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Got JSON data: {type(data)}")
                
                if isinstance(data, list) and len(data) >= 3:
                    # Legacy format: [energy_array, lifetime_energy, current_power]
                    current_power_kw = data[2]  # Current power is at index 2
                    current_power_w = current_power_kw * 1000
                    lifetime_energy = data[1] if len(data) > 1 else 0
                    
                    # For today's energy, we need to extract from energy array
                    energy_array = data[0] if data[0] else []
                    todays_energy = sum(energy_array) if energy_array else 0
                    
                    print(f"⚡ Current power: {current_power_w:.1f}W")
                else:
                    print("❌ Unexpected data format")
                    return None
                
                current_data = {
                    'timestamp': datetime.now().isoformat(),
                    'power_kw': current_power_kw,
                    'power_w': current_power_w,
                    'energy_today_kwh': todays_energy,
                    'lifetime_energy_mwh': lifetime_energy / 1000
                }
                
                # Add to history
                self.power_history.append(current_data)
                self.save_history()
                
                return current_data
        except Exception as e:
            print(f"❌ Error getting current data: {e}")
            return None
    
    def analyze_system_health(self, current_data):
        """Analyze system health and detect potential failures"""
        if not current_data:
            return {'status': 'ERROR', 'alerts': ['Unable to get current data']}
        
        current_power_w = current_data['power_w']
        timestamp = current_data['timestamp']
        
        alerts = []
        warnings = []
        
        # 1. Check total power vs expected (time-aware)
        current_time = datetime.now()
        current_hour = current_time.hour
        current_month = current_time.month
        
        # More accurate daylight hours based on season
        if current_month in [12, 1, 2]:  # Winter
            daylight_start, daylight_end = 7, 17  # 7 AM to 5 PM
        elif current_month in [6, 7, 8]:  # Summer  
            daylight_start, daylight_end = 6, 19  # 6 AM to 7 PM
        else:  # Spring/Fall
            daylight_start, daylight_end = 6, 18  # 6 AM to 6 PM
            
        is_daylight = daylight_start <= current_hour <= daylight_end
        is_peak_hours = 10 <= current_hour <= 15  # Peak solar hours
        
        print(f"🕐 Time check: {current_hour}:00, Daylight: {is_daylight}, Peak: {is_peak_hours}")
        
        if is_daylight:
            # During daylight, check if power is reasonable
            if is_peak_hours:
                # Peak hours: expect higher power
                expected_min_power = self.system_rated_power * 0.2  # 20% minimum
                expected_good_power = self.system_rated_power * 0.4  # 40% is good
            else:
                # Early morning/evening: lower expectations
                expected_min_power = self.system_rated_power * 0.05  # 5% minimum
                expected_good_power = self.system_rated_power * 0.15  # 15% is reasonable
            
            if current_power_w < expected_min_power:
                alerts.append(f"Very low power during daylight: {current_power_w:.0f}W")
            elif current_power_w < expected_good_power and is_peak_hours:
                warnings.append(f"Low power during peak hours: {current_power_w:.0f}W")
        else:
            # After sunset/before sunrise - very low power is normal
            if current_power_w > 100:  # Unexpected high power at night
                warnings.append(f"Unexpected power at night: {current_power_w:.0f}W")
            # No alerts for low power during non-daylight hours
        
        # 2. Check for sudden power drops
        if len(self.power_history) >= 2:
            recent_powers = [entry['power_w'] for entry in self.power_history[-10:]]
            if len(recent_powers) >= 3:
                avg_recent = sum(recent_powers[:-1]) / len(recent_powers[:-1])
                if avg_recent > 500 and current_power_w < avg_recent * 0.7:  # 30% drop
                    alerts.append(f"Sudden power drop: {current_power_w:.0f}W (was {avg_recent:.0f}W)")
        
        # 3. Check for extended zero power during daylight ONLY
        if is_daylight:
            recent_entries = self.power_history[-12:]  # Last 12 readings
            zero_power_count = sum(1 for entry in recent_entries 
                                 if entry['power_w'] < 10)
            if zero_power_count >= 6:  # More than half are zero during daylight
                alerts.append(f"Extended no-power during daylight "
                             f"({zero_power_count}/12 readings)")
        
        # 4. Estimate individual inverter health (only during daylight)
        if is_daylight:
            inverter_health = self.estimate_inverter_health(current_power_w)
            if inverter_health['likely_failed'] > 0:
                alerts.append(f"Estimated {inverter_health['likely_failed']} "
                             f"inverters may be offline")
            if inverter_health['underperforming'] > 0:
                warnings.append(f"Estimated {inverter_health['underperforming']} "
                               f"inverters underperforming")
        else:
            # At night, create a normal health status
            inverter_health = {
                'likely_failed': 0,
                'underperforming': 0, 
                'healthy': 25,
                'estimated_avg_per_inverter': current_power_w / 25,
                'note': 'Night time - low power is normal'
            }
        
        # 5. Check trend over time
        trend_analysis = self.analyze_power_trend()
        if trend_analysis['declining']:
            warnings.append(f"Power output declining trend: {trend_analysis['description']}")
        
        # Determine overall status
        if alerts:
            status = 'CRITICAL'
        elif warnings:
            status = 'WARNING'
        else:
            status = 'HEALTHY'
        
        return {
            'status': status,
            'alerts': alerts,
            'warnings': warnings,
            'current_power_w': current_power_w,
            'inverter_estimate': inverter_health,
            'trend': trend_analysis,
            'timestamp': timestamp
        }
    
    def estimate_inverter_health(self, current_power_w):
        """Estimate individual inverter health based on total power"""
        # This is an estimation method since we don't have individual data
        
        if current_power_w < 10:  # Essentially no power
            return {
                'likely_failed': 25,
                'underperforming': 0,
                'healthy': 0,
                'estimated_avg_per_inverter': 0
            }
        
        # Estimate average power per active inverter
        # Assume a reasonable distribution and estimate how many are working
        estimated_avg_per_inverter = current_power_w / self.total_inverters
        
        # Based on typical performance, estimate health
        if estimated_avg_per_inverter < 20:  # Very low
            likely_failed = max(0, 25 - int(current_power_w / 50))  # Assume 50W minimum per working inverter
            healthy = 25 - likely_failed
            underperforming = 0
        elif estimated_avg_per_inverter < 80:  # Below normal
            likely_failed = 0
            underperforming = max(0, int((80 * 25 - current_power_w) / 80))
            healthy = 25 - underperforming
        else:  # Good performance
            likely_failed = 0
            underperforming = 0
            healthy = 25
        
        return {
            'likely_failed': likely_failed,
            'underperforming': underperforming,
            'healthy': healthy,
            'estimated_avg_per_inverter': estimated_avg_per_inverter
        }
    
    def analyze_power_trend(self):
        """Analyze power trend over recent days"""
        if len(self.power_history) < 10:
            return {'declining': False, 'description': 'Insufficient data'}
        
        # Group by day and find daily peaks (rough solar production estimate)
        daily_peaks = {}
        for entry in self.power_history:
            date = entry['timestamp'][:10]  # YYYY-MM-DD
            power = entry['power_w']
            if date not in daily_peaks or power > daily_peaks[date]:
                daily_peaks[date] = power
        
        if len(daily_peaks) < 3:
            return {'declining': False, 'description': 'Need more days of data'}
        
        # Check if recent days are significantly lower than earlier days
        sorted_days = sorted(daily_peaks.items())
        recent_days = sorted_days[-3:]  # Last 3 days
        earlier_days = sorted_days[:-3]  # Earlier days
        
        if not earlier_days:
            return {'declining': False, 'description': 'Not enough historical data'}
        
        recent_avg = sum(power for _, power in recent_days) / len(recent_days)
        earlier_avg = sum(power for _, power in earlier_days) / len(earlier_days)
        
        if recent_avg < earlier_avg * 0.8:  # 20% decline
            decline_percent = (1 - recent_avg / earlier_avg) * 100
            return {
                'declining': True,
                'description': f'{decline_percent:.1f}% decline in recent days'
            }
        
        return {'declining': False, 'description': 'Stable performance'}
    
    def run_monitoring_cycle(self):
        """Run a complete monitoring cycle"""
        print("🔍 INVERTER FAILURE MONITORING CYCLE")
        print("=" * 50)
        
        # Get current data
        print("📊 Getting current system data...")
        current_data = self.get_current_data()
        
        if not current_data:
            print("❌ Failed to get current data")
            return None
        
        # Analyze health
        print("🏥 Analyzing system health...")
        health_analysis = self.analyze_system_health(current_data)
        
        # Display results
        self.display_health_report(health_analysis)
        
        return health_analysis
    
    def display_health_report(self, health_analysis):
        """Display health analysis results"""
        status = health_analysis['status']
        
        # Status header
        if status == 'HEALTHY':
            print("\n✅ SYSTEM STATUS: HEALTHY")
        elif status == 'WARNING':
            print("\n⚠️ SYSTEM STATUS: WARNING")
        else:
            print("\n🚨 SYSTEM STATUS: CRITICAL")
        
        print(f"📊 Current Power: {health_analysis['current_power_w']:.1f}W")
        
        # Inverter estimates
        inv_est = health_analysis['inverter_estimate']
        print(f"🔧 Estimated Inverter Status:")
        print(f"   Healthy: {inv_est['healthy']}/25")
        print(f"   Underperforming: {inv_est['underperforming']}/25")
        print(f"   Likely Failed: {inv_est['likely_failed']}/25")
        print(f"   Avg per inverter: {inv_est['estimated_avg_per_inverter']:.1f}W")
        
        # Alerts and warnings
        if health_analysis['alerts']:
            print("\n🚨 CRITICAL ALERTS:")
            for alert in health_analysis['alerts']:
                print(f"   • {alert}")
        
        if health_analysis['warnings']:
            print("\n⚠️ WARNINGS:")
            for warning in health_analysis['warnings']:
                print(f"   • {warning}")
        
        # Trend
        trend = health_analysis['trend']
        if trend['declining']:
            print(f"\n📉 TREND: {trend['description']}")
        else:
            print(f"\n📈 TREND: {trend['description']}")
        
        print(f"\n⏰ Analysis Time: {health_analysis['timestamp']}")

def main():
    """Run the failure monitoring system"""
    monitor = InverterFailureMonitor()
    health_report = monitor.run_monitoring_cycle()
    
    # Save report
    if health_report:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"health_report_{timestamp}.json"
        with open(filename, 'w') as f:
            json.dump(health_report, f, indent=2)
        print(f"\n💾 Health report saved to: {filename}")

if __name__ == "__main__":
    main()
