-- Spatial Platform Database Initialization
-- Runs automatically when PostgreSQL container starts

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "postgis";
CREATE EXTENSION IF NOT EXISTS "postgis_topology";

-- Create core tables
CREATE TABLE IF NOT EXISTS reconstruction_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    location_id VARCHAR(255),
    center_lat FLOAT,
    center_lng FLOAT,
    progress_percentage FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}',
    error_message TEXT,
    warnings TEXT[]
);

CREATE TABLE IF NOT EXISTS spatial_maps (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    map_id VARCHAR(255) UNIQUE NOT NULL,
    location_id VARCHAR(255),
    name VARCHAR(255),
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    center_point GEOMETRY(POINT, 4326),
    bounding_box GEOMETRY(POLYGON, 4326),
    quality_score FLOAT,
    num_cameras INTEGER DEFAULT 0,
    num_points INTEGER DEFAULT 0,
    file_size_bytes BIGINT DEFAULT 0,
    metadata JSONB DEFAULT '{}',
    is_public BOOLEAN DEFAULT false
);

CREATE TABLE IF NOT EXISTS ar_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(255) UNIQUE NOT NULL,
    map_id VARCHAR(255) REFERENCES spatial_maps(map_id),
    user_id VARCHAR(255),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ended_at TIMESTAMP WITH TIME ZONE,
    device_info JSONB DEFAULT '{}',
    tracking_quality FLOAT,
    localization_success BOOLEAN DEFAULT false,
    pose_estimates JSONB DEFAULT '[]'
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_status ON reconstruction_jobs(status);
CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_location ON reconstruction_jobs(location_id);
CREATE INDEX IF NOT EXISTS idx_reconstruction_jobs_created ON reconstruction_jobs(created_at);

CREATE INDEX IF NOT EXISTS idx_spatial_maps_location ON spatial_maps(location_id);
CREATE INDEX IF NOT EXISTS idx_spatial_maps_created ON spatial_maps(created_at);
CREATE INDEX IF NOT EXISTS idx_spatial_maps_public ON spatial_maps(is_public);

CREATE INDEX IF NOT EXISTS idx_ar_sessions_map ON ar_sessions(map_id);
CREATE INDEX IF NOT EXISTS idx_ar_sessions_user ON ar_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_ar_sessions_started ON ar_sessions(started_at);

-- Spatial indexes
CREATE INDEX IF NOT EXISTS idx_spatial_maps_center_point ON spatial_maps USING GIST(center_point);
CREATE INDEX IF NOT EXISTS idx_spatial_maps_bounding_box ON spatial_maps USING GIST(bounding_box);

-- Insert sample data for development
INSERT INTO reconstruction_jobs (job_id, status, location_id, metadata) VALUES 
    ('sample-job-001', 'pending', 'dev-location-001', '{"description": "Sample reconstruction job", "image_count": 25}'),
    ('sample-job-002', 'completed', 'dev-location-002', '{"description": "Completed test job", "image_count": 18}')
ON CONFLICT (job_id) DO NOTHING;

INSERT INTO spatial_maps (map_id, location_id, name, center_point, quality_score, num_cameras, num_points) VALUES 
    ('sample-map-001', 'dev-location-001', 'Development Test Map', ST_SetSRID(ST_MakePoint(-122.4194, 37.7749), 4326), 0.85, 15, 2500),
    ('sample-map-002', 'dev-location-002', 'Office Building Map', ST_SetSRID(ST_MakePoint(-73.9857, 40.7484), 4326), 0.92, 22, 4800)
ON CONFLICT (map_id) DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO spatial_admin;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO spatial_admin;

-- Log completion
\echo 'Spatial Platform database initialized successfully!'
