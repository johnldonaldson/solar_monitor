"""
Simple Weather Monitor for Alert Suspension
Uses Weather Underground API data to detect rain
"""

import json
import re
from datetime import datetime
from pathlib import Path

import requests


class SimpleWeatherMonitor:
    def __init__(self):
        self.station_url = 'https://www.wunderground.com/dashboard/pws/KCAHUNTI63'
        self.cache_file = Path('simple_weather_cache.json')
        self.cache_duration = 300          # seconds (5 minutes)
        self.rain_rate_threshold = 0.01    # in/hr
        self.high_humidity_threshold = 98  # %

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_weather_status(self):
        """Get weather status with rain detection"""
        cached = self._load_cache()
        if cached and self._is_cache_valid(cached):
            return cached

        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(self.station_url, headers=headers, timeout=15)
            response.raise_for_status()
            html = response.text

            obs = self._parse_latest_observation(html)
            if obs:
                temp         = obs.get('temp')
                humidity     = obs.get('humidity')
                precip_rate  = obs.get('precip_rate')
                precip_total = obs.get('precip_total')
                solar        = obs.get('solar_radiation')
                obs_time     = obs.get('observation_time')
            else:
                temp         = self._extract_temp(html)
                humidity     = self._extract_humidity(html)
                precip_rate  = self._extract_precip_rate(html)
                precip_total = self._extract_precip_total(html)
                solar        = self._extract_solar_radiation(html)
                obs_time     = datetime.now().isoformat()
            wind_speed = self._extract_wind_speed(html)
            wind_gust = self._extract_wind_gust(html)
            wind_direction = self._extract_wind_direction(html)
            pressure = self._extract_pressure(html)
            uv_index = self._extract_uv_index(html)
            uv_description = self._extract_uv_description(html)
            condition_phrase = self._extract_condition_phrase(html)

            data = {
                'temp':             temp,
                'humidity':         humidity,
                'precip_rate':      precip_rate,
                'precip_total':     precip_total,
                'solar_radiation':  solar,
                'wind_speed':       wind_speed,
                'wind_gust':        wind_gust,
                'wind_direction':   wind_direction,
                'pressure':         pressure,
                'uv_index':         uv_index,
                'uv_description':   uv_description,
                'condition_phrase': condition_phrase,
                'observation_time': obs_time,
                'timestamp':        datetime.now().isoformat(),
            }
            data.update(self._process_weather_data(data))
            self._save_cache(data)
            return data

        except requests.RequestException as e:
            print(f"⚠️ Weather fetch error: {e}")
            return self._unavailable_status()
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            print(f"⚠️ Weather parse error: {e}")
            return self._unavailable_status()

    # ------------------------------------------------------------------
    # Extraction helpers
    # ------------------------------------------------------------------

    def _extract_temp(self, html):
        """Extract temperature"""
        return self._extract_float(html, (
            r'"imperial":\s*\{[^\}]*"temp":([0-9.]+)',
            r'CURRENT\s+(\d+\.?\d*)\s*°',
            r'(\d+\.?\d*)\s*°F',
            r'"tempHigh":([0-9.]+)',
        ))

    def _extract_humidity(self, html):
        """Extract humidity"""
        return self._extract_int(html, (
            r'"relativeHumidity":(\d+)',
            r'HUMIDITY\s+(\d+)\s*%',
            r'"humidityHigh":(\d+)',
        ))

    def _extract_precip_rate(self, html):
        """Extract precipitation rate"""
        return self._extract_float_max(html, (
            r'"precipRate":([0-9.]+)',
            r'PRECIP RATE\s+([0-9.]+)\s*in/hr',
        ))

    def _extract_precip_total(self, html):
        """Extract total precipitation"""
        return self._extract_float_max(html, (
            r'"precipTotal":([0-9.]+)',
            r'PRECIP\s+(?:TOTAL|ACCUM)\s+([0-9.]+)\s*in',
        ))

    def _extract_solar_radiation(self, html):
        """Extract solar radiation (W/m^2) from current-only fields."""
        return self._extract_float(html, (
            r'"solarRadiation":([0-9.]+)',
            r'SOLAR\s+RADIATION\s+CURRENT\s+([0-9.]+)\s*watts/m²',
            r'SOLAR\s+RADIATION\s+CURRENT\s+([0-9.]+)\s*watts/m2',
        ))

    def _extract_wind_speed(self, html):
        """Extract wind speed (mph)"""
        return self._extract_float(html, (
            r'"windSpeed":([0-9.]+)',
            r'WIND\s*&\s*GUST\s+([0-9.]+)\s*/\s*[0-9.]+\s*mph',
        ))

    def _extract_wind_gust(self, html):
        """Extract wind gust (mph)"""
        return self._extract_float(html, (
            r'"windGust":([0-9.]+)',
            r'WIND\s*&\s*GUST\s+[0-9.]+\s*/\s*([0-9.]+)\s*mph',
        ))

    def _extract_wind_direction(self, html):
        """Extract wind direction"""
        return self._extract_text(html, (
            r'"windDirectionCardinal":"([^"]+)"',
            r'WIND\s+FROM\s+([A-Z]+)',
        ))

    def _extract_pressure(self, html):
        """Extract pressure (inHg)"""
        return self._extract_float(html, (
            r'"pressureAltimeter":([0-9.]+)',
            r'"pressureMeanSeaLevel":([0-9.]+)',
            r'PRESSURE\s+([0-9.]+)\s*in',
        ))

    def _extract_uv_index(self, html):
        """Extract UV index"""
        return self._extract_float(html, (
            r'"uvIndex":([0-9.]+)',
            r'CURRENT\s+UV\s+([0-9.]+)',
        ))

    def _extract_uv_description(self, html):
        """Extract UV description"""
        return self._extract_text(html, (
            r'"uvDescription":"([^"]+)"',
        ))

    def _extract_condition_phrase(self, html):
        """Extract current sky/conditions phrase."""
        return self._extract_text(html, (
            r'"cloudCoverPhrase":"([^"]+)"',
            r'"wxPhraseLong":"([^"]+)"',
            r'"wxPhraseMedium":"([^"]+)"',
        ))

    def _extract_float(self, html, patterns):
        """Extract first float value using multiple patterns"""
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1))
                except (ValueError, IndexError):
                    continue
        return 0.0

    def _extract_float_max(self, html, patterns):
        """Extract the maximum float value across all pattern matches"""
        values = []
        for pattern in patterns:
            if isinstance(pattern, tuple):
                pattern = pattern[0]
            for match in re.findall(pattern, html, re.IGNORECASE):
                try:
                    values.append(float(match))
                except (ValueError, IndexError):
                    continue
        return max(values) if values else 0.0

    def _extract_int(self, html, patterns):
        """Extract integer value using multiple patterns"""
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                try:
                    return int(m.group(1))
                except (ValueError, IndexError):
                    continue
        return 0

    def _extract_text(self, html, patterns):
        """Extract first text value using multiple patterns"""
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                try:
                    value = m.group(1).strip()
                except (ValueError, IndexError, AttributeError):
                    continue
                if value:
                    return value
        return None

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    def _process_weather_data(self, data):
        """Process weather data and determine rain status"""
        precip_rate  = data.get('precip_rate') or 0
        precip_total = data.get('precip_total') or 0
        humidity     = data.get('humidity') or 0

        reasons = []
        is_raining = False

        if precip_rate >= self.rain_rate_threshold:
            is_raining = True
            reasons.append(f"Active precipitation: {precip_rate} in/hr")

        if humidity >= self.high_humidity_threshold:
            reasons.append(f"Very high humidity: {humidity}%")

        should_suspend = is_raining
        condition_phrase = data.get('condition_phrase')

        if is_raining:
            summary = ', '.join(reasons)
        elif condition_phrase:
            summary = condition_phrase
        else:
            summary = 'Dry right now'

        detail_parts = []
        if humidity:
            detail_parts.append(f"Humidity {humidity:.0f}%")

        wind_direction = data.get('wind_direction')
        wind_speed = data.get('wind_speed')
        if wind_speed:
            wind_text = f"Wind {wind_speed:.1f} mph"
            if wind_direction:
                wind_text += f" from {wind_direction}"
            detail_parts.append(wind_text)

        pressure = data.get('pressure')
        if pressure:
            detail_parts.append(f"Pressure {pressure:.2f} in")

        uv_index = data.get('uv_index')
        uv_description = data.get('uv_description')
        if uv_index is not None and uv_index != 0:
            uv_text = f"UV {uv_index:.0f}"
            if uv_description:
                uv_text += f" ({uv_description})"
            detail_parts.append(uv_text)
        elif uv_description:
            detail_parts.append(f"UV {uv_description}")

        if not is_raining and precip_rate == 0 and precip_total == 0:
            detail_parts.append('No precipitation at the station')

        if reasons:
            detail_parts = reasons + detail_parts

        condition_detail = ' | '.join(detail_parts) if detail_parts else summary

        return {
            'is_raining':           is_raining,
            'should_suspend_alerts': should_suspend,
            'summary':              summary,
            'condition_detail':     condition_detail,
        }

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def _load_cache(self):
        """Load cached weather data"""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, encoding='utf-8') as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def _save_cache(self, payload):
        """Save weather data to cache"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
        except OSError as e:
            print(f"⚠️ Cache save error: {e}")

    def _is_cache_valid(self, cached_data):
        """Check if cached data is still valid"""
        try:
            ts = cached_data['timestamp']
            age = (datetime.now() - datetime.fromisoformat(ts)).total_seconds()
            return age < self.cache_duration
        except (KeyError, ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_latest_observation(self, html):
        """Parse latest observation block when available"""
        m = re.search(r'"observations":\[(.*?)\]\}', html, re.DOTALL)
        if not m:
            return None
        try:
            # Take the last complete observation object
            raw = '[' + m.group(1) + ']'
            observations = json.loads(raw)
            if not observations:
                return None
            obs = observations[-1]
            imperial = obs.get('imperial', {})
            return {
                'temp':             imperial.get('tempAvg') or imperial.get('temp'),
                'humidity':         obs.get('humidityAvg') or obs.get('humidity'),
                'precip_rate':      imperial.get('precipRate'),
                'precip_total':     imperial.get('precipTotal'),
                'solar_radiation':  obs.get('solarRadiation') or obs.get('solarRadiationHigh'),
                'observation_time': obs.get('obsTimeLocal'),
            }
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _unavailable_status():
        return {
            'is_raining':            False,
            'should_suspend_alerts': False,
            'summary':               'Weather monitoring unavailable',
            'condition_detail':      'Weather monitoring unavailable',
            'temp':                  None,
            'humidity':              None,
            'precip_rate':           None,
            'precip_total':          None,
            'solar_radiation':       None,
            'wind_speed':            None,
            'wind_gust':             None,
            'wind_direction':        None,
            'pressure':              None,
            'uv_index':              None,
            'uv_description':        None,
            'condition_phrase':      None,
            'observation_time':      None,
            'timestamp':             datetime.now().isoformat(),
        }


if __name__ == '__main__':
    print('🌤️  Testing Simple Weather Monitor')
    print('=' * 40)
    monitor = SimpleWeatherMonitor()
    status = monitor.get_weather_status()
    suspend_flag = status.get('should_suspend_alerts')
    details      = status.get('summary')
    print(f"🌧️  Raining: {'Yes' if status.get('is_raining') else 'No'}")
    print(f"🚨 Suspend Alerts: {'Yes' if suspend_flag else 'No'}")
    print(f"📝 Summary: {details}")
    weather_data = status
    print('\n📊 Weather Details:')
    print(f"  🌡️  Temperature: {weather_data.get('temp', 'N/A')}°F")
