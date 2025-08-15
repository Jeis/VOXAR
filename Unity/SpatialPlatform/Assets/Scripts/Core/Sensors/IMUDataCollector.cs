/*
 * Spatial Platform - IMU Data Collector
 * Collects and processes Inertial Measurement Unit data for VIO integration
 */

using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

namespace SpatialPlatform.Sensors
{
    [Serializable]
    public struct IMUReading
    {
        public double timestamp;
        public Vector3 acceleration;    // m/s²
        public Vector3 gyroscope;      // rad/s
        public Vector3 magnetometer;   // μT (microtesla)
        public float temperature;      // °C
        public bool isValid;
        
        public IMUReading(double time, Vector3 accel, Vector3 gyro, Vector3 mag, float temp = 0f)
        {
            timestamp = time;
            acceleration = accel;
            gyroscope = gyro;
            magnetometer = mag;
            temperature = temp;
            isValid = true;
        }
    }
    
    [Serializable]
    public struct IMUCalibration
    {
        public Vector3 accelBias;
        public Vector3 gyroBias;
        public Vector3 magBias;
        public Matrix4x4 accelScale;
        public Matrix4x4 gyroScale;
        public bool isCalibrated;
        
        public static IMUCalibration Default => new IMUCalibration
        {
            accelBias = Vector3.zero,
            gyroBias = Vector3.zero,
            magBias = Vector3.zero,
            accelScale = Matrix4x4.identity,
            gyroScale = Matrix4x4.identity,
            isCalibrated = false
        };
    }
    
    public class IMUDataCollector : MonoBehaviour
    {
        [Header("IMU Configuration")]
        [SerializeField] private float samplingRate = 200f; // Hz
        [SerializeField] private int bufferSize = 1000;
        [SerializeField] private bool enableAutoCalibration = true;
        [SerializeField] private float calibrationDuration = 10f; // seconds
        
        [Header("Filtering")]
        [SerializeField] private bool enableLowPassFilter = true;
        [SerializeField] private float lowPassAlpha = 0.1f;
        [SerializeField] private bool enableOutlierDetection = true;
        [SerializeField] private float outlierThreshold = 3.0f; // standard deviations
        
        // Sensor references
        private Accelerometer accelerometer;
        private Gyroscope gyroscope;
        private Magnetometer magnetometer;
        
        // Data storage
        private CircularBuffer<IMUReading> imuBuffer;
        private IMUCalibration calibration;
        
        // Filtering state
        private Vector3 filteredAccel;
        private Vector3 filteredGyro;
        private Vector3 filteredMag;
        
        // Calibration state
        private bool isCalibrating;
        private float calibrationStartTime;
        private List<Vector3> calibrationAccelData;
        private List<Vector3> calibrationGyroData;
        private List<Vector3> calibrationMagData;
        
        // Events
        public event Action<IMUReading> OnIMUDataReceived;
        public event Action<IMUCalibration> OnCalibrationComplete;
        public event Action<string> OnError;
        
        // Performance monitoring
        private float lastSampleTime;
        private int sampleCount;
        private float actualSamplingRate;
        
        private void Awake()
        {
            InitializeSensors();
            InitializeDataStructures();
        }
        
        private void InitializeSensors()
        {
            try
            {
                // Enable sensors
                InputSystem.EnableDevice(Accelerometer.current);
                InputSystem.EnableDevice(Gyroscope.current);
                InputSystem.EnableDevice(Magnetometer.current);
                
                // Get sensor references
                accelerometer = Accelerometer.current;
                gyroscope = Gyroscope.current;
                magnetometer = Magnetometer.current;
                
                // Check sensor availability
                if (accelerometer == null)
                {
                    OnError?.Invoke("Accelerometer not available on this device");
                    return;
                }
                
                if (gyroscope == null)
                {
                    OnError?.Invoke("Gyroscope not available on this device");
                    return;
                }
                
                // Magnetometer is optional but preferred
                if (magnetometer == null)
                {
                    Debug.LogWarning("Magnetometer not available - VIO accuracy may be reduced");
                }
                
                // Set sampling rates
                accelerometer.samplingFrequency = samplingRate;
                gyroscope.samplingFrequency = samplingRate;
                if (magnetometer != null)
                    magnetometer.samplingFrequency = samplingRate;
                
                Debug.Log($"IMU sensors initialized - Sampling rate: {samplingRate}Hz");
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Failed to initialize IMU sensors: {e.Message}");
            }
        }
        
