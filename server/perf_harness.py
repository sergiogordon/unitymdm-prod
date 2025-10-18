"""
Performance diff harness for comparing legacy vs device_last_status queries.
Logs p95/p99 metrics to validate fast-read optimization.

Usage:
    Enable via environment variable: PERF_DIFF_ENABLED=true
    
This should run for 1 week to gather representative data, then disable.
"""

import time
import os
from functools import wraps
from typing import Callable, Any
from observability import structured_logger, metrics

PERF_DIFF_ENABLED = os.getenv("PERF_DIFF_ENABLED", "false").lower() == "true"

def compare_query_performance(legacy_fn: Callable, fast_fn: Callable, query_name: str):
    """
    Execute both legacy and fast queries, measure latency, log comparison.
    
    Args:
        legacy_fn: Function that executes legacy query
        fast_fn: Function that executes optimized query
        query_name: Name for logging/metrics (e.g., "list_devices", "offline_devices")
    
    Returns:
        Result from fast_fn (or legacy_fn if PERF_DIFF not enabled)
    """
    if not PERF_DIFF_ENABLED:
        # Performance comparison disabled, just run fast query
        return fast_fn()
    
    # Run legacy query and measure
    legacy_start = time.time()
    try:
        legacy_result = legacy_fn()
        legacy_latency_ms = (time.time() - legacy_start) * 1000
        legacy_error = None
    except Exception as e:
        legacy_latency_ms = (time.time() - legacy_start) * 1000
        legacy_error = str(e)
        legacy_result = None
    
    # Run fast query and measure
    fast_start = time.time()
    try:
        fast_result = fast_fn()
        fast_latency_ms = (time.time() - fast_start) * 1000
        fast_error = None
    except Exception as e:
        fast_latency_ms = (time.time() - fast_start) * 1000
        fast_error = str(e)
        fast_result = None
    
    # Log comparison
    speedup = legacy_latency_ms / fast_latency_ms if fast_latency_ms > 0 else 0
    
    structured_logger.log_event(
        "perf_diff.query_comparison",
        query_name=query_name,
        legacy_latency_ms=round(legacy_latency_ms, 2),
        fast_latency_ms=round(fast_latency_ms, 2),
        speedup=round(speedup, 2),
        legacy_error=legacy_error,
        fast_error=fast_error
    )
    
    # Record histograms for percentile calculations
    metrics.observe_histogram(f"query_latency_legacy_{query_name}_ms", legacy_latency_ms, {})
    metrics.observe_histogram(f"query_latency_fast_{query_name}_ms", fast_latency_ms, {})
    
    # Increment comparison counter
    metrics.inc_counter("perf_diff_comparisons_total", {"query_name": query_name})
    
    # Return fast result (or legacy if fast failed)
    return fast_result if fast_error is None else legacy_result


def with_perf_comparison(query_name: str):
    """
    Decorator to automatically compare legacy vs fast query performance.
    
    Usage:
        @with_perf_comparison("list_devices")
        def get_devices_dual(db, use_fast):
            if use_fast:
                return fast_query(db)
            else:
                return legacy_query(db)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not PERF_DIFF_ENABLED:
                # Just run the function normally with use_fast=True
                return func(*args, **kwargs, use_fast=True)
            
            # Run both and compare
            legacy_fn = lambda: func(*args, **kwargs, use_fast=False)
            fast_fn = lambda: func(*args, **kwargs, use_fast=True)
            
            return compare_query_performance(legacy_fn, fast_fn, query_name)
        
        return wrapper
    return decorator
