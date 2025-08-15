#ifndef SPATIAL_SLAM_BRIDGE_H
#define SPATIAL_SLAM_BRIDGE_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Version information for compatibility checking
#define SPATIAL_SLAM_VERSION_MAJOR 1
#define SPATIAL_SLAM_VERSION_MINOR 0
#define SPATIAL_SLAM_VERSION_PATCH 0

// Error codes for robust error handling
typedef enum {
    SPATIAL_SLAM_SUCCESS = 0,
    SPATIAL_SLAM_ERROR_INVALID_PARAMETER = -1,
    SPATIAL_SLAM_ERROR_INITIALIZATION_FAILED = -2,
    SPATIAL_SLAM_ERROR_SYSTEM_NOT_READY = -3,
    SPATIAL_SLAM_ERROR_PROCESSING_FAILED = -4,
    SPATIAL_SLAM_ERROR_MAP_LOAD_FAILED = -5,
    SPATIAL_SLAM_ERROR_INSUFFICIENT_FEATURES = -6,
    SPATIAL_SLAM_ERROR_TRACKING_LOST = -7,
    SPATIAL_SLAM_ERROR_OUT_OF_MEMORY = -8,
    SPATIAL_SLAM_ERROR_UNSUPPORTED_FORMAT = -9,
    SPATIAL_SLAM_ERROR_FILE_NOT_FOUND = -10
} SpatialSLAMResult;

// SLAM system state for status tracking
typedef enum {
    SPATIAL_SLAM_STATE_UNINITIALIZED = 0,
    SPATIAL_SLAM_STATE_INITIALIZING = 1,
    SPATIAL_SLAM_STATE_READY = 2,
    SPATIAL_SLAM_STATE_TRACKING = 3,
    SPATIAL_SLAM_STATE_LOST = 4,
    SPATIAL_SLAM_STATE_RELOCALIZATION = 5,
    SPATIAL_SLAM_STATE_FAILED = 6
} SpatialSLAMState;

// Tracking quality levels
typedef enum {
    SPATIAL_SLAM_QUALITY_POOR = 0,
    SPATIAL_SLAM_QUALITY_FAIR = 1,
    SPATIAL_SLAM_QUALITY_GOOD = 2,
    SPATIAL_SLAM_QUALITY_EXCELLENT = 3
} SpatialSLAMQuality;

// Camera calibration parameters
typedef struct {
    float fx, fy;     // Focal lengths
    float cx, cy;     // Principal point
    float k1, k2, k3; // Radial distortion coefficients
    float p1, p2;     // Tangential distortion coefficients
    int width, height; // Image dimensions
} SpatialCameraCalibration;

// 6DOF pose representation (position + quaternion rotation)
typedef struct {
    float position[3];  // x, y, z in world coordinates
    float rotation[4];  // quaternion: x, y, z, w
    double timestamp;   // timestamp in seconds
    float confidence;   // pose confidence [0, 1]
} SpatialPose;

// Tracking statistics for performance monitoring
typedef struct {
    int total_keyframes;
    int total_landmarks;
    int tracking_keyframes;
    float average_reprojection_error;
    float processing_time_ms;
    SpatialSLAMQuality quality;
    int feature_count;
    int matched_features;
} SpatialTrackingStats;

// Map information
typedef struct {
    char map_id[64];
    float center_position[3];
    float bounding_box_min[3];
    float bounding_box_max[3];
    int landmark_count;
    int keyframe_count;
    double creation_timestamp;
    int version;
} SpatialMapInfo;

// Configuration parameters
typedef struct {
    // Feature detection parameters
    int max_features;
    float feature_quality;
    float min_feature_distance;
    
    // Tracking parameters
    float max_reprojection_error;
    int min_tracking_features;
    int max_tracking_iterations;
    
    // Mapping parameters
    int keyframe_threshold;
    float keyframe_distance;
    float keyframe_angle;
    
    // Performance parameters
    bool enable_multithreading;
    int max_threads;
    bool enable_loop_closure;
    bool enable_relocalization;
    
    // Memory management
    int max_keyframes;
    int max_landmarks;
    float memory_limit_mb;
} SpatialSLAMConfig;

// Opaque handle to SLAM system instance
typedef void* SpatialSLAMHandle;

// System Management Functions
/**
 * Get the version of the SLAM library
 */
void SpatialSLAM_GetVersion(int* major, int* minor, int* patch);

/**
 * Create and initialize a new SLAM system instance
 * @param config Configuration parameters (can be NULL for defaults)
 * @param calibration Camera calibration parameters
 * @param vocabulary_path Path to ORB vocabulary file
 * @return Handle to SLAM system or NULL on failure
 */
SpatialSLAMHandle SpatialSLAM_Create(
    const SpatialSLAMConfig* config,
    const SpatialCameraCalibration* calibration,
    const char* vocabulary_path
);

/**
 * Destroy a SLAM system instance and free resources
 * @param handle SLAM system handle
 */
void SpatialSLAM_Destroy(SpatialSLAMHandle handle);

/**
 * Reset the SLAM system to initial state
 * @param handle SLAM system handle
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_Reset(SpatialSLAMHandle handle);

/**
 * Get current system state
 * @param handle SLAM system handle
 * @return Current state
 */
SpatialSLAMState SpatialSLAM_GetState(SpatialSLAMHandle handle);

