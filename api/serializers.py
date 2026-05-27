from rest_framework import serializers

class TripPlanSerializer(serializers.Serializer):
    current_location = serializers.CharField(
        max_length=200,
        error_messages={
            'required': 'Current location is required.',
            'blank': 'Current location cannot be blank.',
        }
    )
    pickup_location = serializers.CharField(
        max_length=200,
        error_messages={
            'required': 'Pickup location is required.',
            'blank': 'Pickup location cannot be blank.',
        }
    )
    dropoff_location = serializers.CharField(
        max_length=200,
        error_messages={
            'required': 'Dropoff location is required.',
            'blank': 'Dropoff location cannot be blank.',
        }
    )
    current_cycle_used = serializers.FloatField(
        min_value=0,
        max_value=70,
        error_messages={
            'required': 'Current cycle used is required.',
            'invalid': 'Must be a valid number (e.g., 45.5).',
            'min_value': 'Cycle used cannot be less than 0 hours.',
            'max_value': 'Cycle used cannot exceed 70 hours.',
        }
    )

    def validate_current_location(self, value):
        # Additional custom validation (optional)
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Location name too short. Please provide a valid city, state.")
        return value.strip()

    def validate_pickup_location(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Pickup location too short.")
        return value.strip()

    def validate_dropoff_location(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Dropoff location too short.")
        return value.strip()