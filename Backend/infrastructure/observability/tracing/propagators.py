"""
VOXAR Enterprise Observability - Trace Propagators
B3 and Jaeger propagation for microservices compatibility
"""

import logging
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.propagators.jaeger import JaegerPropagator
from opentelemetry.propagators.composite import CompositePropagator

logger = logging.getLogger(__name__)

def setup_propagation():
    """Configure trace propagation for microservices"""
    
    try:
        # Use composite propagator for maximum compatibility
        propagator = CompositePropagator([
            B3MultiFormat(),
            JaegerPropagator()
        ])
        set_global_textmap(propagator)
        
        logger.info("Trace propagation configured with B3 and Jaeger propagators")
        
    except Exception as e:
        logger.error(f"Failed to setup propagation: {e}")

def get_composite_propagator() -> CompositePropagator:
    """Get the composite propagator for VOXAR services"""
    
    return CompositePropagator([
        B3MultiFormat(),
        JaegerPropagator()
    ])