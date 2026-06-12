#!/usr/bin/env python3
"""
Solar Monitor MCP Server
========================
Exposes solar production data as MCP tools via SSE transport so that
AI assistants (Claude, Copilot, etc.) can query the system in real time.

Tools
-----
- get_production_status   : current power output and active panel count
- get_daily_totals        : today's energy production summary
- get_panel_details       : per-inverter status (optional array filter)
- get_end_of_day_report   : the most recent end-of-day report

The server fetches data from the Flask dashboard running alongside it.
Configure the dashboard URL via the DASHBOARD_URL environment variable
(default: http://localhost:5001).

Run
---
    python solar_mcp_server.py

Or via Docker Compose — see docker-compose.yml.
"""

import os
import json
from datetime import datetime
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

# ── Configuration ────────────────────────────────────────────────────────────
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://localhost:5001").rstrip("/")
MCP_HOST = os.environ.get("MCP_HOST", "0.0.0.0")
MCP_PORT = int(os.environ.get("MCP_PORT", 3001))

# ── FastMCP server ───────────────────────────────────────────────────────────
mcp = FastMCP(
    "solar-monitor",
    host=MCP_HOST,
    port=MCP_PORT,
    instructions=(
        "Solar production monitoring for a 25-panel Chilicon microinverter array. "
        "Use get_production_status for real-time power. "
        "Use get_daily_totals or get_end_of_day_report for cumulative figures."
    ),
)


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _fetch_current() -> dict[str, Any]:
    """Fetch /api/current from the dashboard and return the parsed JSON."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{DASHBOARD_URL}/api/current")
        resp.raise_for_status()
        return resp.json()


async def _fetch_daily_report() -> dict[str, Any]:
    """Fetch the latest daily report from /api/admin/latest-daily-report."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{DASHBOARD_URL}/api/admin/latest-daily-report")
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()


def _fmt_kw(value: float) -> str:
    return f"{value:.3f} kW"


def _fmt_kwh(value: float) -> str:
    return f"{value:.3f} kWh"


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def get_production_status() -> dict[str, Any]:
    """
    Get the current solar production status.

    Returns:
        current_power_kw      : instantaneous power being generated right now
        energy_today_kwh      : total energy produced so far today
        active_panels         : number of microinverters currently generating
        total_panels          : total configured microinverters in the array
        panels_offline        : panels that should be producing but are not
        health_status         : human-readable system health string
        operating_mode        : 'daytime', 'standby', 'night', etc.
        last_update           : ISO timestamp of the most recent data fetch
        cache_age_minutes     : how old the cached reading is
    """
    data = await _fetch_current()

    active = int(data.get("active_inverters", 0))
    total = int(data.get("total_inverters", 25))
    cache_info = data.get("cache_info", {})

    return {
        "current_power_kw": round(float(data.get("power_kw", 0)), 3),
        "current_power_formatted": _fmt_kw(float(data.get("power_kw", 0))),
        "energy_today_kwh": round(float(data.get("energy_today_kwh", 0)), 3),
        "energy_today_formatted": _fmt_kwh(float(data.get("energy_today_kwh", 0))),
        "active_panels": active,
        "total_panels": total,
        "panels_offline": max(0, total - active),
        "health_status": data.get("health_status", "Unknown"),
        "operating_mode": data.get("operating_mode", "unknown"),
        "last_update": data.get("last_update"),
        "cache_age_minutes": cache_info.get("age_minutes"),
        "next_update_minutes": cache_info.get("next_update_minutes"),
    }


