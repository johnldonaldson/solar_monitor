#!/usr/bin/env python3
"""
Weather Monitor for Alert Suspension
Checks weather conditions to suspend alerts during rain/storms
"""

import re
import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path


class WeatherMonitor:
    def __init__(self, weather_station_url=None):
        """Initialize weather monitor"""
        self.weather_station_url = weather_station_url or (
            "https://www.wunderground.com/dashboard/pws/KCAHUNTI63"
        )
        
        # Cache for weather data
        self.cache_file = Path('weather_cache.json')
        self.cache_duration = 300  # 5 minutes
        self.last_check = None
        self.cached_data = None
        
        # Rain thresholds
        self.rain_rate_threshold = 0.01  # in/hr - any measurable rain
        self.high_humidity_threshold = 95  # % - very high humidity often indicates rain
        
        # Alert suspension state
        self.alerts_suspended = False
        self.suspension_start_time = None
        self.last_suspension_alert_sent = None
        
    def fetch_weather_data(self):
        """Fetch current weather data from Weather Underground"""
        try:
            headers = {
                'User-Agent': (
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/91.0.4472.124 Safari/537.36'
                )
            }
            
            response = requests.get(
                self.weather_station_url, 
                headers=headers, 
                timeout=10
            )
            response.raise_for_status()
            
            html_content = response.text
            
            # Try to extract weather data from embedded JSON
            weather_data = self._extract_from_json(html_content)
            if not weather_data:
                # Fallback to regex parsing
                weather_data = {
                    'timestamp': datetime.now().isoformat(),
                    'temperature': self._extract_temperature(html_content),
                    'humidity': self._extract_humidity(html_content),
                    'precip_rate': self._extract_precip_rate(html_content),
                    'precip_total': self._extract_precip_total(html_content),
                    'wind_speed': self._extract_wind_speed(html_content),
                    'pressure': self._extract_pressure(html_content),
                    'conditions': self._determine_conditions(html_content)
                }
            
            # Cache the data
            self._cache_weather_data(weather_data)
            
            return weather_data
            
        except Exception as e:
            print(f"⚠️ Error fetching weather data: {e}")
            # Try to return cached data if available
            if self.cached_data:
                print("📦 Using cached weather data")
                return self.cached_data
            return None
    
    def _extract_from_json(self, html):
        """Extract weather data from embedded JSON"""
        try:
            # Look for PWS daily summary data
            json_pattern = (
                r'"summaries":\[{"stationID":"KCAHUNTI63".*?"imperial":'
                r'{"tempHigh":([0-9.]+).*?"humidityHigh":(\d+).*?'
                r'"precipRate":([0-9.]+).*?"precipTotal":([0-9.]+)'
            )
            
            match = re.search(json_pattern, html, re.DOTALL)
            if match:
                temp_high = float(match.group(1))
                humidity = int(match.group(2))
                precip_rate = float(match.group(3))
                precip_total = float(match.group(4))
                
                return {
                    'timestamp': datetime.now().isoformat(),
                    'temperature': temp_high,
                    'humidity': humidity,
                    'precip_rate': precip_rate,
                    'precip_total': precip_total,
                    'wind_speed': None,
                    'pressure': None,
                    'conditions': self._determine_conditions_from_data(
                        precip_rate, 
                        humidity
                    )
                }
        except Exception:
            pass
        return None
    
    def _determine_conditions_from_data(self, precip_rate, humidity):
        """Determine conditions from extracted numeric data"""
        conditions = []
        
        if precip_rate and precip_rate > 0:
            conditions.append('rain')
        
        if humidity and humidity >= 95:
            conditions.append('high_humidity')
        
        return conditions
    
    def _extract_temperature(self, html):
        """Extract current temperature"""
        try:
            # Look for temperature in the main display
            temp_patterns = [
                r'CURRENT\s+(\d+\.?\d*)\s*°',
                r'(\d+\.?\d*)\s*°F\s+Feels\s+Like',
                r'"tempHigh":(\d+\.?\d*)',
                r'"temperature":(\d+\.?\d*)',
            ]
            for pattern in temp_patterns:
                temp_match = re.search(pattern, html)
                if temp_match:
                    return float(temp_match.group(1))
        except Exception:
            pass
        return None
    
    def _extract_humidity(self, html):
        """Extract humidity percentage"""
        try:
            # Look for humidity patterns in the data
            humidity_patterns = [
                r'HUMIDITY\s+(\d+)\s*%',
                r'"humidity":(\d+)',
                r'"relativeHumidity":(\d+)',
                r'Humidity:\s*(\d+)%'
            ]
            for pattern in humidity_patterns:
                humidity_match = re.search(pattern, html, re.IGNORECASE)
                if humidity_match:
                    return int(humidity_match.group(1))
        except Exception:
            pass
        return None
    
    def _extract_precip_rate(self, html):
        """Extract precipitation rate in inches per hour"""
        try:
            # Look for various precipitation rate patterns
            precip_patterns = [
                r'PRECIP RATE\s+(\d+\.?\d*)\s*in/hr',
                r'"precipRate":(\d+\.?\d*)',
                r'Precipitation Rate:\s*(\d+\.?\d*)\s*in/hr'
            ]
            for pattern in precip_patterns:
                precip_match = re.search(pattern, html, re.IGNORECASE)
                if precip_match:
                    return float(precip_match.group(1))
        except Exception:
            pass
        return 0.0
    
    def _extract_precip_total(self, html):
        """Extract total precipitation accumulation"""
        try:
            # Look for precip total patterns like "1.44 in"
            total_match = re.search(r'PRECIP (?:TOTAL|ACCUM)\s+(\d+\.?\d*)\s*in', html, re.IGNORECASE)
            if total_match:
                return float(total_match.group(1))
        except:
            pass
        return 0.0
    
    def _extract_wind_speed(self, html):
        """Extract wind speed"""
        try:
            # Look for wind speed patterns
            wind_match = re.search(r'WIND.*?(\d+\.?\d*)\s*mph', html, re.IGNORECASE)
            if wind_match:
                return float(wind_match.group(1))
        except:
            pass
        return None
    
    def _extract_pressure(self, html):
        """Extract barometric pressure"""
        try:
            # Look for pressure patterns like "29.81 in"
            pressure_match = re.search(r'PRESSURE\s+(\d+\.?\d*)\s*(?:in|In)', html, re.IGNORECASE)
            if pressure_match:
                return float(pressure_match.group(1))
        except:
            pass
        return None
    
    def _determine_conditions(self, html):
        """Determine general weather conditions based on available data"""
        conditions = []
        
        # Check for rain indicators
        if re.search(r'PRECIP RATE\s+([0-9.]+)', html, re.IGNORECASE):
            rate_match = re.search(r'PRECIP RATE\s+([0-9.]+)', html, re.IGNORECASE)
            if rate_match and float(rate_match.group(1)) > 0:
                conditions.append('rain')
        
        # Check for high humidity
        humidity_match = re.search(r'HUMIDITY\s+(\d+)\s*%', html, re.IGNORECASE)
        if humidity_match and int(humidity_match.group(1)) >= 95:
            conditions.append('high_humidity')
        
        return conditions
    
    def _cache_weather_data(self, data):
        """Cache weather data to file"""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            self.cached_data = data
            self.last_check = datetime.now()
        except Exception as e:
            print(f"⚠️ Error caching weather data: {e}")
    
    def _load_cached_data(self):
        """Load cached weather data if recent"""
        try:
            if not self.cache_file.exists():
                return None
            
            with open(self.cache_file, 'r') as f:
                data = json.load(f)
            
            # Check if cache is still valid
            cache_time = datetime.fromisoformat(data['timestamp'])
            if datetime.now() - cache_time < timedelta(seconds=self.cache_duration):
                self.cached_data = data
                return data
            
        except Exception as e:
            print(f"⚠️ Error loading cached weather data: {e}")
        
        return None
    
    def get_current_weather(self):
        """Get current weather, using cache if recent"""
        # Check if we have recent cached data
        if self.cached_data and self.last_check:
            if datetime.now() - self.last_check < timedelta(seconds=self.cache_duration):
                return self.cached_data
        
        # Try to load from cache file
        cached = self._load_cached_data()
        if cached:
            return cached
        
        # Fetch new data
        return self.fetch_weather_data()
    
    def is_raining(self):
        """Check if it's currently raining"""
        weather_data = self.get_current_weather()
        
        if not weather_data:
            print("⚠️ No weather data available, assuming no rain")
            return False
        
        # Check precipitation rate
        precip_rate = weather_data.get('precip_rate', 0.0)
        if precip_rate >= self.rain_rate_threshold:
            return True
        
        # Check for rain in conditions
        conditions = weather_data.get('conditions', [])
        if 'rain' in conditions:
            return True
        
        # Check humidity as secondary indicator
        humidity = weather_data.get('humidity')
        if humidity and humidity >= self.high_humidity_threshold:
            # High humidity might indicate rain/storm conditions
            return True
        
        return False
    
    def should_suspend_alerts(self):
        """Determine if alerts should be suspended due to weather"""
        if self.is_raining():
            if not self.alerts_suspended:
                # Just started raining - suspend alerts
                self.alerts_suspended = True
                self.suspension_start_time = datetime.now()
                print("🌧️ Weather-based alert suspension activated - rain detected")
            return True
        else:
            if self.alerts_suspended:
                # Rain stopped - resume alerts
                self.alerts_suspended = False
                duration = datetime.now() - self.suspension_start_time
                print(f"☀️ Weather-based alert suspension lifted - rain stopped (suspended for {duration})")
                self.suspension_start_time = None
            return False
    
    def get_suspension_status(self):
        """Get current suspension status and details"""
        weather_data = self.get_current_weather()
        suspended = self.should_suspend_alerts()
        
        status = {
            'suspended': suspended,
            'reason': 'rain_detected' if suspended else None,
            'weather_data': weather_data,
            'suspension_start': self.suspension_start_time.isoformat() if self.suspension_start_time else None
        }
        
        return status
    
    def format_weather_summary(self):
        """Format a human-readable weather summary"""
        weather_data = self.get_current_weather()
        
        if not weather_data:
            return "Weather data unavailable"
        
        summary_parts = []
        
        # Temperature
        temp = weather_data.get('temperature')
        if temp:
            summary_parts.append(f"{temp}°F")
        
        # Precipitation
        precip_rate = weather_data.get('precip_rate', 0)
        if precip_rate > 0:
            summary_parts.append(f"Rain: {precip_rate} in/hr")
        
        # Humidity
        humidity = weather_data.get('humidity')
        if humidity:
            summary_parts.append(f"Humidity: {humidity}%")
        
        # Wind
        wind = weather_data.get('wind_speed')
        if wind:
            summary_parts.append(f"Wind: {wind} mph")
        
        return ", ".join(summary_parts) if summary_parts else "No weather data"


