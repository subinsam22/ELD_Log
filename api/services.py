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
                 start_datetime: datetime = None):
        """
        :param cycle_used_hours: total on‑duty hours already accumulated in the last 8 days
                                 before the trip starts. Will be deducted from 70h budget.
        """
        self.start_coord = start_coord
        self.pickup_coord = pickup_coord
        self.dropoff_coord = dropoff_coord
        self.cycle_used_min = cycle_used_hours * 60   # convert to minutes
        self.leg_distances = leg_distances
        self.start_datetime = start_datetime or datetime.now()

        # Build event list: drives, fuel, pickup, dropoff, mandatory breaks
        self.events = self._build_event_list()

    def _build_event_list(self) -> List[Tuple[str, float, int, float]]:
        """
        Returns list of (type, duration_min, leg_index, miles_covered).
        Types: 'drive', 'pickup', 'dropoff', 'fuel', 'break'
        """
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
        return events

    def _calculate_fuel_stops_on_leg(self, leg_idx: int, leg_miles: float) -> List[float]:
        """Returns list of miles from leg start where a fuel stop is needed."""
        stops = []
        cumulative = 0.0
        while cumulative + FUEL_INTERVAL_MILES < leg_miles:
            cumulative += FUEL_INTERVAL_MILES
            stops.append(cumulative)
        return stops

    def _split_leg_into_events(self, leg_idx: int, leg_miles: float,
                               fuel_miles: List[float]) -> List[Tuple[str, float, int, float]]:
        """Split a leg into drive segments separated by fuel stops."""
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
        """Insert 30‑min breaks after every 8 cumulative driving hours."""
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

    def generate_daily_logs(self) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Generates daily logs respecting:
        - rolling 70h/8d window (with initial cycle_used_min deducted)
        - 11h driving / 14h window per shift
        - mandatory 10h off between shifts 
        - correct splitting of events across days
        """
        daily_logs = []
        remaining_events = self.events.copy()
        flag_limit = False
        # Rolling window: remaining budget = 70*60 - cycle_used_min
        total_budget_min = MAX_CYCLE_HOURS * 60
        remaining_budget_min = total_budget_min - self.cycle_used_min
        if remaining_budget_min < 0:
            # Already over 70h – no driving allowed
            return [{
                "date": self.start_datetime.strftime("%Y-%m-%d"),
                "segments": [],
                "total_miles": 0.0,
                "total_on_duty_hours": 0.0,
                "driving_hours": 0.0,
                "remarks": "Already exceed 70h/8d limit. No driving allowed.",
                "warning": f"Already over 70h by {-remaining_budget_min/60:.1f}h"
            }], flag_limit

        day_idx = 0
        day_date = self.start_datetime.replace(hour=0, minute=0, second=0, microsecond=0)
        previous_shift_end_min = None   # minutes within that day
        next_shift_start_min = None     # for the next day

        while remaining_events and remaining_budget_min > 0:
            # --- Determine shift start time ---
            if day_idx == 0:
                shift_start_min = 6 * 60   # 6:00 AM
            else:
                shift_start_min = next_shift_start_min

            # Build timeline for this day
            timeline = []
            # Add off-duty from midnight to shift start
            if shift_start_min > 0:
                timeline.append((0, "off_duty", shift_start_min, 0.0, None))

            current_time_min = shift_start_min
            day_drive_min = 0.0
            day_on_duty_min = 0.0
            day_miles = 0.0

            # Process events until day limits reached
            next_remaining = []
            i = 0
            while i < len(remaining_events):
                ev_type, dur_min, leg_idx, miles = remaining_events[i]

                if ev_type == "drive":
                    # 11‑hour limit
                    if day_drive_min + dur_min > MAX_DRIVE_HOURS * 60:
                        allowed = MAX_DRIVE_HOURS * 60 - day_drive_min
                        if allowed > 0:
                            ratio = allowed / dur_min
                            allowed_miles = miles * ratio
                            timeline.append((current_time_min, "driving", allowed, allowed_miles, None))
                            current_time_min += allowed
                            day_drive_min += allowed
                            day_on_duty_min += allowed
                            day_miles += allowed_miles
                            # Remaining part of this drive
                            remaining_miles = miles - allowed_miles
                            remaining_min = dur_min - allowed
                            next_remaining.append(("drive", remaining_min, leg_idx, remaining_miles))
                        # All subsequent events go to next day
                        next_remaining.extend(remaining_events[i+1:])
                        break

                    # 14‑hour window
                    window_end = shift_start_min + MAX_WINDOW_HOURS * 60
                    if current_time_min + dur_min > window_end:
                        allowed = window_end - current_time_min
                        if allowed > 0:
                            ratio = allowed / dur_min
                            allowed_miles = miles * ratio
                            timeline.append((current_time_min, "driving", allowed, allowed_miles, None))
                            current_time_min += allowed
                            day_drive_min += allowed
                            day_on_duty_min += allowed
                            day_miles += allowed_miles
                            remaining_miles = miles - allowed_miles
                            remaining_min = dur_min - allowed
                            next_remaining.append(("drive", remaining_min, leg_idx, remaining_miles))
                        next_remaining.extend(remaining_events[i+1:])
                        break

                    # Whole drive fits
                    timeline.append((current_time_min, "driving", dur_min, miles, None))
                    current_time_min += dur_min
                    day_drive_min += dur_min
                    day_on_duty_min += dur_min
                    day_miles += miles

                else:  # non-driving (pickup, dropoff, fuel, break)
                    window_end = shift_start_min + MAX_WINDOW_HOURS * 60
                    if current_time_min + dur_min > window_end:
                        # Does not fit – move everything from here onward
                        next_remaining.extend(remaining_events[i:])
                        break
                    status = "on_duty"
                    timeline.append((current_time_min, status, dur_min, 0.0, ev_type))
                    current_time_min += dur_min
                    day_on_duty_min += dur_min

                i += 1
            else:
                # All events consumed
                next_remaining = []

            # Add off-duty from end of shift to midnight
            if current_time_min < 1440:
                timeline.append((current_time_min, "off_duty", 1440 - current_time_min, 0.0, None))

            # Build log sheet
            log = self._build_log_sheet(day_date, timeline, day_drive_min, day_on_duty_min, day_miles)

            # Update rolling budget
            remaining_budget_min -= day_on_duty_min
            if remaining_budget_min < 0:
                log["warning"] = f"70h/8d limit exceeded by {-remaining_budget_min/60:.1f}h"
                flag_limit = True
                break
            else:
                log["warning"] = None

            daily_logs.append(log)

            # Prepare for next day
            day_idx += 1
            day_date += timedelta(days=1)
            previous_shift_end_min = current_time_min
            remaining_events = next_remaining

            # Compute next shift start (after 10h rest)
            if remaining_events:
                next_start = current_time_min + 600   # 10 hours in minutes
                if next_start >= 1440:
                    next_shift_start_min = next_start - 1440
                else:
                    next_shift_start_min = next_start
            else:
                next_shift_start_min = None

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
        """Convert timeline to ELD grid segments and summary."""
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