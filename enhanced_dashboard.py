#!/usr/bin/env python3
"""
Enhanced Chilicon Power Dashboard
Real-time dashboard with direct data fetching
"""

import os
import json
import re
import time
import statistics
import threading
import traceback
import smtplib
import copy
import requests
from pathlib import Path
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from flask import Flask, render_template, jsonify, request
from legacy_chilicon_monitor import ChiliconLegacyMonitor
from inverter_alert_manager import InverterAlertManager, calculate_sunset_time
from intelligent_inverter_timing import create_timing_intelligence_integration

app = Flask(__name__)

# --- Configuration Constants ---
CHILICON_USERNAME = "johnldonaldson@gmail.com"
CHILICON_PASSWORD = "P0pc0rn1"
INSTALLATION_ID = "384b18e73cb8a7c9364ecbb2b220f774fc815d7aa4126ee574d64f8152ab11c7"
INSTALLATION_URL = f"https://cloud.chiliconpower.com/installation/{INSTALLATION_ID}"
DEFAULT_TOTAL_INVERTERS = 25
UPDATE_INTERVAL_SECONDS = 900    # 15 minutes
SUNSET_BUFFER_MINUTES = 30
POWER_THRESHOLD_KW = 0.01        # ~10 W minimum active power
LOW_POWER_THRESHOLD_KW = 0.1     # 100 W threshold for meaningful generation
DEFAULT_HISTORY_HOURS = 24



