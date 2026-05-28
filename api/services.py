import math
from datetime import datetime, timedelta
from typing import List, Tuple, Dict, Any

AVG_SPEED_MPH = 55
MAX_DRIVE_HOURS = 11
MAX_WINDOW_HOURS = 14
MAX_CYCLE_HOURS = 70
CYCLE_DAYS = 8
BREAK_AFTER_DRIVE_HOURS = 8
BREAK_DURATION_MIN = 30
FUEL_INTERVAL_MILES = 1000
FUEL_DURATION_MIN = 30
PICKUP_DROPOFF_DURATION_MIN = 60


class HOSPlanner:
    def __init__(self, start_coord, pickup_coord, dropoff_coord,
                 cycle_used_hours: float, leg_distances: List[float],
                 start_datetime: datetime = datetime.now()):
        
        self.start_coord = start_coord
        self.pickup_coord = pickup_coord
        self.dropoff_coord = dropoff_coord
        self.cycle_used_min = cycle_used_hours * 60   # convert to minutes
        self.leg_distances = leg_distances
        self.start_datetime = start_datetime or datetime.now()

        # Build event list: drives, fuel, pickup, dropoff, mandatory breaks
        self.events = self._build_event_list()

    def _build_event_list(self) -> List[Tuple[str, float, int, float]]:
        
        
        events = []
        # Leg 0: start -> pickup
        leg0_miles = self.leg_distances[0]
        fuel_stops = self._calculate_fuel_stops_on_leg(0, leg0_miles)
        events.extend(self._split_leg_into_events(0, leg0_miles, fuel_stops))
        events.append(('pickup', PICKUP_DROPOFF_DURATION_MIN, 0, 0.0))

        # Leg 1: pickup -> dropoff
        leg1_miles = self.leg_distances[1]
        fuel_stops = self._calculate_fuel_stops_on_leg(1, leg1_miles)
        events.extend(self._split_leg_into_events(1, leg1_miles, fuel_stops))
        events.append(('dropoff', PICKUP_DROPOFF_DURATION_MIN, 1, 0.0))

        # Insert mandatory 30‑min breaks after every 8h of driving
        events = self._insert_required_breaks(events)
        events = self._split_long_drives(events)
        return events
    def _split_long_drives(self, events):
    
        new_events = []
        for ev in events:
            if ev[0] == 'drive' and ev[1] > BREAK_AFTER_DRIVE_HOURS * 60:
                dur_min = ev[1]
                miles = ev[3]
                leg_idx = ev[2]
                remaining_min = dur_min
                remaining_miles = miles
                while remaining_min > BREAK_AFTER_DRIVE_HOURS * 60:
                    new_events.append(('drive', BREAK_AFTER_DRIVE_HOURS * 60, leg_idx, 
                                    miles * (BREAK_AFTER_DRIVE_HOURS * 60 / dur_min)))
                    new_events.append(('break', BREAK_DURATION_MIN, leg_idx, 0.0))
                    remaining_min -= BREAK_AFTER_DRIVE_HOURS * 60
                    remaining_miles -= miles * (BREAK_AFTER_DRIVE_HOURS * 60 / dur_min)
                if remaining_min > 0:
                    new_events.append(('drive', remaining_min, leg_idx, remaining_miles))
            else:
                new_events.append(ev)
        return new_events
    def _calculate_fuel_stops_on_leg(self, leg_idx: int, leg_miles: float) -> List[float]:
        
        stops = []
        cumulative = 0.0
        while cumulative + FUEL_INTERVAL_MILES < leg_miles:
            cumulative += FUEL_INTERVAL_MILES
            stops.append(cumulative)
        return stops

    def _split_leg_into_events(self, leg_idx: int, leg_miles: float,
                               fuel_miles: List[float]) -> List[Tuple[str, float, int, float]]:
        
        events = []
        prev = 0.0
        for fuel_mi in fuel_miles:
            if fuel_mi - prev > 0:
                drive_min = (fuel_mi - prev) / AVG_SPEED_MPH * 60
                events.append(('drive', drive_min, leg_idx, fuel_mi - prev))
            events.append(('fuel', FUEL_DURATION_MIN, leg_idx, 0.0))
            prev = fuel_mi
        remaining = leg_miles - prev
        if remaining > 0:
            drive_min = remaining / AVG_SPEED_MPH * 60
            events.append(('drive', drive_min, leg_idx, remaining))
        return events

    def _insert_required_breaks(self, events: List[Tuple]) -> List[Tuple]:
        
        new_events = []
        cum_drive_min = 0.0
        for ev in events:
            if ev[0] == 'drive':
                dur = ev[1]
                if cum_drive_min + dur >= BREAK_AFTER_DRIVE_HOURS * 60:
                    if cum_drive_min >= BREAK_AFTER_DRIVE_HOURS * 60:
                        # Break needed before this segment
                        new_events.append(('break', BREAK_DURATION_MIN, ev[2], 0.0))
                        new_events.append(ev)
                        cum_drive_min = dur
                    else:
                        # Split this drive segment
                        need = BREAK_AFTER_DRIVE_HOURS * 60 - cum_drive_min
                        if need > 0 and need < dur:
                            miles1 = ev[3] * (need / dur)
                            new_events.append(('drive', need, ev[2], miles1))
                            new_events.append(('break', BREAK_DURATION_MIN, ev[2], 0.0))
                            miles2 = ev[3] - miles1
                            new_events.append(('drive', dur - need, ev[2], miles2))
                            cum_drive_min = dur - need
                        else:
                            new_events.append(ev)
                            cum_drive_min += dur
                else:
                    new_events.append(ev)
                    cum_drive_min += dur
            else:
                new_events.append(ev)
        return new_events

    def generate_daily_logs(self):
        daily_logs = []
        remaining_events = self.events.copy()
        total_budget_min = MAX_CYCLE_HOURS * 60
        remaining_budget_min = total_budget_min - self.cycle_used_min
        flag_limit = False
        if remaining_budget_min < 0:
            return [{
                "date": self.start_datetime.strftime("%Y-%m-%d"),
                "segments": [],
                "total_miles": 0.0,
                "total_on_duty_hours": 0.0,
                "driving_hours": 0.0,
                "remarks": "Already exceed 70h/8d limit. No driving allowed.",
                "warning": f"Already over 70h by {-remaining_budget_min/60:.1f}h"
            }], True  

        # Absolute minutes from the trip start (midnight of first day)
        absolute_minutes = 0
        current_shift_start_abs = 6 * 60   # first shift starts at 6:00 on day 0
        day_date = self.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        day_idx = 0

        while remaining_events and remaining_budget_min > 0:
            shift_start = current_shift_start_abs % 1440
            timeline = []
            if shift_start > 0:
                timeline.append((0, "off_duty", shift_start, 0.0, None))
            current_abs = current_shift_start_abs
            day_drive = 0
            day_on = 0
            day_miles = 0
            next_remaining = []
            i = 0
            window_end_abs = (current_shift_start_abs // 1440) * 1440 + (current_shift_start_abs % 1440) + MAX_WINDOW_HOURS * 60

            while i < len(remaining_events):
                ev_type, dur_min, leg_idx, miles = remaining_events[i]

                if ev_type == "drive":
                    # 11‑hour limit
                    if day_drive + dur_min > MAX_DRIVE_HOURS * 60:
                        allowed = MAX_DRIVE_HOURS * 60 - day_drive
                        if allowed > 0:
                            ratio = allowed / dur_min
                            allowed_miles = miles * ratio
                            timeline.append((current_abs % 1440, "driving", allowed, allowed_miles, None))
                            current_abs += allowed
                            day_drive += allowed
                            day_on += allowed
                            day_miles += allowed_miles
                            # Remaining part of this drive
                            remaining_drive = ("drive", dur_min - allowed, leg_idx, miles - allowed_miles)
                            next_remaining.append(remaining_drive)
                        next_remaining.extend(remaining_events[i+1:])
                        break

                    # 14‑hour window
                    if current_abs + dur_min > window_end_abs:
                        allowed = window_end_abs - current_abs
                        if allowed > 0:
                            ratio = allowed / dur_min
                            allowed_miles = miles * ratio
                            timeline.append((current_abs % 1440, "driving", allowed, allowed_miles, None))
                            current_abs += allowed
                            day_drive += allowed
                            day_on += allowed
                            day_miles += allowed_miles
                            remaining_drive = ("drive", dur_min - allowed, leg_idx, miles - allowed_miles)
                            next_remaining.append(remaining_drive)
                        next_remaining.extend(remaining_events[i+1:])
                        break

                    # Whole drive fits
                    timeline.append((current_abs % 1440, "driving", dur_min, miles, None))
                    current_abs += dur_min
                    day_drive += dur_min
                    day_on += dur_min
                    day_miles += miles

                else:  # non‑driving event (pickup, dropoff, fuel, break)
                    if current_abs + dur_min > window_end_abs:
                        next_remaining.extend(remaining_events[i:])
                        break
                    timeline.append((current_abs % 1440, "on_duty", dur_min, 0.0, ev_type))
                    current_abs += dur_min
                    day_on += dur_min

                i += 1
            else:
                next_remaining = []

            # Off‑duty from end of shift to midnight
            end_of_day_abs = ((current_abs // 1440) + 1) * 1440
            if current_abs < end_of_day_abs:
                off_duration = end_of_day_abs - current_abs
                timeline.append((current_abs % 1440, "off_duty", off_duration, 0.0, None))
                current_abs = end_of_day_abs

            # Build log sheet
            log = self._build_log_sheet(day_date, timeline, day_drive, day_on, day_miles)
            remaining_budget_min -= day_on
            if remaining_budget_min < 0:
                log["warning"] = f"70h/8d limit exceeded by {-remaining_budget_min/60:.1f}h"
                flag_limit = True

            daily_logs.append(log)

            # Prepare next day
            day_idx += 1
            day_date += timedelta(days=1)
            remaining_events = next_remaining
            current_shift_start_abs = current_abs + 600   # 10 hours rest

        return daily_logs,flag_limit
    
    def get_route_stops(self) -> List[Dict[str, Any]]:
        stops = []
        cumulative_miles = 0.0
        for ev in self.events:
            ev_type, dur, leg, miles = ev
            if ev_type == 'drive':
                cumulative_miles += miles
            elif ev_type in ['fuel', 'break']:
                stops.append({"type": ev_type, "distance": cumulative_miles})
        return stops
    def _build_log_sheet(self, date, timeline, drive_min, on_duty_min, total_miles):
        
        # timeline entries: (start_min, status, duration_min, miles, subtype)
        # Build a sorted list of status changes
        changes = [(0, "off_duty")]   # start of day
        for start_min, status, _, _, _ in timeline:
            changes.append((start_min, status))
        # Ensure final segment to midnight
        changes.sort(key=lambda x: x[0])
        # Merge consecutive same status if needed (optional)
        merged = []
        for start, status in changes:
            if merged and merged[-1][1] == status:
                continue
            merged.append([start, status])
        merged.append([1440, merged[-1][1]])
        segments = []
        for i in range(len(merged)-1):
            segments.append((merged[i][0], merged[i+1][0], merged[i][1]))

        return {
            "date": date.strftime("%Y-%m-%d"),
            "segments": segments,
            "total_miles": round(total_miles, 1),
            "total_on_duty_hours": round(on_duty_min / 60, 1),
            "driving_hours": round(drive_min / 60, 1),
            "remarks": "Auto‑generated by HOS planner",
            "warning": None
        }