        private void InitializeDataStructures()
        {
            imuBuffer = new CircularBuffer<IMUReading>(bufferSize);
            calibration = IMUCalibration.Default;
            
            // Initialize calibration data collections
            calibrationAccelData = new List<Vector3>();
            calibrationGyroData = new List<Vector3>();
            calibrationMagData = new List<Vector3>();
            
            // Initialize filtering
            filteredAccel = Vector3.zero;
            filteredGyro = Vector3.zero;
            filteredMag = Vector3.zero;
        }
        
        private void Start()
        {
            if (enableAutoCalibration && !calibration.isCalibrated)
            {
                StartCalibration();
            }
            
            // Start high-frequency sampling
            InvokeRepeating(nameof(CollectIMUData), 0f, 1f / samplingRate);
        }
        
        private void CollectIMUData()
        {
            try
            {
                if (accelerometer == null || gyroscope == null) return;
                
                double timestamp = Time.realtimeSinceStartupAsDouble;
                
                // Read raw sensor data
                Vector3 rawAccel = accelerometer.acceleration.ReadValue();
                Vector3 rawGyro = gyroscope.angularVelocity.ReadValue();
                Vector3 rawMag = magnetometer?.magneticField.ReadValue() ?? Vector3.zero;
                
                // Apply calibration
                Vector3 calibratedAccel = ApplyCalibration(rawAccel, calibration.accelBias, calibration.accelScale);
                Vector3 calibratedGyro = ApplyCalibration(rawGyro, calibration.gyroBias, calibration.gyroScale);
                Vector3 calibratedMag = rawMag - calibration.magBias;
                
                // Apply filtering
                if (enableLowPassFilter)
                {
                    filteredAccel = LowPassFilter(filteredAccel, calibratedAccel, lowPassAlpha);
                    filteredGyro = LowPassFilter(filteredGyro, calibratedGyro, lowPassAlpha);
                    filteredMag = LowPassFilter(filteredMag, calibratedMag, lowPassAlpha);
                }
                else
                {
                    filteredAccel = calibratedAccel;
                    filteredGyro = calibratedGyro;
                    filteredMag = calibratedMag;
                }
                
                // Outlier detection
                if (enableOutlierDetection && IsOutlier(filteredAccel, filteredGyro))
                {
                    Debug.LogWarning($"IMU outlier detected at {timestamp}");
                    return;
                }
                
                // Create IMU reading
                IMUReading reading = new IMUReading(
                    timestamp,
                    filteredAccel,
                    filteredGyro,
                    filteredMag,
                    0f // Temperature not available through Unity Input System
                );
                
                // Store in buffer
                imuBuffer.Add(reading);
                
                // Update performance metrics
                UpdatePerformanceMetrics(timestamp);
                
                // Handle calibration data collection
                if (isCalibrating)
                {
                    CollectCalibrationData(rawAccel, rawGyro, rawMag);
                }
                
                // Notify listeners
                OnIMUDataReceived?.Invoke(reading);
                
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Error collecting IMU data: {e.Message}");
            }
        }
        
        private Vector3 ApplyCalibration(Vector3 raw, Vector3 bias, Matrix4x4 scale)
        {
            Vector3 corrected = raw - bias;
            Vector4 scaled = scale * new Vector4(corrected.x, corrected.y, corrected.z, 1f);
            return new Vector3(scaled.x, scaled.y, scaled.z);
        }
        
        private Vector3 LowPassFilter(Vector3 previous, Vector3 current, float alpha)
        {
            return previous * (1f - alpha) + current * alpha;
        }
        
        private bool IsOutlier(Vector3 accel, Vector3 gyro)
        {
            // Simple outlier detection based on magnitude
            float accelMagnitude = accel.magnitude;
            float gyroMagnitude = gyro.magnitude;
            
            // Typical ranges for mobile devices
            float maxAccel = 50f; // 5G acceleration
            float maxGyro = 10f;  // 10 rad/s angular velocity
            
            return accelMagnitude > maxAccel || gyroMagnitude > maxGyro;
        }
        
