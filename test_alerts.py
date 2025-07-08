#!/usr/bin/env python3
"""
Chilicon Alert Testing Script
Test various alert conditions to verify the alerting system
"""

import json
import time
from datetime import datetime
from complete_monitor_service import ChiliconCompleteMonitor


class AlertTester:
    def __init__(self):
        self.monitor = ChiliconCompleteMonitor()
        self.load_alert_config()
    
    def load_alert_config(self):
        """Load alert configuration"""
        try:
            with open('alert_config.json', 'r') as f:
                self.alert_config = json.load(f)
            print("✅ Alert configuration loaded")
        except FileNotFoundError:
            print("❌ Alert configuration not found. Run alert_config.py first.")
            self.alert_config = None
    
    def create_test_scenarios(self):
        """Create test data scenarios for different alert conditions"""
        scenarios = {
            'normal_operation': {
                'name': '🟢 Normal Operation',
                'current_power_kw': 4.5,
                'active_inverters': 25,
                'total_inverters': 25,
                'health_status': 'Excellent',
                'is_online': True
            },
            'low_power': {
                'name': '🟡 Low Power Alert',
                'current_power_kw': 0.3,  # Below 0.5 kW threshold
                'active_inverters': 20,
                'total_inverters': 25,
                'health_status': 'Warning',
                'is_online': True
            },
            'inverter_failures': {
                'name': '🔴 Multiple Inverter Failures',
                'current_power_kw': 3.2,
                'active_inverters': 18,  # 7 inactive (above 5 threshold)
                'total_inverters': 25,
                'health_status': 'Critical',
                'is_online': True
            },
            'system_offline': {
                'name': '❌ System Offline',
                'current_power_kw': 0,
                'active_inverters': 0,
                'total_inverters': 25,
                'health_status': 'Unknown',
                'is_online': False
            },
            'critical_combined': {
                'name': '💥 Critical - Multiple Issues',
                'current_power_kw': 0.2,
                'active_inverters': 15,  # 10 inactive
                'total_inverters': 25,
                'health_status': 'Critical',
                'is_online': True
            }
        }
        
        return scenarios
    
    def test_scenario(self, scenario_name, scenario_data):
        """Test a specific alert scenario"""
        print(f"\n{'='*60}")
        print(f"🧪 TESTING: {scenario_data['name']}")
        print(f"{'='*60}")
        
        # Create test system data
        test_data = {
            'timestamp': datetime.now().isoformat(),
            'current_power_kw': scenario_data['current_power_kw'],
            'active_inverters': scenario_data['active_inverters'],
            'total_inverters': scenario_data['total_inverters'],
            'health_status': scenario_data['health_status'],
            'is_online': scenario_data['is_online']
        }
        
        print(f"📊 Test Data:")
        print(f"   ⚡ Power: {test_data['current_power_kw']} kW")
        print(f"   🔋 Inverters: {test_data['active_inverters']}/{test_data['total_inverters']}")
        print(f"   🏥 Health: {test_data['health_status']}")
        print(f"   🌐 Online: {test_data['is_online']}")
        
        # Check for alerts using the monitoring service logic
        alerts = self.monitor.check_for_alerts(test_data)
        
        print(f"\n🚨 Alert Results:")
        if alerts:
            print(f"   📢 {len(alerts)} alert(s) detected:")
            for i, alert in enumerate(alerts, 1):
                print(f"   {i}. {alert}")
            
            # Test alert processing (but don't actually send emails for all tests)
            if scenario_name in ['critical_combined', 'system_offline']:
                print(f"\n📧 Processing alerts (will send actual emails)...")
                self.monitor.process_alerts(alerts)
            else:
                print(f"\n📧 Would send alerts (skipping to avoid spam)")
                
        else:
            print("   ✅ No alerts - System operating normally")
        
        return alerts
    
    def run_all_tests(self):
        """Run all alert test scenarios"""
        print("🔌 CHILICON ALERT SYSTEM TEST")
        print("=" * 50)
        print(f"🕒 Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not self.alert_config:
            print("❌ Cannot test alerts without configuration")
            return
        
        print(f"\n📧 Email alerts configured:")
        print(f"   Server: {self.alert_config['smtp_server']}")
        print(f"   Recipients: {', '.join(self.alert_config['alert_recipients'])}")
        print(f"   Enabled: {self.alert_config['email_enabled']}")
        
        scenarios = self.create_test_scenarios()
        results = {}
        
        # Test each scenario
        for scenario_name, scenario_data in scenarios.items():
            alerts = self.test_scenario(scenario_name, scenario_data)
            results[scenario_name] = {
                'alerts_count': len(alerts),
                'alerts': alerts
            }
            
            # Wait between tests
            if scenario_name != list(scenarios.keys())[-1]:  # Not last scenario
                print(f"\n⏳ Waiting 5 seconds before next test...")
                time.sleep(5)
        
        # Summary
        print(f"\n{'='*60}")
        print("📋 TEST SUMMARY")
        print(f"{'='*60}")
        
        total_alerts = 0
        for scenario_name, result in results.items():
            scenario_data = scenarios[scenario_name]
            alert_count = result['alerts_count']
            total_alerts += alert_count
            
            status = "🚨" if alert_count > 0 else "✅"
            print(f"{status} {scenario_data['name']}: {alert_count} alerts")
        
        print(f"\n📊 Total scenarios tested: {len(scenarios)}")
        print(f"🚨 Total alerts generated: {total_alerts}")
        print(f"📧 Email system: {'✅ Active' if self.alert_config['email_enabled'] else '❌ Disabled'}")
        
        return results


def test_real_time_alerts():
    """Test alerts with real system data"""
    print("\n" + "="*60)
    print("🔄 REAL-TIME ALERT TEST")
    print("="*60)
    
    monitor = ChiliconCompleteMonitor()
    
    print("🔌 Getting real system data...")
    real_data = monitor.get_system_data()
    
    if real_data and real_data.get('is_online'):
        print(f"✅ Real system data retrieved:")
        print(f"   ⚡ Power: {real_data.get('current_power_kw', 0):.3f} kW")
        print(f"   🔋 Inverters: {real_data.get('active_inverters', 0)}/{real_data.get('total_inverters', 25)}")
        print(f"   🏥 Health: {real_data.get('health_status', 'Unknown')}")
        
        # Check for real alerts
        alerts = monitor.check_for_alerts(real_data)
        
        if alerts:
            print(f"\n🚨 REAL ALERTS DETECTED:")
            for i, alert in enumerate(alerts, 1):
                print(f"   {i}. {alert}")
            
            # Process real alerts
            monitor.process_alerts(alerts)
            print(f"📧 Real alerts processed and sent!")
        else:
            print(f"\n✅ No real alerts - System is healthy")
    else:
        print(f"❌ Could not get real system data")


def send_test_email():
    """Send a test email directly"""
    print("📧 SENDING TEST EMAIL")
    print("=" * 30)
    
    tester = AlertTester()
    
    if not tester.alert_config:
        print("❌ No alert configuration found")
        print("   Run: python alert_config.py to set up email alerts")
        return False
    
    if not tester.alert_config.get('email_enabled'):
        print("❌ Email alerts are disabled in configuration")
        print("   Run: python alert_config.py to enable them")
        return False
    
    try:
        print("📧 Sending test email...")
        # Create a simple test alert with timestamp
        test_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        test_alerts = [f"🧪 TEST EMAIL from Chilicon monitoring system at {test_time}"]
        
        # Use the monitor's process_alerts method
        result = tester.monitor.process_alerts(test_alerts)
        
        print("✅ Test email sent successfully! Check your inbox.")
        print(f"   📬 Sent to: {', '.join(tester.alert_config['alert_recipients'])}")
        return True
        
    except Exception as e:
        print(f"❌ Error sending test email: {str(e)}")
        return False


def main():
    """Main testing function"""
    import sys
    
    # Check if we have command line arguments for non-interactive mode
    if len(sys.argv) > 1:
        option = sys.argv[1].lower()
        if option in ["test-email", "email"]:
            send_test_email()
            return
        elif option in ["all-tests", "all", "test-all"]:
            tester = AlertTester()
            tester.run_all_tests()
            return
        elif option in ["real-time", "realtime", "real"]:
            test_real_time_alerts()
            return
        elif option in ["help", "-h", "--help", "-help"]:
            print("🧪 CHILICON ALERT TESTING SCRIPT")
            print("=" * 40)
            print("Command-line usage:")
            print("  python test_alerts.py test-email    # Send test email")
            print("  python test_alerts.py all-tests     # Run all test scenarios")
            print("  python test_alerts.py real-time     # Test with real-time data")
            print("  python test_alerts.py help          # Show this help")
            print("  python test_alerts.py               # Interactive menu")
            print("\nAvailable aliases:")
            print("  email, test-email    → Send test email")
            print("  all, test-all        → Run all tests")
            print("  real, realtime       → Real-time test")
            return
        else:
            print(f"❌ Unknown option: {option}")
            print("   Use 'python test_alerts.py help' for available options")
            return
    
    tester = AlertTester()
    
    print("🧪 CHILICON ALERT TESTING MENU")
    print("=" * 40)
    print("1. 🎯 Test All Alert Scenarios")
    print("2. 🔄 Test with Real-Time Data")
    print("3. 📧 Send Test Email")
    print("4. ⚙️  Show Alert Configuration")
    print("5. ❌ Exit")
    
    while True:
        try:
            choice = input("\nSelect option (1-5): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 Alert testing completed!")
            break
        
        if choice == '1':
            tester.run_all_tests()
        
        elif choice == '2':
            test_real_time_alerts()
        
        elif choice == '3':
            send_test_email()
        
        elif choice == '4':
            if tester.alert_config:
                print("\n⚙️  ALERT CONFIGURATION:")
                print(f"   📧 Email: {tester.alert_config['email_address']}")
                print(f"   📬 Recipients: {', '.join(tester.alert_config['alert_recipients'])}")
                print(f"   ⚡ Min Power: {tester.alert_config['min_power_daylight']} kW")
                print(f"   🔋 Max Inactive: {tester.alert_config['max_inactive_inverters']}")
                print(f"   🕒 Cooldown: {tester.alert_config['alert_cooldown_minutes']} min")
                print(f"   ✅ Enabled: {tester.alert_config['email_enabled']}")
            else:
                print("❌ No alert configuration found")
        
        elif choice == '5':
            print("👋 Alert testing completed!")
            break
        
        else:
            print("❌ Invalid choice. Please try again.")


if __name__ == "__main__":
    main()