class EnhancedDashboard:
    def __init__(self):
        self.monitor = ChiliconLegacyMonitor()
        self.username = CHILICON_USERNAME
        self.password = CHILICON_PASSWORD
        self.installation_url = INSTALLATION_URL
        
        # Live data storage
        self.current_data = {
            'last_update': None,
            'power_kw': 0,
            'energy_today_kwh': 0,
            'lifetime_energy_mwh': 0,
            'active_inverters': 0,
            'total_inverters': DEFAULT_TOTAL_INVERTERS,
            'health_status': 'Unknown',
            'alerts': [],
            'individual_inverters': [],
            'is_online': False,
            'daily_production_summary': None,
            'daily_report': None
        }
        
        # Historical data for charts
        self.power_history = []
        self.power_history_file = 'power_history_cache.json'
        
        # Load existing power history
        self._load_power_history()
        
        # Session management - track last website access
        self.last_website_access = None
        self.website_interval = UPDATE_INTERVAL_SECONDS
        # Cache for inverter config to avoid re-reading file on every API call
        self._inverter_config_cache = None
        self._inverter_config_mtime = None
        
        # Daily report management
        self.daily_report_sent_today = False
        self.last_daily_report_date = None
        self.sunset_buffer_minutes = SUNSET_BUFFER_MINUTES
        
        # Initialize intelligent alert manager
        self.alert_manager = InverterAlertManager()
        
        # Initialize intelligent timing system
        self.timing_intelligence = create_timing_intelligence_integration()
        
        # Daily peak power tracking for accurate timing intelligence
        self.daily_peaks = {}  # {serial: {'max_power': float, 'peak_time': str, 'date': str}}
        self._reset_daily_peaks_if_new_day()
        
        # Track daily production duration for end-of-day reporting
        self.daily_production = {}
        self.last_production_update = None
        self.production_summary_sent = False
        self.daily_report_history = []

        # Rolling inverter production history (7-day retention)
        self.production_history_file = Path('inverter_production_history.json')
        self.production_history = self._load_production_history()
        self.current_data['recent_production_history'] = (
            self.production_history[-7:]
        )

        # Debug tracking
        self.debug_info = {
            'thread_start_time': datetime.now().isoformat(),
            'iteration_count': 0,
            'last_operation': 'initialization',
            'last_operation_time': datetime.now().isoformat(),
            'errors': []
        }
        
        # Start background data updating
        self.monitoring = True
        self.update_thread = threading.Thread(target=self.background_update)
        self.update_thread.daemon = True
        self.update_thread.start()
        
        # Start sunset-based daily report scheduler
        self.daily_report_thread = threading.Thread(target=self.daily_report_scheduler)
        self.daily_report_thread.daemon = True
        self.daily_report_thread.start()
    
    def _save_inverter_config(self, config):
        """Save inverter configuration to JSON file"""
        try:
            config_file = 'inverter_config.json'
            config['last_updated'] = datetime.now().isoformat()
            
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Invalidate config cache so next read picks up the new file
            self._inverter_config_cache = None
            self._inverter_config_mtime = None
            print(f"✅ Saved inverter configuration")
            return True
            
        except Exception as e:
            print(f"❌ Error saving inverter config: {e}")
            return False
    
    def _reset_daily_peaks_if_new_day(self):
        """Reset daily peak and production tracking when the date changes"""
        today = datetime.now().date().isoformat()
        previous_date = getattr(self, 'daily_metrics_date', None)

        if previous_date == today:
            return

        if previous_date and self.daily_production:
            try:
                self._archive_daily_production(previous_date)
            except Exception as error:
                print(
                    f"⚠️ Archive production failed ({previous_date}): {error}"
                )

        self.daily_metrics_date = today
        self.daily_peaks = {}
        self.daily_production = {}
        self.last_production_update = None
        self.production_summary_sent = False
        print("🔄 Reset daily peaks and production metrics for new day")
    
    def _update_daily_peak(self, serial: str, current_power: float):
        """Update daily peak power tracking for an inverter"""
        today = datetime.now().date().isoformat()
        current_time = datetime.now().strftime("%H:%M")
        
        if serial not in self.daily_peaks:
            # First reading of the day for this inverter
            self.daily_peaks[serial] = {
                'max_power': current_power,
                'peak_time': current_time,
                'date': today
            }
        else:
            # Check if this is a new daily maximum
            if current_power > self.daily_peaks[serial]['max_power']:
                self.daily_peaks[serial].update({
                    'max_power': current_power,
                    'peak_time': current_time,
                    'date': today
                })
    
    def _update_daily_production(self, detailed_stats):
        """Track production minutes using the latest readings"""
        now = datetime.now()
        delta_minutes = 0
        if self.last_production_update:
            elapsed = (now - self.last_production_update).total_seconds() / 60
            if elapsed > 0:
                delta_minutes = max(1, min(30, int(elapsed)))
        self.last_production_update = now

        for stats in detailed_stats or []:
            serial = stats.get('serial')
            if not serial:
                continue
            if serial.startswith('INV_') or serial.startswith('New_'):
                continue

            info = self.daily_production.setdefault(serial, {
                'active_minutes': 0,
                'total_minutes': 0,
                'max_power': 0.0,
                'ever_active': False,
                'energy_kwh': 0.0,
                'samples': 0,
                'array': stats.get('array', 'unknown'),
                'position': stats.get('position', 0),
            })

            current_power = stats.get('current_power', 0.0)
            info['last_power'] = current_power
            info['array'] = stats.get('array', info.get('array', 'unknown'))
            info['position'] = stats.get('position', info.get('position', 0))
            info['max_power'] = max(info.get('max_power', 0.0), current_power)
            info['last_seen'] = now.isoformat()

            if current_power > POWER_THRESHOLD_KW:
                info['ever_active'] = True

            if delta_minutes > 0:
                info['total_minutes'] = (
                    info.get('total_minutes', 0) + delta_minutes
                )
                if current_power > POWER_THRESHOLD_KW:
                    info['active_minutes'] = (
                        info.get('active_minutes', 0) + delta_minutes
                    )

                # Convert power (kW) over elapsed minutes into energy (kWh)
                hours_elapsed = delta_minutes / 60.0
                energy_accumulated = current_power * hours_elapsed
                info['energy_kwh'] = round(
                    info.get('energy_kwh', 0.0) + energy_accumulated, 5
                )
                info['samples'] = info.get('samples', 0) + 1

    def _build_daily_production_summary(self):
        """Summarize production durations for all known inverters"""
        config = self.get_inverter_config()
        inverter_cfg = config.get('inverters', {})
        known_serials = {}
        for inv_id, inv_info in inverter_cfg.items():
            serial = inv_info.get('serial')
            if serial:
                known_serials[serial] = {
                    'array': inv_info.get('array', 'unknown'),
                    'position': inv_info.get('position', 0)
                }

        entries = []
        total_active_minutes = 0
        total_energy_kwh = 0.0
        zero_producers = []

        def _add_entry(serial, meta, info):
            array = meta.get('array', info.get('array', 'unknown'))
            position = meta.get('position', info.get('position', 0))
            active_minutes = info.get('active_minutes', 0)
            active_hours = (
                round(active_minutes / 60, 2) if active_minutes else 0.0
            )
            energy_kwh = round(info.get('energy_kwh', 0.0), 3)
            entry = {
                'serial': serial,
                'array': array,
                'position': position,
                'active_minutes': active_minutes,
                'active_hours': active_hours,
                'max_power': round(info.get('max_power', 0.0), 3),
                'energy_kwh': energy_kwh,
                'samples': info.get('samples', 0),
                'ever_active': info.get('ever_active', False)
            }
            entries.append(entry)
            return active_minutes, energy_kwh

        for serial, meta in known_serials.items():
            info = self.daily_production.get(serial, {})
            active_minutes, energy_kwh = _add_entry(serial, meta, info)
            total_active_minutes += active_minutes
            total_energy_kwh += energy_kwh
            if active_minutes == 0:
                zero_producers.append(serial)

        # Include any extra inverters that reported but are not in config
        for serial, info in self.daily_production.items():
            if serial in known_serials:
                continue
            meta = {
                'array': info.get('array', 'unknown'),
                'position': info.get('position', 0)
            }
            active_minutes, energy_kwh = _add_entry(serial, meta, info)
            total_active_minutes += active_minutes
            total_energy_kwh += energy_kwh
            if active_minutes == 0:
                zero_producers.append(serial)

        entries.sort(
            key=lambda item: (
                item.get('array', 'unknown'),
                item.get('position', 0)
            )
        )

        energy_values = [
            entry['energy_kwh']
            for entry in entries
            if entry.get('energy_kwh') is not None
        ]
        if energy_values:
            median_energy = round(statistics.median(energy_values), 3)
        else:
            median_energy = 0.0

        inverter_count = len(entries) if entries else len(known_serials)
        if total_active_minutes:
            total_hours = round(total_active_minutes / 60, 2)
        else:
            total_hours = 0.0

        if inverter_count:
            average_hours = round(total_hours / inverter_count, 2)
        else:
            average_hours = 0.0

        return {
            'generated_at': datetime.now().isoformat(),
            'date': self.daily_metrics_date,
            'total_inverters': inverter_count,
            'total_inverter_hours': total_hours,
            'average_inverter_hours': average_hours,
            'total_inverter_energy_kwh': round(total_energy_kwh, 3),
            'median_inverter_energy_kwh': median_energy,
            'zero_production': zero_producers,
            'entries': entries
        }

    def _format_daily_production_report(self, summary):
        """Create human-readable runtime summary text"""
        lines = []
        lines.append("⏱️ INVERTER RUNTIME SUMMARY:")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(
            f"Total inverter-hours: {summary['total_inverter_hours']:.1f} h"
        )
        total_energy = summary.get('total_inverter_energy_kwh', 0.0)
        lines.append(
            f"Total inverter energy: {total_energy:.2f} kWh"
        )
        avg_hours = summary['average_inverter_hours']
        lines.append(
            f"Average runtime per inverter: {avg_hours:.1f} h"
        )
        median_energy = summary.get('median_inverter_energy_kwh', 0.0)
        lines.append(
            f"Median inverter energy: {median_energy:.2f} kWh"
        )

        zero_list = summary.get('zero_production', [])
        if zero_list:
            lines.append(
                "Zero production inverters: " + ", ".join(sorted(zero_list))
            )
        else:
            lines.append("Zero production inverters: None")

        if summary.get('entries'):
            lines.append("")
            lines.append("Runtime by inverter (hours):")
            for entry in summary['entries']:
                array_label = entry.get('array', 'unknown') or 'unknown'
                array_label = array_label.title()
                active_hours = entry['active_hours']
                max_power = entry['max_power']
                energy_kwh = entry.get('energy_kwh', 0.0)
                lines.append(
                    f" - {entry['serial']} ({array_label}): "
                    f"{active_hours:.1f}h / {energy_kwh:.2f}kWh "
                    f"(max {max_power:.2f}kW)"
                )

        return "\n".join(lines)

    def _refresh_daily_production_snapshot(self):
        """Update current data with the latest production summary"""
        summary = self._build_daily_production_summary()
        self.current_data['daily_production_summary'] = summary
        return summary

    def _store_daily_report_record(self, report_record):
        """Persist the most recent daily report in memory for quick access"""
        self.current_data['daily_report'] = report_record
        self.daily_report_history.append(report_record)
        # Keep the last two weeks of reports
        self.daily_report_history = self.daily_report_history[-14:]

    def get_inverter_config(self):
        """Get full inverter configuration including array assignments (cached)."""
        try:
            config_file = 'inverter_config.json'
            if not os.path.exists(config_file):
                return {'inverters': {}, 'arrays': {}}

            mtime = os.path.getmtime(config_file)
            if self._inverter_config_cache is not None and mtime == self._inverter_config_mtime:
                return copy.deepcopy(self._inverter_config_cache)

            with open(config_file, 'r') as f:
                config = json.load(f)

            self._inverter_config_cache = config
            self._inverter_config_mtime = mtime
            return copy.deepcopy(config)

        except Exception as e:
            print(f"❌ Error loading inverter config: {e}")
            return {'inverters': {}, 'arrays': {}}
    
    def background_update(self):
        """Background thread to update data every 15 minutes ONLY with debug logging"""
        print("🔄 Starting background data update thread...")
        print("⚠️ Website access limited to every 15 minutes to avoid blocking")
        print("🛡️ Process resilience: Using caffeinate and error recovery")
        
        update_count = 0
        startup_time = datetime.now()
        consecutive_errors = 0
        max_consecutive_errors = 3
        
        while self.monitoring:
            try:
                current_time = datetime.now()
                update_count += 1
                
                # Update debug info
                self.debug_info.update({
                    'iteration_count': update_count,
                    'last_iteration_time': current_time.isoformat(),
                    'last_operation': 'iteration_start',
                    'last_operation_time': current_time.isoformat()
                })
                
                # Debug logging
                print(f"🕐 {current_time.strftime('%H:%M:%S')} - Update #{update_count}")
                print(f"📊 Thread alive: {threading.current_thread().is_alive()}")
                print(f"🔄 Monitoring flag: {self.monitoring}")
                
                # Check if we should fetch from website
                self.debug_info['last_operation'] = 'checking_should_fetch'
                should_fetch = self._should_fetch_from_website()
                print(f"🌐 Should fetch from website: {should_fetch}")
                
                if should_fetch:
                    self.debug_info['last_operation'] = 'fetching_from_website'
                    print("🌐 Time for fresh data fetch from website...")
                    print("🔐 Starting login process...")
                    
                    fetch_success = self._fetch_from_website()
                    
                    if fetch_success:
                        print("✅ Data fetched successfully")
                        print(f"📊 Current power: {self.current_data.get('power_kw', 0):.3f} kW")
                        print(f"🔌 Active inverters: {self.current_data.get('active_inverters', 0)}/{self.current_data.get('total_inverters', 25)}")
                        self.debug_info['last_successful_fetch'] = current_time.isoformat()
                    else:
                        print("❌ Data fetch failed, will retry in 15 minutes")
                        self.debug_info['last_failed_fetch'] = current_time.isoformat()
                else:
                    time_until_next = self._time_until_next_fetch()
                    print(f"📋 Using cached data. Next fetch in {time_until_next} minutes")
                    
                    # Debug cache info
                    if self.current_data.get('last_update'):
                        try:
                            last_update = datetime.fromisoformat(self.current_data['last_update'])
                            age_minutes = (current_time - last_update).total_seconds() / 60
                            print(f"📊 Cache age: {age_minutes:.1f} minutes")
                        except:
                            print("📊 Cache age: Unable to calculate")
                
                print("✅ Update cycle complete. Next check in 15 minutes.")
                print(f"⏰ Uptime: {(current_time - startup_time).total_seconds()/60:.1f} minutes")
                print("💤 Sleeping for 15 minutes...")
                
                # Simple, reliable 15-minute sleep with heartbeat
                self.debug_info['last_operation'] = 'sleeping'
                sleep_start = datetime.now()
                self.debug_info['sleep_start_time'] = sleep_start.isoformat()
                target_sleep_seconds = UPDATE_INTERVAL_SECONDS  # 15 minutes
                
                print(f"   💤 Sleeping for 15 minutes until {(sleep_start + timedelta(seconds=target_sleep_seconds)).strftime('%H:%M:%S')}")
                
                # Sleep in 60-second chunks with heartbeat to prevent system termination
                elapsed_seconds = 0
                while elapsed_seconds < target_sleep_seconds and self.monitoring:
                    time.sleep(60)  # Sleep 1 minute at a time
                    elapsed_seconds += 60
                    
                    # Heartbeat every 5 minutes to show we're alive
                    if elapsed_seconds % 300 == 0:  # Every 5 minutes
                        elapsed_minutes = elapsed_seconds / 60
                        remaining_minutes = (target_sleep_seconds - elapsed_seconds) / 60
                        print(f"   💓 Heartbeat: {elapsed_minutes:.0f}m elapsed, {remaining_minutes:.0f}m remaining")
                        
                        # Update debug info
                        self.debug_info.update({
                            'last_operation_time': datetime.now().isoformat(),
                            'sleep_progress': f"{elapsed_minutes:.0f}m/{remaining_minutes:.0f}m remaining"
                        })
                
                # Reset error counter on successful cycle
                consecutive_errors = 0
                    
            except Exception as e:
                consecutive_errors += 1
                error_msg = f"Background update error: {e}"
                print(f"❌ {error_msg} (Error #{consecutive_errors})")
                traceback.print_exc()
                
                # Track errors in debug info
                self.debug_info['errors'].append({
                    'error': error_msg,
                    'timestamp': datetime.now().isoformat(),
                    'iteration': update_count,
                    'consecutive_errors': consecutive_errors
                })
                
                # Keep only last 10 errors
                if len(self.debug_info['errors']) > 10:
                    self.debug_info['errors'] = self.debug_info['errors'][-10:]
                
                self.debug_info['last_operation'] = 'error_recovery'
                
                # Exponential backoff for consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    print(f"⚠️ Too many consecutive errors ({consecutive_errors}). Extended sleep (30 minutes)...")
                    time.sleep(1800)  # 30 minutes
                    consecutive_errors = 0  # Reset after extended sleep
                else:
                    sleep_duration = min(UPDATE_INTERVAL_SECONDS, 300 * consecutive_errors)  # 5min, 10min, 15min
                    print(f"⚠️ Sleeping {sleep_duration/60:.0f} minutes before retry...")
                    time.sleep(sleep_duration)
        
        print("🛑 Background update thread stopped")
        self.debug_info['thread_stop_time'] = datetime.now().isoformat()
        self.debug_info['last_operation'] = 'thread_stopped'
    
    def _should_fetch_from_website(self):
        """Check if we should fetch from website (only every 15 minutes)"""
        if not self.current_data.get('last_update'):
            return True
        
        try:
            last_update_str = self.current_data['last_update']
            last_update = datetime.fromisoformat(last_update_str)
            now = datetime.now()
            time_diff = (now - last_update).total_seconds()
            return time_diff >= UPDATE_INTERVAL_SECONDS  # 15 minutes
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
                time.sleep(UPDATE_INTERVAL_SECONDS)
                
            except Exception as e:
                print(f"❌ Daily report scheduler error: {e}")
                time.sleep(UPDATE_INTERVAL_SECONDS)
    
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
                if result.get('message'):
                    print(f"ℹ️ Daily report note: {result['message']}")
                print("✅ Automatic daily report sent successfully")
            else:
                print(f"❌ Failed to send automatic daily report: {result.get('error')}")
                
        except Exception as e:
            print(f"❌ Error sending automatic daily report: {e}")

    def _generate_and_send_daily_report(self, trigger='automatic'):
        """Generate, persist, and optionally email the daily report."""
        report_record = {}
        try:

            # Ensure we have the latest production snapshot
            production_summary = self._refresh_daily_production_snapshot()
            production_report = self._format_daily_production_report(
                production_summary
            )
            if self.daily_metrics_date:
                self._archive_daily_production(
                    self.daily_metrics_date,
                    summary=production_summary
                )
            self.production_summary_sent = True
            current_data = self.get_current_data()
            today_history = self.get_power_history(24)
            current_time = datetime.now()
            sunset_time = calculate_sunset_time()
            time_after_sunset = current_time - sunset_time
            hours_after_sunset = time_after_sunset.total_seconds() / 3600
            timing_note = f"Sent {hours_after_sunset:.1f} hours after sunset"

            max_power = max(
                (entry['power'] for entry in today_history),
                default=0
            )
            avg_power = 0
            production_hours = 0
            if today_history:
                total_power = sum(
                    entry['power'] for entry in today_history
                )
                avg_power = total_power / len(today_history)
                productive_samples = sum(
                    1 for entry in today_history if entry['power'] > LOW_POWER_THRESHOLD_KW
                )
                production_hours = productive_samples / 4

            zero_list = production_summary.get('zero_production', [])
            if zero_list:
                zero_serials = ", ".join(zero_list)
                print(f"⚠️ Zero-production inverters today: {zero_serials}")
            else:
                print("✅ All inverters produced power today")

            report_body = f"""📊 Daily Solar Report - {current_time.strftime('%Y-%m-%d')}

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
📊 Efficiency: {(
    (current_data.get('active_inverters', 0) /
     max(current_data.get('total_inverters', 25), 1)) * 100
):.1f}% inverters active
🕐 Last Data Update: {current_data.get('last_update', 'Unknown')}

{production_report}

💡 END-OF-DAY ANALYSIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📉 Generation Status: {'✅ Normal shutdown after sunset' if current_data.get('power_kw', 0) < 0.1 else '⚠️ Still generating after sunset'}
🔋 Daily Performance: {'✅ Good' if current_data.get('energy_today_kwh', 0) > 10 else '⚠️ Low production'}
🔧 System Health: {'✅ All systems nominal' if current_data.get('active_inverters', 0) >= 20 else '⚠️ Some inverters offline'}

🌐 Dashboard: http://solar_monitor:5002
⚙️ Configure alerts: http://solar_monitor:5002/admin
📅 Generated: {current_time.strftime('%Y-%m-%d %H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
This automated daily report is sent after sunset when solar generation stops.
Next report will be sent tomorrow after sunset (~{(sunset_time + timedelta(days=1)).strftime('%H:%M')}).
"""

            alert_config = {}
            alert_config_path = Path('alert_config.json')
            if alert_config_path.exists():
                alert_config = json.loads(alert_config_path.read_text())

            email_enabled = alert_config.get('email_alerts_enabled', False)

            report_record = {
                'date': current_time.date().isoformat(),
                'generated_at': current_time.isoformat(),
                'trigger': trigger,
                'sunset_time': sunset_time.isoformat(),
                'timing_note': timing_note,
                'hours_after_sunset': round(hours_after_sunset, 2),
                'report_body': report_body,
                'report_path': None,
                'file_saved': False,
                'file_error': None,
                'email_enabled': email_enabled,
                'email_sent': False,
                'email_error': None,
                'stats': {
                    'max_power_kw': round(max_power, 3),
                    'avg_power_kw': round(avg_power, 3),
                    'production_hours': round(production_hours, 2),
                    'energy_today_kwh': current_data.get('energy_today_kwh', 0),
                    'lifetime_energy_mwh': current_data.get('lifetime_energy_mwh', 0),
                    'fleet_energy_kwh': production_summary.get('total_inverter_energy_kwh', 0.0),
                },
                'production_summary': production_summary,
                'zero_production_inverters': zero_list,
                'dashboard_snapshot': {
                    'power_kw': current_data.get('power_kw', 0),
                    'active_inverters': current_data.get('active_inverters', 0),
                    'total_inverters': current_data.get('total_inverters', DEFAULT_TOTAL_INVERTERS),
                    'health_status': current_data.get('health_status', 'Unknown'),
                    'is_online': current_data.get('is_online'),
                    'last_update': current_data.get('last_update'),
                }
            }

            try:
                reports_dir = Path('daily_reports')
                reports_dir.mkdir(exist_ok=True)
                report_filename = reports_dir / f"daily_report_{current_time.strftime('%Y%m%d')}.txt"
                report_filename.write_text(report_body, encoding='utf-8')
                report_record['report_path'] = str(report_filename)
                report_record['file_saved'] = True
                print(f"💾 Daily report saved to {report_filename}")
            except Exception as file_error:
                report_record['file_error'] = str(file_error)
                print(f"❌ Failed to save daily report to disk: {file_error}")

            if email_enabled:
                email_config_path = Path('email_config.json')
                if not email_config_path.exists():
                    report_record['email_error'] = 'Email not configured'
                else:
                    config = json.loads(email_config_path.read_text())
                    try:
                        msg = MIMEText(report_body)
                        msg['Subject'] = (
                            f"🌇 End-of-Day Solar Report - {current_time.strftime('%m/%d/%Y')}"
                        )
                        display_name = config.get('display_name', 'Solar Monitor')
                        from_email = config['smtp_username']
                        msg['From'] = f"{display_name} <{from_email}>"
                        msg['To'] = config['email']

                        server = smtplib.SMTP(
                            config['smtp_server'], int(config['smtp_port'])
                        )
                        server.starttls()
                        server.login(
                            config['smtp_username'], config['smtp_password']
                        )
                        server.send_message(msg)
                        server.quit()
                        report_record['email_sent'] = True
                        print("✅ Daily report email sent successfully")
                    except Exception as email_error:
                        report_record['email_error'] = str(email_error)
                        print(f"❌ Failed to send daily report email: {email_error}")
            else:
                print("ℹ️ Email alerts disabled; daily report stored locally only")

            self._store_daily_report_record(report_record)
            report_record['history_snapshot'] = (
                self.get_recent_production_history()
            )

            success = report_record['file_saved'] and (
                report_record['email_sent'] or not email_enabled
            )
            response = {'success': success, 'report': report_record}
            if not email_enabled:
                response['message'] = 'Email alerts disabled; report saved locally'
            elif not report_record['email_sent']:
                response['message'] = report_record.get('email_error')

            return response

        except Exception as error:
            if report_record:
                report_record['email_error'] = str(error)
                self._store_daily_report_record(report_record)
            return {'success': False, 'error': str(error), 'report': report_record}

    def _fetch_from_website(self):
        """Fetch fresh data from the website"""
        try:
            print("🌐 Contacting Chilicon website...")
            self._reset_daily_peaks_if_new_day()
            
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
                current_time = datetime.now()
                power_value = self.current_data['power_kw']
                
                self.power_history.append({
                    'time': current_time.strftime('%H:%M'),
                    'power': power_value,
                    'timestamp': current_time.isoformat(),
                    'data_source': 'success'
                })
                
                # Keep only last 24 hours
                cutoff_time = current_time - timedelta(hours=24)
                self.power_history = [
                    entry for entry in self.power_history
                    if datetime.fromisoformat(entry['timestamp']) > cutoff_time
                ]
                
                # Save power history to cache
                self._save_power_history()
                
                # Fetch detailed individual inverter analysis data (AJAX-based, accurate)
                print("🔍 Fetching detailed individual inverter analysis...")
                detailed_stats = self._fetch_individual_inverter_data()
                if detailed_stats:
                    self.current_data['detailed_inverter_stats'] = detailed_stats
                    print(f"✅ Detailed analysis: {len(detailed_stats)} inverters analyzed")
                    
                    # Convert detailed stats to individual_inverters format for compatibility
                    converted_inverters = []
                    for i, stats in enumerate(detailed_stats):
                        serial = stats['serial']
                        current_power = stats['current_power']
                        
                        # Update daily peak tracking for this inverter
                        self._update_daily_peak(serial, current_power)
                        
                        # Get real peak time from daily tracking
                        peak_info = self.daily_peaks.get(serial, {})
                        real_peak_time = peak_info.get('peak_time', datetime.now().strftime("%H:%M"))
                        
                        converted_inverters.append({
                            'position': i,
                            'serial': serial,
                            'power_w': current_power,  # Keep in kW for display
                            'power': current_power,    # Keep in kW
                            'status': 'active' if current_power > POWER_THRESHOLD_KW else 'inactive',
                            'timestamp': datetime.now().isoformat(),
                            'max_power_today': stats.get('max_power', current_power),
                            'avg_power': stats.get('avg_positive_power', current_power),
                            'peak_time': real_peak_time  # Now uses real peak time!
                        })
                    
                    self.current_data['individual_inverters'] = converted_inverters
                    self._update_daily_production(detailed_stats)
                    self._refresh_daily_production_snapshot()
                    
                    # Update active inverters count from AJAX data
                    active_count = len([s for s in detailed_stats if s['current_power'] > POWER_THRESHOLD_KW])
                    self.current_data['active_inverters'] = active_count
                    self.current_data['total_inverters'] = DEFAULT_TOTAL_INVERTERS
                    print(f"✅ Updated individual inverters: {active_count}/{DEFAULT_TOTAL_INVERTERS} active")

                    # Derive health status directly from AJAX data
                    activity_rate = active_count / DEFAULT_TOTAL_INVERTERS
                    avg_active_power = (
                        sum(s['current_power'] for s in detailed_stats if s['current_power'] > POWER_THRESHOLD_KW)
                        / active_count if active_count else 0
                    )
                    underperforming = len([
                        s for s in detailed_stats
                        if POWER_THRESHOLD_KW < s['current_power'] < avg_active_power * 0.7
                    ])
                    not_active = DEFAULT_TOTAL_INVERTERS - active_count
                    health_issues = []
                    if activity_rate >= 0.95 and underperforming == 0:
                        health_status = "🟢 EXCELLENT"
                    elif activity_rate >= 0.85:
                        health_status = "🟡 GOOD"
                    elif activity_rate >= 0.70:
                        health_status = "🔶 FAIR"
                    else:
                        health_status = "🔴 POOR"
                    if not_active > 0:
                        health_issues.append(f"{not_active} inverter(s) not active")
                    if underperforming > 0:
                        health_issues.append(f"{underperforming} underperforming inverter(s)")
                    self.current_data['health_status'] = health_status
                    self.current_data['alerts'] = health_issues
                    
                    # *** INTELLIGENT TIMING ANALYSIS ***
                    # Analyze timing patterns and learn from inverter behavior
                    print("🧠 Analyzing inverter timing patterns...")
                    try:
                        # Filter out phantom "New_xxxx" and "INV_xxxx" entries before timing analysis
                        real_stats = [stats for stats in detailed_stats 
                                    if not (stats['serial'].startswith('New_') or stats['serial'].startswith('INV_'))]
                        print(f"📊 Filtered timing data: {len(real_stats)}/{len(detailed_stats)} real inverters")
                        
                        timing_analysis = self.timing_intelligence['analyze_and_learn'](real_stats)
                        self.current_data['timing_analysis'] = timing_analysis
                        
                        # Log key insights
                        if timing_analysis.get('anomalies_detected'):
                            anomaly_count = len(timing_analysis['anomalies_detected'])
                            print(f"⚠️ Detected {anomaly_count} timing anomalies")
                        
                        if timing_analysis.get('patterns_learned'):
                            pattern_count = len(timing_analysis['patterns_learned'])
                            print(f"📚 Learned {pattern_count} new timing patterns")
                        
                        # Get timing predictions for tomorrow
                        predictions = self.timing_intelligence['get_predictions']()
                        self.current_data['wake_predictions'] = predictions
                        
                        if predictions.get('east_array_wake'):
                            print(f"🌅 East array expected to wake at: {predictions['east_array_wake']}")
                        if predictions.get('south_array_wake'):
                            print(f"� South array expected to wake at: {predictions['south_array_wake']}")
                            
                    except Exception as e:
                        print(f"⚠️ Timing analysis error: {e}")
                    
                    # *** MISSING ALERT CHECK - ADD THIS ***
                    # Check for alerts after getting detailed stats
                    print("🚨 Checking for inverter alerts...")
                    try:
                        self.alert_manager.check_and_send_alerts(
                            detailed_stats,
                            self.current_data.get('daily_production_summary')
                        )
                        print("✅ Alert check completed")
                    except Exception as e:
                        print(f"❌ Alert check failed: {e}")
                else:
                    print("⚠️ Could not fetch detailed inverter analysis")
                
                return True
            else:
                print("❌ Failed to get power data - login or connection issue")
                self.current_data.update({
                    'is_online': False,
                    'last_update': datetime.now().isoformat(),
                    'connection_error': True
                })
                return False
                
        except Exception as e:
            print(f"❌ Website fetch error: {e}")
            return False

    def _fetch_individual_inverter_data(self):
        """Fetch individual inverter power data using AJAX endpoint"""
        try:
            print("🔍 Fetching individual inverter data from AJAX endpoint...")
            
            # Use the same session from the monitor for authentication
            if not hasattr(self, '_ajax_session'):
                # Create session and login if needed
                monitor = ChiliconLegacyMonitor()
                if not monitor.login(self.username, self.password):
                    print("❌ Failed to login for AJAX data")
                    return []
                self._ajax_session = monitor.session
            
            # Get today's date in the format expected by the API
            today = datetime.now().strftime('%Y-%-m-%-d')
            
            # AJAX endpoint URL
            ajax_url = f"https://cloud.chiliconpower.com/ajax/fetchData?selection=p_out_avg&lastDay={today}&timeSpan=1&aggregateView=none"
            
            print(f"🌐 Fetching from: {ajax_url}")
            
            # Make request with proper headers
            headers = {
                'Accept': 'application/json',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.installation_url
            }
            
            response = self._ajax_session.get(ajax_url, headers=headers)
            
            if response.status_code != 200:
                print(f"❌ AJAX request failed with status {response.status_code}")
                return []
            
            # Parse JSON response
            try:
                data = response.json()
            except Exception as e:
                print(f"❌ Failed to parse JSON response: {e}")
                return []
            
            if not data:
                print("❌ Empty response from AJAX endpoint")
                return []
            
            print(f"✅ Received {len(data)} data points from AJAX endpoint")
            
            # Process the data to get latest power values for each inverter
            inverter_power = {}
            
            # Data format: [timestamp, power_kw, inverter_id]
            for entry in data:
                if len(entry) >= 3:
                    timestamp = entry[0]
                    power_kw = float(entry[1])
                    inverter_id = entry[2]
                    
                    # Keep the latest reading for each inverter
                    if inverter_id not in inverter_power or timestamp > inverter_power[inverter_id]['timestamp']:
                        inverter_power[inverter_id] = {
                            'power_kw': power_kw,
                            'timestamp': timestamp
                        }
            
            print(f"✅ Found latest power data for {len(inverter_power)} inverters")
            
            # Create inverter stats using the power values and configuration
            inverter_stats = []
            config = self.get_inverter_config()
            
            # Map serial numbers to inverter IDs for lookup
            serial_to_id = {}
            for inv_id_str, inv_info in config.get('inverters', {}).items():
                try:
                    inv_id = int(inv_id_str)
                    serial_to_id[inv_info['serial']] = {
                        'id': inv_id,
                        'array': inv_info['array'],
                        'position': inv_info['position']
                    }
                except (ValueError, KeyError):
                    continue
            
            # Create stats for each inverter with power data
            for inverter_id, power_data in inverter_power.items():
                # Find the serial for this inverter ID
                serial = None
                array = 'unknown'
                position = 0
                
                for ser, info in serial_to_id.items():
                    if info['id'] == inverter_id:
                        serial = ser
                        array = info['array']
                        position = info['position']
                        break
                
                if not serial:
                    # Skip unknown inverters instead of creating phantom entries
                    print(f"⚠️ Skipping unknown inverter ID {inverter_id} (not configured)")
                    continue
                
                # AJAX endpoint returns power values in watts directly (250W panels)
                power_watts = float(power_data['power_kw'])  # Already in watts, not kW
                
                # Determine status based on POWER_THRESHOLD_KW (~10W) threshold
                if power_watts > POWER_THRESHOLD_KW:
                    status = 'active'
                elif power_watts > 0:
                    status = 'low_power'
                else:
                    status = 'offline'
                
                # Convert timestamp to readable time
                reading_time = datetime.fromtimestamp(power_data['timestamp']).strftime("%H:%M")
                
                # Update daily peak tracking for accurate timing intelligence
                self._update_daily_peak(serial, power_watts)
                peak_info = self.daily_peaks.get(serial, {})
                real_peak_time = peak_info.get('peak_time', reading_time)
                
                stats = {
                    'inverter_id': inverter_id,
                    'serial': serial,
                    'total_readings': 1,
                    'positive_readings': 1 if power_watts > 0 else 0,
                    'max_power': power_watts,
                    'min_power': power_watts,
                    'avg_power': power_watts,
                    'avg_positive_power': power_watts if power_watts > 0 else 0,
                    'current_power': power_watts,
                    'last_reading_time': reading_time,
                    'peak_time': real_peak_time,  # Real peak time for timing intelligence
                    'status': status,
                    'array': array,
                    'position': position
                }
                
                inverter_stats.append(stats)
            
            # Sort by position for consistent ordering
            inverter_stats.sort(key=lambda x: x['position'])
            
            print(f"✅ Created stats for {len(inverter_stats)} inverters with AJAX data")
            
            # Log some sample data for verification
            for i, stats in enumerate(inverter_stats[:3]):  # Show first 3
                print(f"   📊 {stats['serial']}: {stats['current_power']:.1f}W ({stats['status']})")
            
            return inverter_stats
            
        except Exception as e:
            print(f"❌ Error fetching AJAX inverter data: {e}")
            import traceback
            traceback.print_exc()
            return []

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
                    print(f"📊 Loaded {len(self.power_history)} cached power history entries")
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

    def _load_production_history(self):
        """Load stored inverter production history from disk"""
        try:
            if self.production_history_file.exists():
                with open(self.production_history_file, 'r') as handle:
                    data = json.load(handle)
                records = data.get('records', [])
                records.sort(key=lambda item: item.get('date', ''))
                return records[-7:]
        except Exception as error:
            print(f"⚠️ Could not load production history: {error}")
        return []

    def _save_production_history(self):
        """Persist rolling inverter production history to disk"""
        try:
            payload = {
                'records': self.production_history[-7:],
                'updated_at': datetime.now().isoformat()
            }
            with open(self.production_history_file, 'w') as handle:
                json.dump(payload, handle, indent=2)
        except Exception as error:
            print(f"⚠️ Could not save production history: {error}")

    def _archive_daily_production(self, date_str, summary=None):
        """Archive daily production metrics with 7-day retention."""
        if not date_str:
            return

        if summary is None:
            summary = self._build_daily_production_summary()

        archive_entry = {
            'date': date_str,
            'captured_at': datetime.now().isoformat(),
            'total_inverter_hours': summary.get('total_inverter_hours', 0.0),
            'average_inverter_hours': summary.get(
                'average_inverter_hours', 0.0
            ),
            'total_inverter_energy_kwh': summary.get(
                'total_inverter_energy_kwh', 0.0
            ),
            'entries': summary.get('entries', [])
        }

        # Replace existing entry for the same date (if any)
        filtered_history = [
            record for record in self.production_history
            if record.get('date') != date_str
        ]
        filtered_history.append(archive_entry)
        filtered_history.sort(key=lambda item: item.get('date', ''))
        self.production_history = filtered_history[-7:]
        self._save_production_history()
        self.current_data['recent_production_history'] = (
            self.production_history[-7:]
        )

    def get_recent_production_history(self, days=7):
        """Return recent inverter production records."""
        recent = self.production_history[-days:]
        return copy.deepcopy(recent)  # Deep copy


