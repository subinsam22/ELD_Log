from datetime import datetime, timedelta
from .throttles import PlanTripRateThrottle
from rest_framework.decorators import api_view,throttle_classes
from rest_framework.response import Response
from .serializers import TripPlanSerializer
from .route_service import RouteService
from .services import HOSPlanner   # updated class
from rest_framework.throttling import AnonRateThrottle
route_service = RouteService()

@api_view(['POST'])
@throttle_classes([AnonRateThrottle, PlanTripRateThrottle])
def plan_trip(request):
    serializer = TripPlanSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=400)
    
    data = serializer.validated_data
    try:
        cur_coord = route_service.geocode(data['current_location'])
        pick_coord = route_service.geocode(data['pickup_location'])
        drop_coord = route_service.geocode(data['dropoff_location'])
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    
    # Get distances for legs
    try:
        leg1_miles = route_service.get_route_distance(*cur_coord, *pick_coord)
        leg2_miles = route_service.get_route_distance(*pick_coord, *drop_coord)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)
    
    planner = HOSPlanner(
        start_coord=cur_coord,
        pickup_coord=pick_coord,
        dropoff_coord=drop_coord,
        cycle_used_hours=data['current_cycle_used'],
        leg_distances=[leg1_miles, leg2_miles],
        start_datetime=datetime.now()
    )
    logs,flag_limit = planner.generate_daily_logs()
    stops = planner.get_route_stops()
    
    geometry = route_service.get_full_route_geometry([cur_coord, pick_coord, drop_coord])
    logs_stops = []
    for i, log in enumerate(logs):
        
        if i == 0:
            logs_stops.append({"type": "break","distance": log["total_miles"]})
        elif i == len(logs) - 1:
            continue
        else:
            logs_stops.append({"type": "break","distance": log["total_miles"] + logs_stops[-1]["distance"]})
    stops = sorted(stops + logs_stops, key=lambda x: x["distance"])
    
    return Response({
        "logs": logs,
        "flag_limit": flag_limit,
        "route_geometry": geometry,
        "waypoints": [cur_coord, pick_coord, drop_coord],
        "total_distance_miles": leg1_miles + leg2_miles,
        "stops": stops
    })