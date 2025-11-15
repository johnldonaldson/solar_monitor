#!/usr/bin/env python3
"""
Chilicon Power Monitoring System - Main Launcher
Choose which component to run
"""

import sys
import subprocess
from pathlib import Path


def show_menu():
    """Display the main menu"""
    print("\n🔌 CHILICON POWER MONITORING SYSTEM")
    print("=" * 50)
    print("\nSelect a component to run:")
    print("\n1. 📊 Basic Monitor - Test current power reading")
    print("2. 🔄 Full Monitoring Service - Continuous monitoring + alerts")
    print("3. 🌐 Web Dashboard - Real-time web interface")
    print("4. 📧 Configure Alerts - Setup email notifications")
    print("5. 🔧 Enhanced Inverter Mapping - Detailed inverter analysis")
    print("6. 🛠️  System Setup - Install requirements and configure")
    print("7. 📄 View Latest Data - Show recent readings")
    print("8. 📋 System Status - Check service health")
    print("\n0. ❌ Exit")
    print("\n" + "=" * 50)


def run_component(choice):
    """Run the selected component"""
    scripts = {
        '1': 'legacy_chilicon_monitor.py',
        '2': 'complete_monitor_service.py',
        '3': 'enhanced_dashboard.py',
        '4': 'alert_config.py',
        '5': 'enhanced_inverter_mapper.py',
        '6': 'setup_chilicon_monitoring.py'
    }
    
    if choice in scripts:
        script = scripts[choice]
        if Path(script).exists():
            print(f"\n🚀 Starting {script}...")
            print("=" * 50)
            try:
                subprocess.run([sys.executable, script], check=True)
            except subprocess.CalledProcessError as e:
                print(f"❌ Error running {script}: {e}")
            except KeyboardInterrupt:
                print(f"\n⏹️  Stopped {script}")
        else:
            print(f"❌ Script not found: {script}")
    
    elif choice == '7':
        show_latest_data()
    
    elif choice == '8':
        show_system_status()
    
    elif choice == '0':
        print("\n👋 Goodbye!")
        return False
    
    else:
        print("❌ Invalid choice. Please try again.")
    
    return True


def show_latest_data():
    """Show the latest monitoring data"""
    data_file = Path("monitoring_data/latest.json")
    
    if data_file.exists():
        import json
        try:
            with open(data_file, 'r') as f:
                data = json.load(f)
            
            print("\n📊 LATEST SYSTEM DATA")
            print("=" * 30)
            print(f"🕒 Timestamp: {data.get('timestamp', 'Unknown')}")
            print(f"⚡ Power: {data.get('current_power_kw', 0):.3f} kW")
            print(f"📈 Today's Energy: {data.get('todays_energy_kwh', 0):.2f} kWh")
            print(f"🔋 Active Inverters: {data.get('active_inverters', 0)}/{data.get('total_inverters', 25)}")
            print(f"🏥 Health: {data.get('health_status', 'Unknown')}")
            print(f"🌐 Online: {'✅ Yes' if data.get('is_online') else '❌ No'}")
            
        except Exception as e:
            print(f"❌ Error reading data file: {e}")
    else:
        print("❌ No data file found. Run the monitoring service first.")


def show_system_status():
    """Show system status and health"""
    print("\n🔍 SYSTEM STATUS")
    print("=" * 30)
    
    # Check if files exist
    files_to_check = [
        ('legacy_chilicon_monitor.py', 'Basic Monitor'),
        ('complete_monitor_service.py', 'Monitoring Service'),
        ('enhanced_dashboard.py', 'Web Dashboard'),
        ('alert_config.py', 'Alert Configuration'),
        ('monitor_config.json', 'Configuration File'),
        ('templates/dashboard.html', 'Dashboard Template')
    ]
    
    for file_path, description in files_to_check:
        status = "✅" if Path(file_path).exists() else "❌"
        print(f"{status} {description}")
    
    # Check data directory
    data_dir = Path("monitoring_data")
    if data_dir.exists():
        files_count = len(list(data_dir.glob("*.json")))
        print(f"✅ Data Directory ({files_count} files)")
    else:
        print("❌ Data Directory")
    
    # Check if monitoring is running (look for recent data)
    latest_data = Path("monitoring_data/latest.json")
    if latest_data.exists():
        import json
        from datetime import datetime, timedelta
        try:
            with open(latest_data, 'r') as f:
                data = json.load(f)
            
            timestamp_str = data.get('timestamp', '')
            if timestamp_str:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                age = datetime.now() - timestamp.replace(tzinfo=None)
                
                if age < timedelta(minutes=10):
                    print("✅ Monitoring Active (recent data)")
                else:
                    print(f"⚠️  Monitoring Inactive (last update: {age} ago)")
            else:
                print("❌ No timestamp in data")
                
        except Exception as e:
            print(f"❌ Error checking monitoring status: {e}")
    else:
        print("❌ No monitoring data found")


def main():
    """Main function"""
    try:
        while True:
            show_menu()
            choice = input("\nEnter your choice (0-8): ").strip()
            
            if not run_component(choice):
                break
            
            if choice not in ['0', '6']:  # Don't pause after exit or setup
                input("\n⏸️  Press Enter to continue...")
    
    except KeyboardInterrupt:
        print("\n\n👋 Goodbye!")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()