# Global dashboard instance
dashboard = EnhancedDashboard()


# Debug endpoints for monitoring background thread
@app.route('/debug/status')
def debug_status():
    """Debug endpoint to check background thread status"""
    try:
        status = {
            'monitoring_active': dashboard.monitoring,
            'thread_alive': dashboard.update_thread and dashboard.update_thread.is_alive(),
            'daily_report_thread_alive': dashboard.daily_report_thread and dashboard.daily_report_thread.is_alive(),
            'current_time': datetime.now().isoformat(),
            'debug_info': getattr(dashboard, 'debug_info', {'error': 'No debug info available'})
        }
        
        # Add cache age
        if dashboard.current_data.get('last_update'):
            try:
                last_update = datetime.fromisoformat(dashboard.current_data['last_update'])
                age_seconds = (datetime.now() - last_update).total_seconds()
                status['cache_age_minutes'] = round(age_seconds / 60, 1)
                status['next_update_minutes'] = max(0, round((UPDATE_INTERVAL_SECONDS - age_seconds) / 60, 1))
            except:
                pass
        
        return jsonify(status)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/debug/force-update')
def debug_force_update():
    """Debug endpoint to force a data update"""
    try:
        print("🔧 Debug: Forcing data update...")
        success = dashboard._fetch_from_website()
        return jsonify({
            'success': success,
            'message': 'Data update completed' if success else 'Data update failed',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/admin')
def admin():
    """Admin configuration page"""
    # Load configuration files
    email_config = {}
    alert_config = {}
    imessage_config = {}
    
    try:
        if os.path.exists('email_config.json'):
            with open('email_config.json', 'r') as f:
                email_config = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load email_config.json: {e}")
    
    try:
        if os.path.exists('alert_config.json'):
            with open('alert_config.json', 'r') as f:
                alert_config = json.load(f)
    except Exception as e:
        print(f"Warning: Could not load alert_config.json: {e}")
    
    # iMessage config (may not exist)
    try:
        if os.path.exists('imessage_config.json'):
            with open('imessage_config.json', 'r') as f:
                imessage_config = json.load(f)
    except Exception as e:
        print(f"Info: No imessage_config.json found: {e}")
    
    return render_template('admin.html',
                           email_config=email_config,
                           alert_config=alert_config,
                           imessage_config=imessage_config)


@app.route('/api/admin/test-imessage', methods=['POST'])
def test_imessage():
    """Test iMessage functionality"""
    try:
        # Send test iMessage using alert manager
        result = dashboard.alert_manager.send_alert_imessage(
            "🧪 Test iMessage from Dashboard Admin Panel", 
            "info"
        )
        
        if result.get('success'):
            return jsonify({
                'success': True,
                'message': 'Test iMessage sent successfully!'
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Unknown error occurred')
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'iMessage test failed: {str(e)}'
        })


@app.route('/api/admin/test-alerts', methods=['POST'])
def test_all_alerts():
    """Test all alert methods with multiple alert scenarios"""
    results = {
        'email_tests': [],
        'imessage_tests': [],
        'total_sent': 0,
        'total_failed': 0
    }
    
    # Define test alert scenarios
    test_scenarios = [
        {
            'type': 'low_power',
            'email_subject': '🔋 Test Low Power Alert',
            'email_body': 'TEST: Solar system producing very low power. Multiple inverters may be offline.',
            'imessage_text': '🔋 TEST: Low power alert - Solar system underperforming',
            'severity': 'warning'
        },
        {
            'type': 'offline_inverters',
            'email_subject': '⚠️ Test Offline Inverters Alert',
            'email_body': 'TEST: Multiple microinverters are offline. Inverters 90F00179, 90F00170 not responding.',
            'imessage_text': '⚠️ TEST: Offline inverters detected - Check solar array',
            'severity': 'warning'
        },
        {
            'type': 'system_health',
            'email_subject': '🔧 Test System Health Alert',
            'email_body': 'TEST: Solar monitoring system health check. All systems operational.',
            'imessage_text': '🔧 TEST: System health check - Dashboard monitoring active',
            'severity': 'info'
        }
    ]
    
    try:
        for scenario in test_scenarios:
            # Test email alert for this scenario
            try:
                email_result = dashboard.alert_manager.send_alert_email(
                    scenario['email_subject'],
                    scenario['email_body'],
                    scenario['severity']
                )
                results['email_tests'].append({
                    'scenario': scenario['type'],
                    'result': email_result
                })
                if email_result.get('success'):
                    results['total_sent'] += 1
                else:
                    results['total_failed'] += 1
            except Exception as e:
                results['email_tests'].append({
                    'scenario': scenario['type'],
                    'result': {'success': False, 'error': str(e)}
                })
                results['total_failed'] += 1
            
            # Test iMessage alert for this scenario
            try:
                imessage_result = dashboard.alert_manager.send_alert_imessage(
                    scenario['imessage_text'],
                    scenario['severity']
                )
                results['imessage_tests'].append({
                    'scenario': scenario['type'],
                    'result': imessage_result
                })
                if imessage_result.get('success'):
                    results['total_sent'] += 1
                else:
                    results['total_failed'] += 1
            except Exception as e:
                results['imessage_tests'].append({
                    'scenario': scenario['type'],
                    'result': {'success': False, 'error': str(e)}
                })
                results['total_failed'] += 1
        
        # Create summary message
        if results['total_sent'] > 0:
            message = f"Sent {results['total_sent']} test alerts ({len(test_scenarios)} scenarios x 2 methods)"
            if results['total_failed'] > 0:
                message += f". {results['total_failed']} failed."
            success = True
        else:
            message = f"All {results['total_failed']} test alerts failed. Check configurations."
            success = False
        
        return jsonify({
            'success': success,
            'message': message,
            'details': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Alert test failed: {str(e)}',
            'details': results
        })


@app.route('/api/admin/alert-config', methods=['POST'])
def save_alert_config():
    """Save alert configuration"""
    try:
        config_data = request.get_json()
        
        # Validate the configuration data
        required_fields = [
            'low_power_threshold', 'offline_alert_minutes', 'daily_report_enabled',
            'inverter_alerts_enabled', 'min_active_inverters', 'max_offline_inverters',
            'sunset_buffer_minutes', 'email_alerts_enabled', 'imessage_alerts_enabled'
        ]
        
        for field in required_fields:
            if field not in config_data:
                return jsonify({
                    'success': False,
                    'error': f'Missing required field: {field}'
                })
        
        # Save to alert_config.json
        with open('alert_config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Alert configuration saved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save alert config: {str(e)}'
        })


@app.route('/api/admin/email-config', methods=['POST'])
def save_email_config():
    """Save email configuration"""
    try:
        config_data = request.get_json()
        
        with open('email_config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'Email configuration saved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save email config: {str(e)}'
        })


