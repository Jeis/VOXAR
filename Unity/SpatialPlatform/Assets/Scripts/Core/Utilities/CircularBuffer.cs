using System;
using System.Collections;
using System.Collections.Generic;

namespace SpatialPlatform.Core.Utilities
{
    /// <summary>
    /// High-performance circular buffer implementation for real-time data
    /// Used for frame time tracking, sensor data smoothing, and performance metrics
    /// </summary>
    /// <typeparam name="T">The type of elements to store</typeparam>
    public class CircularBuffer<T> : IEnumerable<T>
    {
        private readonly T[] buffer;
        private int head;
        private int count;
        
        public int Capacity { get; }
        public int Count => count;
        public bool IsFull => count == Capacity;
        public bool IsEmpty => count == 0;
        
        /// <summary>
        /// Creates a new circular buffer with the specified capacity
        /// </summary>
        /// <param name="capacity">Maximum number of elements the buffer can hold</param>
        public CircularBuffer(int capacity)
        {
            if (capacity <= 0)
                throw new ArgumentException("Capacity must be positive", nameof(capacity));
                
            Capacity = capacity;
            buffer = new T[capacity];
            head = 0;
            count = 0;
        }
        
        /// <summary>
        /// Adds an item to the buffer. If full, overwrites the oldest item
        /// </summary>
        /// <param name="item">Item to add</param>
        public void Add(T item)
        {
            buffer[head] = item;
            head = (head + 1) % Capacity;
            
            if (count < Capacity)
            {
                count++;
            }
        }
        
        /// <summary>
        /// Gets the item at the specified index (0 is the oldest item)
        /// </summary>
        /// <param name="index">Index of the item to get</param>
        /// <returns>Item at the specified index</returns>
        public T this[int index]
        {
            get
            {
                if (index < 0 || index >= count)
                    throw new ArgumentOutOfRangeException(nameof(index));
                    
                int actualIndex = (head - count + index + Capacity) % Capacity;
                return buffer[actualIndex];
            }
        }
        
        /// <summary>
        /// Gets the most recently added item
        /// </summary>
        /// <returns>The newest item in the buffer</returns>
        public T GetNewest()
        {
            if (IsEmpty)
                throw new InvalidOperationException("Buffer is empty");
                
            int newestIndex = (head - 1 + Capacity) % Capacity;
            return buffer[newestIndex];
        }
        
        /// <summary>
        /// Gets the oldest item in the buffer
        /// </summary>
        /// <returns>The oldest item in the buffer</returns>
        public T GetOldest()
        {
            if (IsEmpty)
                throw new InvalidOperationException("Buffer is empty");
                
            int oldestIndex = (head - count + Capacity) % Capacity;
            return buffer[oldestIndex];
        }
        
        /// <summary>
        /// Clears all items from the buffer
        /// </summary>
        public void Clear()
        {
            Array.Clear(buffer, 0, buffer.Length);
            head = 0;
            count = 0;
        }
        
        /// <summary>
        /// Copies the buffer contents to an array in chronological order (oldest first)
        /// </summary>
        /// <returns>Array containing all buffer elements in chronological order</returns>
        public T[] ToArray()
        {
            T[] result = new T[count];
            
            for (int i = 0; i < count; i++)
            {
                result[i] = this[i];
            }
            
            return result;
        }
        
        /// <summary>
        /// Calculates the average of numeric values in the buffer
        /// </summary>
        /// <returns>Average value</returns>
        public double Average() where T : struct, IConvertible
        {
            if (IsEmpty)
                return 0.0;
                
            double sum = 0.0;
            for (int i = 0; i < count; i++)
            {
                sum += this[i].ToDouble(null);
            }
            
            return sum / count;
        }
        
        /// <summary>
        /// Finds the minimum value in the buffer
        /// </summary>
        /// <returns>Minimum value</returns>
        public T Min() where T : IComparable<T>
        {
            if (IsEmpty)
                throw new InvalidOperationException("Buffer is empty");
                
            T min = this[0];
            for (int i = 1; i < count; i++)
            {
                if (this[i].CompareTo(min) < 0)
                    min = this[i];
            }
            
            return min;
        }
        
        /// <summary>
        /// Finds the maximum value in the buffer
        /// </summary>
        /// <returns>Maximum value</returns>
        public T Max() where T : IComparable<T>
        {
            if (IsEmpty)
                throw new InvalidOperationException("Buffer is empty");
                
            T max = this[0];
            for (int i = 1; i < count; i++)
            {
                if (this[i].CompareTo(max) > 0)
                    max = this[i];
            }
            
            return max;
        }
        
