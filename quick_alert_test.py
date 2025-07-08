#!/usr/bin/env python3
"""
Quick Alert Test - Force trigger an alert to test email functionality
"""

from complete_monitor_service import ChiliconCompleteMonitor
from datetime import datetime

def trigger_test_alert():
    """Trigger a test alert to verify email functionality"""
    print("🧪 CHILICON ALERT TEST")
    print("=" * 30)
    
    monitor = ChiliconCompleteMonitor()
    
    # Create test scenario data that will trigger alerts
    test_data = {
        'timestamp': datetime.now().isoformat(),
        'current_power_kw': 0.3,  # Below 0.5 threshold
        'active_inverters': 20,   # 5 inactive
        'total_inverters': 25,
        'health_status': 'Warning',
        'is_online': True
    }
    
    print("📊 Test scenario (should trigger 2 alerts):")
    print(f"   ⚡ Power: {test_data['current_power_kw']} kW (below 0.5 threshold)")
    print(f"   🔋 Inverters: {test_data['active_inverters']}/{test_data['total_inverters']} (5 inactive)")
    print(f"   🏥 Health: {test_data['health_status']}")
    
    # Check for alerts
    alerts = monitor.check_for_alerts(test_data)
    
    if alerts:
        print(f"\n🚨 {len(alerts)} alert(s) detected:")
        for i, alert in enumerate(alerts, 1):
            print(f"   {i}. {alert}")
        
        print(f"\n📧 Sending alert emails...")
        monitor.process_alerts(alerts)
        print(f"✅ Alert emails processed!")
        print(f"📬 Check your inbox at: johndona@cisco.com, johnldonaldson@hotmail.com")
    else:
        print("\n❌ No alerts triggered (this shouldn't happen with test data)")

if __name__ == "__main__":
    trigger_test_alert()