@app.route('/api/admin/test-email', methods=['POST'])
def test_email():
    """Test email functionality"""
    try:
        result = dashboard.alert_manager.send_alert_email(
            "🧪 Test Email from Dashboard Admin Panel",
            "This is a test email sent from the dashboard admin panel.",
            "info"
        )
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Email test failed: {str(e)}'
        })


@app.route('/api/admin/imessage-config', methods=['POST'])
def save_imessage_config():
    """Save iMessage configuration"""
    try:
        config_data = request.get_json()
        
        with open('imessage_config.json', 'w') as f:
            json.dump(config_data, f, indent=2)
        
        return jsonify({
            'success': True,
            'message': 'iMessage configuration saved successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to save iMessage config: {str(e)}'
        })


@app.route('/api/admin/send-daily-report', methods=['POST'])
def send_daily_report():
    """Send daily report manually"""
    try:
        result = dashboard._generate_and_send_daily_report(trigger='manual')
        status = 200 if result.get('success') else 500
        return jsonify({
            'success': result.get('success', False),
            'message': result.get('message', 'Daily report processed'),
            'report': result.get('report')
        }), status
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to send daily report: {str(e)}'
        })


@app.route('/api/admin/reset-daily-report', methods=['POST'])
def reset_daily_report():
    """Reset daily report status"""
    try:
        dashboard.daily_report_sent_today = False
        dashboard.last_daily_report_date = None
        
        return jsonify({
            'success': True,
            'message': 'Daily report status reset successfully'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to reset daily report: {str(e)}'
        })