        private void UpdatePerformanceMetrics(double timestamp)
        {
            sampleCount++;
            float currentTime = (float)timestamp;
            
            if (lastSampleTime > 0)
            {
                float deltaTime = currentTime - lastSampleTime;
                actualSamplingRate = 1f / deltaTime;
            }
            
            lastSampleTime = currentTime;
            
            // Log performance every 1000 samples
            if (sampleCount % 1000 == 0)
            {
                Debug.Log($"IMU Performance: {actualSamplingRate:F1}Hz actual vs {samplingRate}Hz target");
            }
        }
        
        public void StartCalibration()
        {
            if (isCalibrating) return;
            
            isCalibrating = true;
            calibrationStartTime = Time.time;
            
            calibrationAccelData.Clear();
            calibrationGyroData.Clear();
            calibrationMagData.Clear();
            
            Debug.Log($"Starting IMU calibration for {calibrationDuration} seconds...");
            Debug.Log("Please keep the device stationary during calibration");
        }
        
        private void CollectCalibrationData(Vector3 accel, Vector3 gyro, Vector3 mag)
        {
            calibrationAccelData.Add(accel);
            calibrationGyroData.Add(gyro);
            calibrationMagData.Add(mag);
            
            // Check if calibration is complete
            if (Time.time - calibrationStartTime >= calibrationDuration)
            {
                CompleteCalibration();
            }
        }
        
        private void CompleteCalibration()
        {
            isCalibrating = false;
            
            try
            {
                // Calculate biases (average of collected data)
                calibration.accelBias = CalculateAverage(calibrationAccelData);
                calibration.gyroBias = CalculateAverage(calibrationGyroData);
                calibration.magBias = CalculateAverage(calibrationMagData);
                
                // For now, use identity matrices for scaling
                // In a more advanced implementation, you would calculate proper scaling factors
                calibration.accelScale = Matrix4x4.identity;
                calibration.gyroScale = Matrix4x4.identity;
                
                calibration.isCalibrated = true;
                
                Debug.Log("IMU calibration completed");
                Debug.Log($"Accel bias: {calibration.accelBias}");
                Debug.Log($"Gyro bias: {calibration.gyroBias}");
                Debug.Log($"Mag bias: {calibration.magBias}");
                
                OnCalibrationComplete?.Invoke(calibration);
            }
            catch (Exception e)
            {
                OnError?.Invoke($"Calibration failed: {e.Message}");
            }
        }
        
        private Vector3 CalculateAverage(List<Vector3> data)
        {
            if (data.Count == 0) return Vector3.zero;
            
            Vector3 sum = Vector3.zero;
            foreach (Vector3 sample in data)
            {
                sum += sample;
            }
            return sum / data.Count;
        }
        
        public IMUReading[] GetRecentReadings(int count)
        {
            return imuBuffer.GetLastN(count);
        }
        
        public IMUReading[] GetReadingsSince(double timestamp)
        {
            var readings = new List<IMUReading>();
            var allReadings = imuBuffer.GetAll();
            
            foreach (var reading in allReadings)
            {
                if (reading.timestamp > timestamp)
                {
                    readings.Add(reading);
                }
            }
            
            return readings.ToArray();
        }
        
        public IMUCalibration GetCalibration()
        {
            return calibration;
        }
        
        public void SetCalibration(IMUCalibration newCalibration)
        {
            calibration = newCalibration;
            Debug.Log("IMU calibration updated from external source");
        }
        
        public float GetActualSamplingRate()
        {
            return actualSamplingRate;
        }
        
        public bool IsSensorAvailable(string sensorType)
        {
            return sensorType.ToLower() switch
            {
                "accelerometer" => accelerometer != null,
                "gyroscope" => gyroscope != null,
                "magnetometer" => magnetometer != null,
                _ => false
            };
        }
        
        private void OnDestroy()
        {
            CancelInvokeRepeating();
        }
        
        private void OnApplicationPause(bool pauseStatus)
        {
            if (pauseStatus)
            {
                CancelInvokeRepeating();
            }
            else
            {
                InvokeRepeating(nameof(CollectIMUData), 0f, 1f / samplingRate);
            }
        }
    }
}