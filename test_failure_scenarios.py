#!/usr/bin/env python3
"""
Test the failure monitor with simulated scenarios
"""

from inverter_failure_monitor import InverterFailureMonitor
from datetime import datetime
import json

def test_failure_scenarios():
    """Test different failure scenarios"""
    
    monitor = InverterFailureMonitor()
    
    # Test scenarios with simulated data
    test_scenarios = [
        {
            'name': 'Normal Evening (Current)',
            'power_w': 35.3,
            'time_hour': 20,  # 8 PM
            'expected_status': 'HEALTHY'
        },
        {
            'name': 'Normal Peak Hours',
            'power_w': 4500,  # Good production
            'time_hour': 12,  # Noon
            'expected_status': 'HEALTHY'
        },
        {
            'name': 'System Failure During Peak',
            'power_w': 50,    # Very low during peak
            'time_hour': 12,  # Noon
            'expected_status': 'CRITICAL'
        },
        {
            'name': 'Partial Failure Morning',
            'power_w': 800,   # Low but some production
            'time_hour': 8,   # 8 AM
            'expected_status': 'WARNING'
        },
        {
            'name': 'Normal Night',
            'power_w': 5,     # Very low at night
            'time_hour': 23,  # 11 PM
            'expected_status': 'HEALTHY'
        }
    ]
    
    print("🧪 FAILURE MONITOR TEST SCENARIOS")
    print("=" * 60)
    
    for scenario in test_scenarios:
        print(f"\n🔬 Testing: {scenario['name']}")
        print(f"   Power: {scenario['power_w']}W at {scenario['time_hour']}:00")
        
        # Create simulated current data
        simulated_data = {
            'timestamp': datetime.now().replace(hour=scenario['time_hour']).isoformat(),
            'power_kw': scenario['power_w'] / 1000,
            'power_w': scenario['power_w'],
            'energy_today_kwh': 20,
            'lifetime_energy_mwh': 100
        }
        
        # Temporarily modify the analyze function to use our time
        original_now = datetime.now
        test_time = datetime.now().replace(hour=scenario['time_hour'])
        
        # Mock datetime.now() for this test
        import builtins
        original_datetime = builtins.__dict__.get('datetime', datetime)
        
        class MockDateTime:
            @staticmethod
            def now():
                return test_time
            @staticmethod  
            def fromisoformat(date_string):
                return datetime.fromisoformat(date_string)
        
        # Temporarily replace datetime in the monitor
        import sys
        sys.modules[monitor.__module__].datetime = MockDateTime
        
        try:
            # Run analysis with simulated data
            analysis = monitor.analyze_system_health(simulated_data)
            
            status = analysis['status']
            print(f"   Result: {status}")
            print(f"   Expected: {scenario['expected_status']}")
            
            if status == scenario['expected_status']:
                print("   ✅ PASS")
            else:
                print("   ❌ FAIL")
                
            if analysis['alerts']:
                print(f"   Alerts: {analysis['alerts']}")
            if analysis['warnings']:
                print(f"   Warnings: {analysis['warnings']}")
                
        finally:
            # Restore original datetime
            sys.modules[monitor.__module__].datetime = datetime
    
    print(f"\n" + "=" * 60)
    print("✅ Test complete! The failure monitor should now correctly")
    print("   distinguish between normal nighttime operation and actual failures.")

if __name__ == "__main__":
    test_failure_scenarios()