@app.route('/api/admin/latest-daily-report')
def get_latest_daily_report():
    """Return the most recent daily report payload"""
    try:
        latest_report = dashboard.current_data.get('daily_report')
        if not latest_report:
            return jsonify({
                'success': False,
                'error': 'No daily report generated yet'
            }), 404

        return jsonify({
            'success': True,
            'report': latest_report
        })

    except Exception as error:
        return jsonify({
            'success': False,
            'error': f'Failed to load latest report: {error}'
        }), 500


@app.route('/api/admin/daily-report-history')
def get_daily_report_history():
    """Return recent daily report metadata"""
    try:
        return jsonify({
            'success': True,
            'reports': dashboard.daily_report_history
        })

    except Exception as error:
        return jsonify({
            'success': False,
            'error': f'Failed to load report history: {error}'
        }), 500


@app.route('/api/admin/inverter-production-history')
def get_inverter_production_history():
    """Return the rolling inverter production history used for analytics"""
    try:
        return jsonify({
            'success': True,
            'history': dashboard.get_recent_production_history()
        })

    except Exception as error:
        return jsonify({
            'success': False,
            'error': f'Failed to load production history: {error}'
        }), 500


@app.route('/api/admin/sunset-info')
def get_sunset_info():
    """Get sunset information"""
    try:
        sunset_time = calculate_sunset_time()
        
        return jsonify({
            'success': True,
            'sunset_time': sunset_time.strftime('%H:%M'),
            'sunset_datetime': sunset_time.isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get sunset info: {str(e)}'
        })


