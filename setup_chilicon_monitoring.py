#!/usr/bin/env python3
"""
Chilicon Power Monitoring System - Setup and Installation
"""

import os
import sys
import subprocess
import json
from pathlib import Path

def check_python_version():
    """Check if Python version is compatible"""
    if sys.version_info < (3, 7):
        print("❌ Python 3.7 or higher is required")
        print(f"Current version: {sys.version}")
        return False
    print(f"✅ Python {sys.version.split()[0]} - Compatible")
    return True

def install_requirements():
    """Install required Python packages"""
    requirements = [
        'requests>=2.25.0',
        'flask>=2.0.0',
        'beautifulsoup4>=4.9.0'
    ]
    
    print("📦 Installing required packages...")
    for package in requirements:
        try:
            subprocess.check_call([
                sys.executable, '-m', 'pip', 'install', package
            ])
            print(f"✅ Installed: {package}")
        except subprocess.CalledProcessError:
            print(f"❌ Failed to install: {package}")
            return False
    
    return True

def create_config_file():
    """Create initial configuration"""
    config = {
        "credentials": {
            "username": "johnldonaldson@gmail.com",
            "password": "P0pc0rn1"
        },
        "installation_url": (
            "https://cloud.chiliconpower.com/installation/"
            "384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
        ),
        "monitoring": {
            "check_interval_minutes": 5,
            "save_interval_minutes": 15,
            "daily_summary_hour": 20
        },
        "alerts": {
            "min_power_threshold_kw": 0.5,
            "max_inactive_inverters": 3,
            "email_enabled": False,
            "email_address": "johnldonaldson@gmail.com",
            "alert_cooldown_minutes": 60
        },
        "dashboard": {
            "host": "0.0.0.0",
            "port": 5000,
            "debug": False
        }
    }
    
    config_file = "monitor_config.json"
    if not Path(config_file).exists():
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"✅ Created configuration file: {config_file}")
    else:
        print(f"ℹ️  Configuration file already exists: {config_file}")
    
    return config

def create_directories():
    """Create necessary directories"""
    directories = [
        "monitoring_data",
        "logs",
        "templates"
    ]
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Created directory: {directory}")

def display_usage_instructions():
    """Display usage instructions"""
    print("\n" + "="*60)
    print("🔌 CHILICON POWER MONITORING SYSTEM")
    print("="*60)
    print("\n📋 AVAILABLE COMPONENTS:")
    print("\n1. 📊 Legacy Monitor (legacy_chilicon_monitor.py)")
    print("   - Basic power and inverter monitoring")
    print("   - Run: python legacy_chilicon_monitor.py")
    
    print("\n2. 🔄 Complete Monitoring Service (complete_monitor_service.py)")
    print("   - Continuous monitoring with alerts")
    print("   - Data logging and daily summaries")
    print("   - Run: python complete_monitor_service.py")
    
    print("\n3. 🌐 Web Dashboard (enhanced_dashboard.py)")
    print("   - Real-time web interface")
    print("   - Charts and system status")
    print("   - Run: python enhanced_dashboard.py")
    print("   - Access: http://solar_monitor:5002")
    
    print("\n4. 📧 Alert Configuration (alert_config.py)")
    print("   - Configure email alerts")
    print("   - Test email functionality")
    print("   - Run: python alert_config.py")
    
    print("\n5. 🔧 Enhanced Inverter Mapping (enhanced_inverter_mapper.py)")
    print("   - Improved serial number to power mapping")
    print("   - Run: python enhanced_inverter_mapper.py")
    
    print("\n📁 DATA STORAGE:")
    print("   - monitoring_data/: Daily readings and summaries")
    print("   - logs/: System logs")
    print("   - *.json: Configuration and output files")
    
    print("\n🚀 QUICK START:")
    print("   1. Test basic monitoring: python legacy_chilicon_monitor.py")
    print("   2. Configure alerts: python alert_config.py")
    print("   3. Start dashboard: python enhanced_dashboard.py")
    print("   4. Start monitoring service: python complete_monitor_service.py")
    
    print("\n⚙️  CONFIGURATION:")
    print("   - Edit monitor_config.json for settings")
    print("   - Edit alert_config.json for email alerts")
    
    print("\n📊 OUTPUTS:")
    print("   - Real-time power: Displayed on dashboard")
    print("   - Daily summaries: monitoring_data/summary_YYYYMMDD.json")
    print("   - System logs: chilicon_complete_monitor.log")
    
    print("\n" + "="*60)

def main():
    """Main setup function"""
    print("🔌 Chilicon Power Monitoring System Setup")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        return False
    
    # Install requirements
    if not install_requirements():
        print("❌ Failed to install requirements")
        return False
    
    # Create directories
    create_directories()
    
    # Create config
    create_config_file()
    
    print("\n✅ Setup completed successfully!")
    
    # Display usage instructions
    display_usage_instructions()
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)