@mcp.tool()
async def get_daily_totals() -> dict[str, Any]:
    """
    Get today's cumulative solar production totals.

    Returns figures tracked since midnight for today including total energy,
    average runtime per inverter, and a list of any inverters that produced
    nothing today.

    Returns:
        date                      : calendar date (YYYY-MM-DD)
        energy_today_kwh          : energy reported by the Chilicon portal today
        total_inverter_energy_kwh : sum of per-inverter energy tracked locally
        total_inverter_hours      : total inverter-hours of production today
        average_inverter_hours    : average runtime per inverter in hours
        median_inverter_energy_kwh: median energy per inverter
        total_inverters_tracked   : number of inverters in the summary
        zero_production_panels    : serials of inverters with zero output today
        generated_at              : when the summary was last computed
    """
    data = await _fetch_current()

    portal_kwh = round(float(data.get("energy_today_kwh", 0)), 3)
    summary: dict[str, Any] = data.get("daily_production_summary") or {}

    return {
        "date": summary.get("date", datetime.now().date().isoformat()),
        "energy_today_kwh": portal_kwh,
        "energy_today_formatted": _fmt_kwh(portal_kwh),
        "total_inverter_energy_kwh": round(
            float(summary.get("total_inverter_energy_kwh", 0)), 3
        ),
        "total_inverter_hours": round(
            float(summary.get("total_inverter_hours", 0)), 2
        ),
        "average_inverter_hours": round(
            float(summary.get("average_inverter_hours", 0)), 2
        ),
        "median_inverter_energy_kwh": round(
            float(summary.get("median_inverter_energy_kwh", 0)), 3
        ),
        "total_inverters_tracked": int(summary.get("total_inverters", 0)),
        "zero_production_panels": summary.get("zero_production", []),
        "generated_at": summary.get("generated_at"),
    }


@mcp.tool()
async def get_panel_details(array: str = "") -> dict[str, Any]:
    """
    Get individual microinverter status details.

    Args:
        array: Optional filter. Pass "east" or "south" to limit results to
               one array.  Leave empty for all panels.

    Returns:
        total_count : number of inverters returned
        array_filter: the filter applied (empty = all)
        inverters   : list of individual inverter objects with serial, power,
                      array assignment, and status information
    """
    data = await _fetch_current()

    inverters: list[dict] = data.get("individual_inverters") or []
    if array:
        inverters = [
            inv for inv in inverters
            if (inv.get("array") or "").lower() == array.lower()
        ]

    # Summarise for clarity
    active_count = sum(
        1 for inv in inverters if float(inv.get("current_power", 0)) > 0.01
    )

    return {
        "total_count": len(inverters),
        "active_count": active_count,
        "array_filter": array or "all",
        "inverters": inverters,
    }


@mcp.tool()
async def get_end_of_day_report() -> dict[str, Any]:
    """
    Get the most recent end-of-day production report.

    This report is generated automatically after sunset once generation has
    stopped and contains final daily totals, per-inverter runtime, and
    zero-production alerts.

    Returns:
        available      : whether a report has been generated yet today
        report         : the full report payload (if available)
        message        : human-readable summary (if available)
    """
    payload = await _fetch_daily_report()

    if not payload.get("success"):
        return {
            "available": False,
            "report": None,
            "message": "No end-of-day report has been generated yet.  "
                       "Reports are created automatically after sunset.",
        }

    report = payload.get("report", {})
    production_summary = report.get("production_summary", {})

    # Build a short human-readable summary
    date = production_summary.get("date", "today")
    total_kwh = production_summary.get("total_inverter_energy_kwh", 0)
    total_hours = production_summary.get("total_inverter_hours", 0)
    zero_panels = production_summary.get("zero_production", [])

    summary_lines = [
        f"End-of-day report for {date}:",
        f"  Total energy: {_fmt_kwh(float(total_kwh))}",
        f"  Total inverter-hours: {float(total_hours):.1f} h",
    ]
    if zero_panels:
        summary_lines.append(
            f"  Zero-production panels ({len(zero_panels)}): "
            + ", ".join(sorted(zero_panels))
        )
    else:
        summary_lines.append("  All panels produced energy today.")

    return {
        "available": True,
        "report": report,
        "message": "\n".join(summary_lines),
    }


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"☀️  Solar Monitor MCP Server starting on {MCP_HOST}:{MCP_PORT}")
    print(f"📊 Dashboard URL: {DASHBOARD_URL}")
    print(f"🔌 SSE endpoint:  http://{MCP_HOST}:{MCP_PORT}/sse")
    mcp.run(transport="sse")