@app.route('/api/admin/inverters', methods=['GET'])
def get_inverter_mapping():
    """Get current inverter configuration with array assignments"""
    try:
        # Get the full configuration from file
        config = dashboard.get_inverter_config()
        
        # Get timing intelligence data
        timing_file = 'inverter_timing_intelligence.json'
        timing_data = {}
        if os.path.exists(timing_file):
            with open(timing_file, 'r') as f:
                timing_data = json.load(f)
        
        # Format for admin panel
        inverter_list = []
        for inverter_id_str, inverter_info in config.get('inverters', {}).items():
            # Handle both numeric IDs and temporary string IDs
            if inverter_id_str.startswith('TEMP_'):
                # For temporary IDs, use the string as-is
                inverter_id = inverter_id_str
                is_temp = True
            else:
                # For regular numeric IDs, convert to int
                try:
                    inverter_id = int(inverter_id_str)
                    is_temp = False
                except ValueError:
                    # Skip invalid IDs
                    print(f"⚠️ Skipping invalid inverter ID: {inverter_id_str}")
                    continue
            
            # Get learned timing data if available (only for non-temp IDs)
            learned_orientation = "unknown"
            reliability_score = 0
            
            if not is_temp:
                for timing in timing_data.get('learned_patterns', {}).values():
                    if timing.get('inverter_id') == inverter_id:
                        learned_orientation = timing.get(
                            'learned_orientation', 'unknown')
                        reliability_score = timing.get('reliability_score', 0)
                        break
                        break
            
            # Map array to display format
            array_display = {
                'east': 'East Array',
                'south': 'South Array', 
                'west': 'West Array'
            }.get(inverter_info['array'], 'Unknown')
            
            # Color coding
            array_colors = {
                'East Array': '#FFA500',  # Orange
                'South Array': '#32CD32',  # Green
                'West Array': '#FF6347',   # Red
                'Unknown': '#808080'       # Gray
            }
            
            inverter_list.append({
                'id': inverter_id,
                'serial': inverter_info['serial'],
                'position': inverter_info['position'],
                'array': inverter_info['array'],
                'array_assignment': array_display,
                'array_color': array_colors.get(array_display, '#808080'),
                'description': inverter_info.get('description', ''),
                'learned_orientation': learned_orientation,
                'reliability_score': reliability_score,
                'status': 'configured'
            })
        
        # Sort by position
        inverter_list.sort(key=lambda x: x['position'])
        
        # Group by array
        arrays = {}
        for array_key, array_info in config.get('arrays', {}).items():
            array_display = {
                'east': 'East Array',
                'south': 'South Array',
                'west': 'West Array'
            }.get(array_key, array_key)
            
            arrays[array_display] = [
                inv for inv in inverter_list 
                if inv['array'] == array_key
            ]
        
        return jsonify({
            'success': True,
            'inverters': inverter_list,
            'arrays': arrays,
            'total_count': len(inverter_list),
            'array_summary': {
                'east_count': len([i for i in inverter_list if i['array'] == 'east']),
                'south_count': len([i for i in inverter_list if i['array'] == 'south']),
                'west_count': len([i for i in inverter_list if i['array'] == 'west'])
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get inverter configuration: {str(e)}'
        })
        
        # Get timing intelligence insights for array orientation
        try:
            # Read timing intelligence data directly from file
            timing_file = 'inverter_timing_intelligence.json'
            timing_data = {}
            if os.path.exists(timing_file):
                with open(timing_file, 'r') as f:
                    timing_raw = json.load(f)
                    # Extract learned patterns for each inverter
                    patterns = timing_raw.get('inverter_patterns', {})
                    for serial, inverter_data in patterns.items():
                        learned = inverter_data.get('learned_pattern', {})
                        timing_data[serial] = {
                            'array_orientation': learned.get(
                                'array_orientation', 'unknown'),
                            'typical_wake_time': learned.get(
                                'typical_wake_time', 'Unknown'),
                            'reliability_score': learned.get(
                                'reliability_score', 0),
                            'days_of_data': learned.get('days_of_data', 0)
                        }
            print(f"✅ Loaded timing data for {len(timing_data)} inverters")
        except Exception as e:
            print(f"⚠️ Could not load timing intelligence data: {e}")
            timing_data = {}
        
        # Convert to a more detailed format with array orientation
        inverter_list = []
        for inverter_id, serial in inverter_id_map.items():
            # Determine inverter type
            if inverter_id in [1902118887, 1902121595]:
                inverter_type = "New Replacement"
            elif inverter_id in [-1053817559, 1093666578]:
                inverter_type = "Previous Replacement"
            else:
                inverter_type = "Original"
            
            # Get learned orientation from timing intelligence
            inverter_timing = timing_data.get(serial, {})
            learned_orientation = inverter_timing.get(
                'array_orientation', 'unknown')
            wake_time = inverter_timing.get('typical_wake_time', 'Unknown')
            reliability = inverter_timing.get('reliability_score', 0)
            days_of_data = inverter_timing.get('days_of_data', 0)
            
            # Determine array assignment based on learned data
            if learned_orientation == 'east_facing':
                array_assignment = 'East Array'
                array_color = '#FF6B35'  # Orange for east
            elif learned_orientation == 'south_facing':
                array_assignment = 'South Array'
                array_color = '#4ECDC4'  # Teal for south
            else:
                array_assignment = 'Unknown'
                array_color = '#95A5A6'  # Gray for unknown
            
            inverter_list.append({
                'id': inverter_id,
                'serial': serial,
                'type': inverter_type,
                'array_assignment': array_assignment,
                'array_color': array_color,
                'learned_orientation': learned_orientation,
                'wake_time': wake_time,
                'reliability_score': reliability,
                'days_of_data': days_of_data,
                'is_positive_id': inverter_id > 0,
                'hex_calculated': (f"{inverter_id:08X}" if inverter_id > 0
                                   else f"{(inverter_id + 2**32):08X}")
            })
        
        # Sort by array assignment, then by serial number
        inverter_list.sort(key=lambda x: (x['array_assignment'], x['serial']))
        
        # Group by array for easier display
        east_array = [inv for inv in inverter_list
                      if inv['array_assignment'] == 'East Array']
        south_array = [inv for inv in inverter_list
                       if inv['array_assignment'] == 'South Array']
        unknown_array = [inv for inv in inverter_list
                         if inv['array_assignment'] == 'Unknown']
        
        arrays = {
            'East Array': east_array,
            'South Array': south_array,
            'Unknown': unknown_array
        }
        
        return jsonify({
            'success': True,
            'inverters': inverter_list,
            'arrays': arrays,
            'total_count': len(inverter_list),
            'array_summary': {
                'east_count': len(arrays['East Array']),
                'south_count': len(arrays['South Array']),
                'unknown_count': len(arrays['Unknown'])
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get inverter mapping: {str(e)}'
        })


@app.route('/api/admin/inverters/update-array', methods=['POST'])
def update_inverter_array():
    """Update an inverter's array assignment"""
    try:
        data = request.get_json()
        inverter_id = data.get('id')
        new_array = data.get('array')
        
        if not inverter_id or not new_array:
            return jsonify({
                'success': False,
                'error': 'Inverter ID and array are required'
            })
        
        # Validate array assignment
        valid_arrays = ['east', 'south', 'west']
        if new_array not in valid_arrays:
            return jsonify({
                'success': False,
                'error': 'Invalid array. Must be east, south, or west'
            })
        
        # Load current configuration
        config = dashboard.get_inverter_config()
        
        # Update the inverter's array assignment
        inverter_id_str = str(inverter_id)
        if inverter_id_str in config.get('inverters', {}):
            config['inverters'][inverter_id_str]['array'] = new_array
            config['inverters'][inverter_id_str]['last_updated'] = datetime.now().isoformat()
            
            # Update array count
            for array_key in config.get('arrays', {}):
                count = len([inv for inv in config['inverters'].values() if inv['array'] == array_key])
                config['arrays'][array_key]['inverter_count'] = count
            
            # Save configuration
            if dashboard._save_inverter_config(config):
                return jsonify({
                    'success': True,
                    'message': f'Updated inverter {config["inverters"][inverter_id_str]["serial"]} to {new_array} array'
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to save configuration'
                })
        else:
            return jsonify({
                'success': False,
                'error': f'Inverter {inverter_id} not found in configuration'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to update inverter array: {str(e)}'
        })


@app.route('/api/admin/inverters/add', methods=['POST'])
def add_inverter():
    """Add a new inverter to the configuration"""
    try:
        data = request.get_json()
        inverter_id = data.get('id')
        serial = data.get('serial')
        array = data.get('array', 'south')
        position = data.get('position')
        description = data.get('description', '')
        
        if not inverter_id or not serial:
            return jsonify({
                'success': False,
                'error': 'Inverter ID and serial are required'
            })
        
        # Load current configuration
        config = dashboard.get_inverter_config()
        
        # Check if inverter already exists
        if str(inverter_id) in config.get('inverters', {}):
            return jsonify({
                'success': False,
                'error': f'Inverter {inverter_id} already exists'
            })
        
        # Find next available position if not provided
        if not position:
            existing_positions = [inv['position'] for inv in config.get('inverters', {}).values()]
            position = max(existing_positions, default=0) + 1
        
        # Add new inverter
        config.setdefault('inverters', {})[str(inverter_id)] = {
            'serial': serial,
            'position': position,
            'array': array,
            'description': description or f"{array.title()}-facing array inverter",
            'added_date': datetime.now().isoformat()
        }
        
        # Update array count
        for array_key in config.get('arrays', {}):
            count = len([inv for inv in config['inverters'].values() if inv['array'] == array_key])
            config['arrays'][array_key]['inverter_count'] = count
        
        # Save configuration
        if dashboard._save_inverter_config(config):
            return jsonify({
                'success': True,
                'message': f'Added inverter {serial} to {array} array'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to save configuration'
            })
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to add inverter: {str(e)}'
        })


