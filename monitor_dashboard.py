#!/usr/bin/env python3
"""
Dashboard Monitor - Tracks reliability and uptime
"""

import time
import requests
import json
from datetime import datetime

def check_dashboard_status():
    """Check dashboard status and return metrics"""
    try:
        response = requests.get('http://localhost:5002/debug/status', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return {
                'online': True,
                'thread_alive': data.get('thread_alive', False),
                'cache_age_minutes': data.get('cache_age_minutes', 999),
                'iteration_count': data.get('debug_info', {}).get('iteration_count', 0),
                'last_operation': data.get('debug_info', {}).get('last_operation', 'unknown'),
                'errors': len(data.get('debug_info', {}).get('errors', [])),
                'monitoring_active': data.get('monitoring_active', False)
            }
        else:
            return {'online': False, 'error': f'HTTP {response.status_code}'}
    except Exception as e:
        return {'online': False, 'error': str(e)}

def check_data_freshness():
    """Check if data is being updated regularly"""
    try:
        response = requests.get('http://localhost:5002/api/current', timeout=5)
        if response.status_code == 200:
            data = response.json()
            last_update = data.get('last_update')
            if last_update:
                from datetime import datetime
                update_time = datetime.fromisoformat(last_update)
                age_minutes = (datetime.now() - update_time).total_seconds() / 60
                return {
                    'data_available': True,
                    'last_update': last_update,
                    'age_minutes': age_minutes,
                    'power_kw': data.get('power_kw', 0),
                    'active_inverters': data.get('active_inverters', 0)
                }
        return {'data_available': False}
    except Exception as e:
        return {'data_available': False, 'error': str(e)}

def main():
    """Monitor dashboard continuously"""
    print("🔍 Dashboard Reliability Monitor")
    print("=" * 50)
    print("Press Ctrl+C to stop monitoring")
    print()
    
    check_count = 0
    
    try:
        while True:
            check_count += 1
            current_time = datetime.now().strftime('%H:%M:%S')
            
            # Check dashboard status
            status = check_dashboard_status()
            data = check_data_freshness()
            
            # Display status
            if status.get('online'):
                thread_status = "🟢" if status.get('thread_alive') else "🔴"
                monitoring_status = "🟢" if status.get('monitoring_active') else "🔴"
                
                cache_age = status.get('cache_age_minutes', 999)
                if cache_age < 16:
                    cache_status = "🟢"
                elif cache_age < 30:
                    cache_status = "🟡"
                else:
                    cache_status = "🔴"
                
                print(f"[{current_time}] Check #{check_count}")
                print(f"  Status: 🟢 Online | Thread: {thread_status} | Monitoring: {monitoring_status} | Cache: {cache_status}")
                print(f"  Iterations: {status.get('iteration_count', 0)} | Cache Age: {cache_age:.1f}m | Errors: {status.get('errors', 0)}")
                print(f"  Operation: {status.get('last_operation', 'unknown')}")
                
                if data.get('data_available'):
                    print(f"  Power: {data.get('power_kw', 0):.3f} kW | Inverters: {data.get('active_inverters', 0)}/25")
                    print(f"  Last Update: {data.get('last_update', 'unknown')}")
                else:
                    print(f"  Data: ❌ No data available")
                
            else:
                print(f"[{current_time}] Check #{check_count}")
                print(f"  Status: 🔴 Offline - {status.get('error', 'Unknown error')}")
            
            print()
            
            # Wait 2 minutes between checks
            time.sleep(120)
            
    except KeyboardInterrupt:
        print("\n🛑 Monitoring stopped by user")
        print(f"Completed {check_count} status checks")

if __name__ == "__main__":
    main()
