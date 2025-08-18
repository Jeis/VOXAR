"""
VOXAR Enterprise Observability - Auto Instrumentation
Automatic instrumentation setup for common libraries and frameworks
"""

import logging

logger = logging.getLogger(__name__)

def setup_auto_instrumentation():
    """Setup automatic instrumentation for common libraries"""
    
    try:
        # FastAPI instrumentation
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor().instrument()
        logger.info("FastAPI auto-instrumentation configured")
        
        # Requests instrumentation
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        RequestsInstrumentor().instrument()
        logger.info("Requests auto-instrumentation configured")
        
        # PostgreSQL instrumentation
        try:
            from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
            Psycopg2Instrumentor().instrument()
            logger.info("PostgreSQL auto-instrumentation configured")
        except ImportError:
            logger.debug("Psycopg2 not available, skipping PostgreSQL instrumentation")
        
        # Redis instrumentation
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor
            RedisInstrumentor().instrument()
            logger.info("Redis auto-instrumentation configured")
        except ImportError:
            logger.debug("Redis not available, skipping Redis instrumentation")
        
        logger.info("Auto-instrumentation setup completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to setup auto-instrumentation: {e}")

def setup_custom_processors():
    """Setup custom span processors for AR-specific enrichment"""
    # Placeholder for custom processors
    # This would be implemented with custom processors
    # for adding AR session context, performance annotations, etc.
    pass