@app.route('/api/admin/array-groups', methods=['GET'])
def get_array_groups():
    """Get detailed array group information"""
    try:
        # Get timing intelligence insights
        insights = dashboard.timing_intelligence['get_insights']()
        
        # Get array groups from insights
        array_groups = insights.get('array_groups', {})
        timing_summary = insights.get('timing_summary', {})
        
        # Enhance with current power data if available
        current_inverters = dashboard.current_data.get(
            'individual_inverters', [])
        current_power_map = {
            inv['serial']: inv['power'] for inv in current_inverters
        }
        
        enhanced_groups = {}
        for group_name, group_data in array_groups.items():
            enhanced_inverters = []
            total_current_power = 0
            active_count = 0
            
            for serial in group_data.get('inverters', []):
                timing_info = timing_summary.get(serial, {})
                current_power = current_power_map.get(serial, 0)
                
                if current_power > POWER_THRESHOLD_KW:
                    active_count += 1
                total_current_power += current_power
                
                enhanced_inverters.append({
                    'serial': serial,
                    'wake_time': timing_info.get('typical_wake_time',
                                                 'Unknown'),
                    'sleep_time': timing_info.get('typical_sleep_time',
                                                  'Unknown'),
                    'reliability': timing_info.get('reliability_score', 0),
                    'days_of_data': timing_info.get('days_of_data', 0),
                    'current_power': current_power,
                    'is_active': current_power > POWER_THRESHOLD_KW
                })
            
            enhanced_groups[group_name] = {
                'inverters': enhanced_inverters,
                'total_inverters': len(enhanced_inverters),
                'active_inverters': active_count,
                'total_current_power': round(total_current_power, 3),
                'average_wake_time': group_data.get(
                    'typical_wake_time', 'Unknown'),
                'average_sleep_time': group_data.get(
                    'typical_sleep_time', 'Unknown'),
                'group_confidence': group_data.get('confidence_score', 0)
            }
        
        return jsonify({
            'success': True,
            'array_groups': enhanced_groups,
            'learning_status': insights.get('learning_status', {})
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get array groups: {str(e)}'
        })


@app.route('/api/admin/inverters/add-by-serial', methods=['POST'])
def add_inverter_by_serial():
    """Add a new inverter by serial number only (practical workflow)"""
    try:
        data = request.get_json()
        serial = data.get('serial', '').strip().upper()
        array = data.get('array', 'south')
        description = data.get('description', '')
        
        if not serial:
            return jsonify({
                'success': False,
                'error': 'Serial number is required'
            })
        
        if not re.match(r'^[0-9A-F]{8}$', serial):
            return jsonify({
                'success': False,
                'error': ('Serial number must be exactly 8 hexadecimal '
                          'characters (0-9, A-F)')
            })
        
        # Load current configuration
        config = dashboard.get_inverter_config()
        
        # Check if serial already exists
        for inv_id, inv_data in config.get('inverters', {}).items():
            if inv_data.get('serial') == serial:
                return jsonify({
                    'success': False,
                    'error': f'Serial {serial} already exists for ID {inv_id}'
                })
        
        # Create temporary placeholder ID for discovery
        import time
        temp_id = f"TEMP_{int(time.time())}"
        
        # Find next available position
        existing_positions = [inv['position']
                              for inv in config.get('inverters', {}).values()]
        position = max(existing_positions, default=0) + 1
        
        # Add inverter with temporary ID
        config.setdefault('inverters', {})[temp_id] = {
            'serial': serial,
            'position': position,
            'array': array,
            'description': (description or
                            f"New {array} array inverter (awaiting ID)"),
            'added_date': datetime.now().isoformat(),
            'status': 'awaiting_discovery',
            'temp_id': True
        }
        
        # Update config file
        config['last_updated'] = datetime.now().isoformat()
        dashboard._save_inverter_config(config)
        
        return jsonify({
            'success': True,
            'message': f'Inverter added with serial {serial}',
            'temp_id': temp_id,
            'serial': serial,
            'array': array,
            'position': position,
            'note': ('This inverter will be linked to its system ID '
                     'when discovered in Chilicon data')
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to add inverter by serial: {str(e)}'
        })


@app.route('/api/admin/inverters/convert-hex', methods=['POST'])
def convert_inverter_hex():
    """Convert an inverter ID to hex serial format"""
    try:
        data = request.get_json()
        inverter_id = data.get('inverter_id')
        
        if not inverter_id:
            return jsonify({
                'success': False,
                'error': 'Inverter ID is required'
            })
        
        try:
            inverter_id = int(inverter_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Inverter ID must be a valid integer'
            })
        
        # Convert to hex
        if inverter_id > 0:
            hex_serial = f"{inverter_id:08X}"
            conversion_type = "Positive ID (direct conversion)"
        else:
            hex_serial = f"{(inverter_id + 2**32):08X}"
            conversion_type = "Negative ID (2's complement conversion)"
        
        return jsonify({
            'success': True,
            'inverter_id': inverter_id,
            'hex_serial': hex_serial,
            'conversion_type': conversion_type
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to convert inverter ID: {str(e)}'
        })


@app.route('/api/admin/inverters/discover-unknown', methods=['GET'])
def discover_unknown_inverters():
    """Discover unknown inverter IDs by fetching current system data"""
    try:
        # Get current detailed inverter stats from the dashboard
        detailed_stats = dashboard._fetch_individual_inverter_data()
        
        if not detailed_stats:
            return jsonify({
                'success': False,
                'error': 'Could not fetch current inverter data from system'
            })
        
        # Find unknown inverters (those with "Unknown_" serials)
        unknown_inverters = []
        for stats in detailed_stats:
            if stats['serial'].startswith('Unknown_'):
                inverter_id = stats['inverter_id']
                
                # Calculate what the hex serial should be
                if inverter_id > 0:
                    calculated_hex = f"{inverter_id:08X}"
                    conversion_type = "Positive ID"
                else:
                    calculated_hex = f"{(inverter_id + 2**32):08X}"
                    conversion_type = "Negative ID"
                
                unknown_inverters.append({
                    'inverter_id': inverter_id,
                    'current_serial': stats['serial'],
                    'calculated_hex': calculated_hex,
                    'conversion_type': conversion_type,
                    'current_power': stats['current_power'],
                    'max_power_today': stats['max_power'],
                    'status': stats['status']
                })
        
        return jsonify({
            'success': True,
            'unknown_inverters': unknown_inverters,
            'total_unknown': len(unknown_inverters),
            'message': f'Found {len(unknown_inverters)} unknown inverter(s)'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to discover unknown inverters: {str(e)}'
        })