// Tracking Functions
/**
 * Process a new camera frame for tracking
 * @param handle SLAM system handle
 * @param image_data RGB image data (8-bit per channel)
 * @param width Image width in pixels
 * @param height Image height in pixels
 * @param timestamp Frame timestamp in seconds
 * @param pose Output pose (can be NULL if not needed)
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_ProcessFrame(
    SpatialSLAMHandle handle,
    const uint8_t* image_data,
    int width,
    int height,
    double timestamp,
    SpatialPose* pose
);

/**
 * Get the current camera pose
 * @param handle SLAM system handle
 * @param pose Output pose
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_GetCurrentPose(
    SpatialSLAMHandle handle,
    SpatialPose* pose
);

/**
 * Get tracking statistics
 * @param handle SLAM system handle
 * @param stats Output statistics
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_GetTrackingStats(
    SpatialSLAMHandle handle,
    SpatialTrackingStats* stats
);

/**
 * Enable or disable tracking
 * @param handle SLAM system handle
 * @param enable True to enable, false to disable
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_SetTrackingEnabled(
    SpatialSLAMHandle handle,
    bool enable
);

// Map Management Functions
/**
 * Save the current map to a binary buffer
 * @param handle SLAM system handle
 * @param buffer Output buffer (allocated by caller)
 * @param buffer_size Size of the buffer
 * @param bytes_written Number of bytes actually written
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_SaveMapToBuffer(
    SpatialSLAMHandle handle,
    uint8_t* buffer,
    size_t buffer_size,
    size_t* bytes_written
);

/**
 * Load a map from a binary buffer
 * @param handle SLAM system handle
 * @param buffer Input buffer containing map data
 * @param buffer_size Size of the buffer
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_LoadMapFromBuffer(
    SpatialSLAMHandle handle,
    const uint8_t* buffer,
    size_t buffer_size
);

/**
 * Save the current map to a file
 * @param handle SLAM system handle
 * @param filename Output filename
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_SaveMapToFile(
    SpatialSLAMHandle handle,
    const char* filename
);

/**
 * Load a map from a file
 * @param handle SLAM system handle
 * @param filename Input filename
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_LoadMapFromFile(
    SpatialSLAMHandle handle,
    const char* filename
);

/**
 * Get information about the current map
 * @param handle SLAM system handle
 * @param info Output map information
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_GetMapInfo(
    SpatialSLAMHandle handle,
    SpatialMapInfo* info
);

/**
 * Clear the current map
 * @param handle SLAM system handle
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_ClearMap(SpatialSLAMHandle handle);

// Relocalization Functions
/**
 * Enable relocalization against the loaded map
 * @param handle SLAM system handle
 * @param enable True to enable, false to disable
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_SetRelocalizationEnabled(
    SpatialSLAMHandle handle,
    bool enable
);

/**
 * Request immediate relocalization attempt
 * @param handle SLAM system handle
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_RequestRelocalization(SpatialSLAMHandle handle);

/**
 * Get the last relocalization result
 * @param handle SLAM system handle
 * @param pose Output pose if relocalization succeeded
 * @param confidence Output confidence [0, 1]
 * @return Result code (SUCCESS if relocalization succeeded)
 */
SpatialSLAMResult SpatialSLAM_GetRelocalizationResult(
    SpatialSLAMHandle handle,
    SpatialPose* pose,
    float* confidence
);

// Configuration Functions
/**
 * Update configuration parameters
 * @param handle SLAM system handle
 * @param config New configuration
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_UpdateConfig(
    SpatialSLAMHandle handle,
    const SpatialSLAMConfig* config
);

/**
 * Get current configuration parameters
 * @param handle SLAM system handle
 * @param config Output configuration
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_GetConfig(
    SpatialSLAMHandle handle,
    SpatialSLAMConfig* config
);

// Utility Functions
/**
 * Convert result code to human-readable string
 * @param result Result code
 * @return String description
 */
const char* SpatialSLAM_GetErrorString(SpatialSLAMResult result);

/**
 * Convert state to human-readable string
 * @param state SLAM state
 * @return String description
 */
const char* SpatialSLAM_GetStateString(SpatialSLAMState state);

/**
 * Check if the system has enough memory for operation
 * @param handle SLAM system handle
 * @param required_mb Required memory in MB
 * @return True if enough memory is available
 */
bool SpatialSLAM_CheckMemoryAvailable(
    SpatialSLAMHandle handle,
    float required_mb
);

/**
 * Get memory usage statistics
 * @param handle SLAM system handle
 * @param used_mb Current memory usage in MB
 * @param peak_mb Peak memory usage in MB
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_GetMemoryUsage(
    SpatialSLAMHandle handle,
    float* used_mb,
    float* peak_mb
);

// Callback Functions (for advanced usage)
typedef void (*SpatialSLAMStateCallback)(SpatialSLAMState state, void* user_data);
typedef void (*SpatialSLAMPoseCallback)(const SpatialPose* pose, void* user_data);
typedef void (*SpatialSLAMErrorCallback)(SpatialSLAMResult error, const char* message, void* user_data);

/**
 * Set callback for state changes
 * @param handle SLAM system handle
 * @param callback Callback function
 * @param user_data User data passed to callback
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_SetStateCallback(
    SpatialSLAMHandle handle,
    SpatialSLAMStateCallback callback,
    void* user_data
);

/**
 * Set callback for pose updates
 * @param handle SLAM system handle
 * @param callback Callback function
 * @param user_data User data passed to callback
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_SetPoseCallback(
    SpatialSLAMHandle handle,
    SpatialSLAMPoseCallback callback,
    void* user_data
);

/**
 * Set callback for errors
 * @param handle SLAM system handle
 * @param callback Callback function
 * @param user_data User data passed to callback
 * @return Result code
 */
SpatialSLAMResult SpatialSLAM_SetErrorCallback(
    SpatialSLAMHandle handle,
    SpatialSLAMErrorCallback callback,
    void* user_data
);

#ifdef __cplusplus
}
#endif

#endif // SPATIAL_SLAM_BRIDGE_H