# Test the weather monitor
if __name__ == "__main__":
    print("🌤️ Testing Weather Monitor")
    print("=" * 40)
    
    monitor = WeatherMonitor()
    
    # Get current weather
    weather = monitor.get_current_weather()
    if weather:
        print(f"📊 Current Weather:")
        print(f"  🌡️ Temperature: {weather.get('temperature', 'N/A')}°F")
        print(f"  💧 Precipitation Rate: {weather.get('precip_rate', 0)} in/hr")
        print(f"  🌧️ Total Precipitation: {weather.get('precip_total', 0)} in")
        print(f"  💨 Humidity: {weather.get('humidity', 'N/A')}%")
        print(f"  💨 Wind Speed: {weather.get('wind_speed', 'N/A')} mph")
        print(f"  🗂️ Conditions: {', '.join(weather.get('conditions', ['Clear']))}")
    
    # Check rain status
    is_raining = monitor.is_raining()
    print(f"\n🌧️ Is it raining? {'Yes' if is_raining else 'No'}")
    
    # Check alert suspension
    should_suspend = monitor.should_suspend_alerts()
    print(f"🚨 Should suspend alerts? {'Yes' if should_suspend else 'No'}")
    
    # Get status summary
    status = monitor.get_suspension_status()
    print(f"\n📋 Suspension Status: {status}")
    
    # Weather summary
    summary = monitor.format_weather_summary()
    print(f"\n📝 Weather Summary: {summary}")