@app.route('/api/admin/inverters/find-by-serial', methods=['POST'])
def find_inverter_by_serial():
    """Find an inverter ID by reverse-calculating from physical serial number"""
    try:
        data = request.get_json()
        physical_serial = data.get('serial', '').strip().upper()
        
        if not physical_serial:
            return jsonify({
                'success': False,
                'error': 'Physical serial number is required'
            })
        
        # Validate serial format (8 hex characters)
        if not re.match(r'^[0-9A-F]{8}$', physical_serial):
            return jsonify({
                'success': False,
                'error': 'Serial must be exactly 8 hexadecimal characters (0-9, A-F)'
            })
        
        # Convert hex serial back to potential inverter IDs
        hex_value = int(physical_serial, 16)
        
        # Two possible interpretations:
        # 1. Positive ID (direct)
        positive_id = hex_value
        
        # 2. Negative ID (2's complement)
        negative_id = hex_value - 2**32 if hex_value > 2**31 - 1 else hex_value
        
        # Check current system for these IDs
        detailed_stats = dashboard._fetch_individual_inverter_data()
        found_matches = []
        
        if detailed_stats:
            for stats in detailed_stats:
                if stats['inverter_id'] in [positive_id, negative_id]:
                    found_matches.append({
                        'inverter_id': stats['inverter_id'],
                        'current_serial': stats['serial'],
                        'current_power': stats['current_power'],
                        'status': stats['status'],
                        'is_unknown': stats['serial'].startswith('Unknown_')
                    })
        
        return jsonify({
            'success': True,
            'physical_serial': physical_serial,
            'possible_ids': {
                'positive_interpretation': positive_id,
                'negative_interpretation': negative_id if negative_id != positive_id else None
            },
            'found_in_system': found_matches,
            'recommendation': (
                'Found matching inverter in system!' if found_matches else
                'No matching inverter found in current system data. This may be a new/replacement inverter.'
            )
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to find inverter by serial: {str(e)}'
        })


@app.route('/api/admin/inverters/remove', methods=['POST'])
def remove_inverter_mapping():
    """Remove an inverter ID mapping (for offline/replaced inverters)"""
    try:
        data = request.get_json()
        inverter_id = data.get('inverter_id')
        reason = data.get('reason', 'Manual removal')
        
        if not inverter_id:
            return jsonify({
                'success': False,
                'error': 'Inverter ID is required'
            })
        
        try:
            inverter_id = int(inverter_id)
        except ValueError:
            return jsonify({
                'success': False,
                'error': 'Inverter ID must be a valid integer'
            })
        
        # Get current mapping to show what would be removed
        current_mapping = {
            -1863319184: '90F00170',  # Position 1
            -1863319181: '90F00173',  # Position 2
            -1863319160: '90F00188',  # Position 3
            -1863319204: '90F0015C',  # Position 4
            -1863319143: '90F00199',  # Position 6
            -1863319173: '90F0017B',  # Position 7
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
            -1053817559: 'C1300529',  # Position 5 (replacement)
            1093666578: '41300712',   # Position 20 (replacement)
            1902118887: '716007E7',   # New replacement
            1902121595: '7160127B',   # New replacement
            # Removed inverters (no longer on system):
            # -1863319175: '90F00179',  # Position 0 - REMOVED
            # -1863319188: '90F0016C',  # Position 8 - REMOVED
        }
        
        if inverter_id not in current_mapping:
            return jsonify({
                'success': False,
                'error': f'Inverter ID {inverter_id} not found in current mapping'
            })
        
        serial = current_mapping[inverter_id]
        
        # TODO: In production, you'd actually remove this from the mapping
        # and reload the dashboard
        return jsonify({
            'success': True,
            'message': f'Inverter {inverter_id} (Serial: {serial}) would be removed',
            'removed_inverter': {
                'id': inverter_id,
                'serial': serial,
                'reason': reason
            },
            'note': 'This is a preview. In production, this would update the inverter mapping and require a dashboard restart.'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to remove inverter mapping: {str(e)}'
        })


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
            next_update_minutes = max(0, round((UPDATE_INTERVAL_SECONDS - age_seconds) / 60, 1))
            
            current_data['cache_info'] = {
                'age_minutes': age_minutes,
                'next_update_minutes': next_update_minutes,
                'last_update_formatted': last_update.strftime('%H:%M:%S')
            }
        except Exception:
            pass

    weather_payload = {
        'summary': 'Weather monitoring unavailable',
        'is_raining': False,
        'should_suspend_alerts': False,
        'solar_radiation_w_m2': None,
        'status_label': 'Weather monitoring unavailable'
    }
    alerts_suspended = False

    weather_monitor = getattr(dashboard.alert_manager, 'weather_monitor', None)
    if weather_monitor:
        try:
            weather_status = weather_monitor.get_weather_status()
            # Fields are returned flat at the top level (no nested 'weather_data' key)
            weather_data = weather_status
            alerts_suspended = bool(
                weather_status.get('should_suspend_alerts', False)
            )

            is_raining = bool(weather_status.get('is_raining', False))
            weather_payload = {
                'summary': weather_status.get(
                    'summary',
                    'Weather data unavailable'
                ),
                'is_raining': is_raining,
                'should_suspend_alerts': alerts_suspended,
                'temperature_f': weather_data.get('temp'),
                'humidity_percent': weather_data.get('humidity'),
                'precip_rate_in_hr': weather_data.get('precip_rate'),
                'precip_total_in': weather_data.get('precip_total'),
                'solar_radiation_w_m2': weather_data.get('solar_radiation'),
                'observation_time': weather_data.get('observation_time'),
                'source': weather_data.get('source'),
                'cache_timestamp': weather_data.get('timestamp'),
                'status_label': (
                    'Rain detected' if is_raining else 'No rain detected'
                )
            }
        except Exception as error:
            weather_payload = {
                'summary': 'Weather data unavailable',
                'is_raining': False,
                'should_suspend_alerts': False,
                'error': str(error),
                'status_label': 'Weather data unavailable'
            }

    current_data['weather_status'] = weather_payload
    current_data['alerts_suspended_due_to_weather'] = alerts_suspended
    
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
        'total_inverters': data.get('total_inverters', DEFAULT_TOTAL_INVERTERS),
        'last_update': data.get('last_update'),
        'is_online': data.get('is_online', False)
    })


@app.route('/api/timing-intelligence')
def api_timing_intelligence():
    """Get intelligent timing analysis and insights"""
    try:
        # Get timing insights
        insights = dashboard.timing_intelligence['get_insights']()
        
        # Get current timing analysis from cache
        data = dashboard.get_current_data()
        timing_analysis = data.get('timing_analysis', {})
        wake_predictions = data.get('wake_predictions', {})
        
        return jsonify({
            'success': True,
            'insights': insights,
            'latest_analysis': timing_analysis,
            'wake_predictions': wake_predictions,
            'learning_progress': {
                'days_analyzed': insights.get('learning_status', {}).get('days_analyzed', 0),
                'days_required': insights.get('learning_status', {}).get('days_required', 7),
                'completion_percentage': min(100, round(
                    (insights.get('learning_status', {}).get('days_analyzed', 0) / 
                     insights.get('learning_status', {}).get('days_required', 7)) * 100, 1
                ))
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get timing intelligence: {str(e)}'
        })


@app.route('/api/array-groups')
def api_array_groups():
    """Get array group information and timing patterns"""
    try:
        insights = dashboard.timing_intelligence['get_insights']()
        predictions = dashboard.timing_intelligence['get_predictions']()
        
        # Enhanced array group data
        array_groups = insights.get('array_groups', {})
        enhanced_groups = {}
        
        for group_name, group_data in array_groups.items():
            enhanced_groups[group_name] = {
                **group_data,
                'predicted_wake_time': predictions.get(f'{group_name.split("_")[0]}_array_wake'),
                'group_type': group_name.replace('_', ' ').title(),
                'is_learned': group_data.get('count', 0) > 0
            }
        
        return jsonify({
            'success': True,
            'array_groups': enhanced_groups,
            'predictions': predictions,
            'total_inverters_classified': sum(
                group.get('count', 0) for group in array_groups.values()
            )
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get array groups: {str(e)}'
        })


@app.route('/api/timing-anomalies')
def api_timing_anomalies():
    """Get current timing anomalies"""
    try:
        data = dashboard.get_current_data()
        timing_analysis = data.get('timing_analysis', {})
        anomalies = timing_analysis.get('anomalies_detected', [])
        
        # Categorize anomalies
        categorized = {
            'high_priority': [a for a in anomalies if a.get('severity') == 'high'],
            'medium_priority': [a for a in anomalies if a.get('severity') == 'medium'],
            'all_anomalies': anomalies
        }
        
        return jsonify({
            'success': True,
            'anomalies': categorized,
            'anomaly_count': len(anomalies),
            'last_analysis': timing_analysis.get('date'),
            'recommendations': timing_analysis.get('recommendations', [])
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Failed to get timing anomalies: {str(e)}'
        })


def run_dashboard(host='0.0.0.0', port=5000, debug=False):
    """Run the dashboard server"""
    print("🌐 Starting Enhanced Chilicon Dashboard...")
    print(f"📊 Dashboard: http://{host}:{port}")
    print(f"🔍 Debug Status: http://{host}:{port}/debug/status")
    print(f"🔧 Force Update: http://{host}:{port}/debug/force-update")
    print("🔌 Monitoring service active")
    
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    run_dashboard(port=5001, debug=False)
