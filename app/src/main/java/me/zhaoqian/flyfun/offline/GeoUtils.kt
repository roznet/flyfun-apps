package me.zhaoqian.flyfun.offline

import kotlin.math.*

/**
 * Geodesic utility functions for aviation route calculations.
 * Uses WGS84 spherical Earth approximation for nautical mile distances.
 */
object GeoUtils {
    private const val EARTH_RADIUS_NM = 3440.065 // nautical miles
    
    /**
     * Calculate great circle distance between two points using Haversine formula.
     * @return Distance in nautical miles
     */
    fun haversineDistance(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val lat1Rad = Math.toRadians(lat1)
        val lat2Rad = Math.toRadians(lat2)
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1)
        
        val a = sin(dLat / 2).pow(2) + cos(lat1Rad) * cos(lat2Rad) * sin(dLon / 2).pow(2)
        val c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return EARTH_RADIUS_NM * c
    }
    
    /**
     * Calculate initial bearing from point 1 to point 2.
     * @return Bearing in degrees (0-360)
     */
    fun initialBearing(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val lat1Rad = Math.toRadians(lat1)
        val lat2Rad = Math.toRadians(lat2)
        val dLon = Math.toRadians(lon2 - lon1)
        
        val y = sin(dLon) * cos(lat2Rad)
        val x = cos(lat1Rad) * sin(lat2Rad) - sin(lat1Rad) * cos(lat2Rad) * cos(dLon)
        
        val bearing = Math.toDegrees(atan2(y, x))
        return (bearing + 360) % 360
    }
    
    /**
     * Calculate cross-track (perpendicular) distance from a point to a great circle route.
     * @param pointLat Point latitude
     * @param pointLon Point longitude  
     * @param startLat Route start latitude
     * @param startLon Route start longitude
     * @param endLat Route end latitude
     * @param endLon Route end longitude
     * @return Cross-track distance in nautical miles (always positive)
     */
    fun crossTrackDistance(
        pointLat: Double, pointLon: Double,
        startLat: Double, startLon: Double,
        endLat: Double, endLon: Double
    ): Double {
        // Angular distance from start to point (in radians)
        val d13 = haversineDistance(startLat, startLon, pointLat, pointLon) / EARTH_RADIUS_NM
        
        // Bearing from start to point
        val theta13 = Math.toRadians(initialBearing(startLat, startLon, pointLat, pointLon))
        
        // Bearing from start to end
        val theta12 = Math.toRadians(initialBearing(startLat, startLon, endLat, endLon))
        
        // Cross-track distance in radians
        val dXt = asin(sin(d13) * sin(theta13 - theta12))
        
        return abs(dXt * EARTH_RADIUS_NM)
    }
    
    /**
     * Calculate along-track distance - how far along the route the closest point is.
     * @return Along-track distance in nautical miles from route start
     */
    fun alongTrackDistance(
        pointLat: Double, pointLon: Double,
        startLat: Double, startLon: Double,
        endLat: Double, endLon: Double
    ): Double {
        // Angular distance from start to point
        val d13 = haversineDistance(startLat, startLon, pointLat, pointLon) / EARTH_RADIUS_NM
        
        // Cross-track distance in radians
        val dXt = crossTrackDistance(pointLat, pointLon, startLat, startLon, endLat, endLon) / EARTH_RADIUS_NM
        
        // Along-track distance - clamp to [-1, 1] to avoid NaN from floating point errors
        val cosRatio = (cos(d13) / cos(dXt)).coerceIn(-1.0, 1.0)
        val dAt = acos(cosRatio)
        
        // Handle NaN case (shouldn't happen with clamping, but be safe)
        return if (dAt.isNaN()) 0.0 else dAt * EARTH_RADIUS_NM
    }
    
    /**
     * Check if a point is within the route segment (not beyond start or end).
     */
    fun isWithinRouteSegment(
        pointLat: Double, pointLon: Double,
        startLat: Double, startLon: Double,
        endLat: Double, endLon: Double
    ): Boolean {
        val routeDistance = haversineDistance(startLat, startLon, endLat, endLon)
        val alongTrack = alongTrackDistance(pointLat, pointLon, startLat, startLon, endLat, endLon)
        
        // Point is within segment if along-track distance is between 0 and route length
        return alongTrack >= 0 && alongTrack <= routeDistance
    }
}