        /// <summary>
        /// Calculates the standard deviation of numeric values in the buffer
        /// </summary>
        /// <returns>Standard deviation</returns>
        public double StandardDeviation() where T : struct, IConvertible
        {
            if (count < 2)
                return 0.0;
                
            double mean = Average();
            double sumSquaredDifferences = 0.0;
            
            for (int i = 0; i < count; i++)
            {
                double value = this[i].ToDouble(null);
                double difference = value - mean;
                sumSquaredDifferences += difference * difference;
            }
            
            return Math.Sqrt(sumSquaredDifferences / (count - 1));
        }
        
        /// <summary>
        /// Applies a smoothing function to the values in the buffer
        /// Useful for sensor data noise reduction
        /// </summary>
        /// <param name="smoothingFactor">Smoothing factor between 0 and 1</param>
        /// <returns>Smoothed value</returns>
        public T ExponentialSmooth(float smoothingFactor = 0.1f) where T : struct, IConvertible
        {
            if (IsEmpty)
                throw new InvalidOperationException("Buffer is empty");
                
            if (count == 1)
                return this[0];
                
            double smoothed = this[0].ToDouble(null);
            
            for (int i = 1; i < count; i++)
            {
                double current = this[i].ToDouble(null);
                smoothed = smoothingFactor * current + (1 - smoothingFactor) * smoothed;
            }
            
            return (T)Convert.ChangeType(smoothed, typeof(T));
        }
        
        /// <summary>
        /// Checks if the buffer contains a specific item
        /// </summary>
        /// <param name="item">Item to search for</param>
        /// <returns>True if the item is found, false otherwise</returns>
        public bool Contains(T item)
        {
            EqualityComparer<T> comparer = EqualityComparer<T>.Default;
            
            for (int i = 0; i < count; i++)
            {
                if (comparer.Equals(this[i], item))
                    return true;
            }
            
            return false;
        }
        
        /// <summary>
        /// Returns an enumerator that iterates through the buffer in chronological order
        /// </summary>
        /// <returns>An enumerator for the buffer</returns>
        public IEnumerator<T> GetEnumerator()
        {
            for (int i = 0; i < count; i++)
            {
                yield return this[i];
            }
        }
        
        IEnumerator IEnumerable.GetEnumerator()
        {
            return GetEnumerator();
        }
        
        /// <summary>
        /// Creates a string representation of the buffer contents
        /// </summary>
        /// <returns>String representation of the buffer</returns>
        public override string ToString()
        {
            if (IsEmpty)
                return "CircularBuffer<T> [Empty]";
                
            var items = new List<string>();
            for (int i = 0; i < Math.Min(count, 10); i++) // Show max 10 items
            {
                items.Add(this[i].ToString());
            }
            
            string content = string.Join(", ", items);
            if (count > 10)
                content += "...";
                
            return $"CircularBuffer<T> [{content}] ({count}/{Capacity})";
        }
    }
    
    /// <summary>
    /// Specialized circular buffer for float values with common AR/VR operations
    /// </summary>
    public class PerformanceBuffer : CircularBuffer<float>
    {
        public PerformanceBuffer(int capacity) : base(capacity) { }
        
        /// <summary>
        /// Calculates frames per second from frame time data
        /// </summary>
        /// <returns>Average FPS over the buffer period</returns>
        public float GetAverageFPS()
        {
            if (IsEmpty)
                return 0f;
                
            double averageFrameTime = Average();
            return averageFrameTime > 0 ? (float)(1.0 / averageFrameTime) : 0f;
        }
        
        /// <summary>
        /// Gets the 99th percentile frame time (useful for performance analysis)
        /// </summary>
        /// <returns>99th percentile frame time in seconds</returns>
        public float Get99thPercentile()
        {
            if (IsEmpty)
                return 0f;
                
            var sortedValues = ToArray();
            Array.Sort(sortedValues);
            
            int index = Mathf.RoundToInt((Count - 1) * 0.99f);
            return sortedValues[index];
        }
        
        /// <summary>
        /// Checks if performance is stable (low variation in frame times)
        /// </summary>
        /// <param name="maxStdDev">Maximum acceptable standard deviation</param>
        /// <returns>True if performance is stable</returns>
        public bool IsPerformanceStable(float maxStdDev = 0.005f)
        {
            if (Count < Capacity / 2) // Need at least half the buffer filled
                return false;
                
            return StandardDeviation() <= maxStdDev;
        }
    }
}