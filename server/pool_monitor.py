"""
Connection Pool Monitoring and Alerting

Monitors connection pool saturation and raises alerts when thresholds are exceeded.
Safe to run frequently (every 1-5 minutes) for production monitoring.

Thresholds:
- WARN: >80% pool utilization
- CRITICAL: >95% pool utilization

Integration:
- Can be called via /ops/pool_health endpoint
- Can be scheduled via Replit's task scheduler
- Emits structured logs for alerting system integration
"""

from models import engine, SessionLocal
from observability import structured_logger, metrics
from typing import Dict, Any
import sys


def check_pool_health() -> Dict[str, Any]:
    """
    Check connection pool health and emit alerts if thresholds exceeded.
    
    Returns:
        {
            "status": "ok" | "warn" | "critical",
            "pool_size": int,
            "checked_out": int,
            "utilization_pct": float,
            "overflow": int,
            "total_capacity": int,
            "message": str
        }
    """
    pool = engine.pool
    
    # Extract pool stats
    pool_size = pool.size()
    checked_in = pool.checkedin()
    checked_out = pool.checkedout()
    overflow = pool.overflow()
    total_capacity = pool_size + overflow
    
    # Calculate utilization (checked_out / max_capacity)
    # Max capacity = pool_size + max_overflow (from engine config)
    max_overflow = engine.pool._max_overflow  # 50 from models.py
    max_capacity = pool_size + max_overflow
    utilization_pct = (checked_out / max_capacity) * 100 if max_capacity > 0 else 0
    
    # Determine status
    if utilization_pct >= 95:
        status = "critical"
        message = f"CRITICAL: Pool at {utilization_pct:.1f}% capacity ({checked_out}/{max_capacity})"
        level = "ERROR"
    elif utilization_pct >= 80:
        status = "warn"
        message = f"WARN: Pool at {utilization_pct:.1f}% capacity ({checked_out}/{max_capacity})"
        level = "WARN"
    else:
        status = "ok"
        message = f"Pool healthy: {utilization_pct:.1f}% capacity ({checked_out}/{max_capacity})"
        level = "INFO"
    
    # Emit structured log
    structured_logger.log_event(
        "pool.health_check",
        level=level,
        status=status,
        pool_size=pool_size,
        checked_in=checked_in,
        checked_out=checked_out,
        overflow=overflow,
        total_capacity=total_capacity,
        max_capacity=max_capacity,
        utilization_pct=round(utilization_pct, 2),
        message=message
    )
    
    # Update gauge metrics
    metrics.set_gauge("db_pool_utilization_pct", utilization_pct)
    
    return {
        "status": status,
        "pool_size": pool_size,
        "checked_in": checked_in,
        "checked_out": checked_out,
        "utilization_pct": round(utilization_pct, 2),
        "overflow": overflow,
        "total_capacity": total_capacity,
        "max_capacity": max_capacity,
        "message": message
    }


def check_postgres_connection_health() -> Dict[str, Any]:
    """
    Check Postgres connection usage vs max_connections.
    
    Returns connection health including current usage and headroom.
    """
    db = SessionLocal()
    try:
        from sqlalchemy import text
        
        result = db.execute(text("""
            SELECT 
                count(*) as current_connections,
                (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections
            FROM pg_stat_activity
        """)).fetchone()
        
        current_conns = result.current_connections
        max_conns = result.max_connections
        usage_pct = (current_conns / max_conns) * 100 if max_conns > 0 else 0
        
        structured_logger.log_event(
            "postgres.connection_check",
            current_connections=current_conns,
            max_connections=max_conns,
            usage_pct=round(usage_pct, 2),
            headroom=max_conns - current_conns
        )
        
        return {
            "current_connections": current_conns,
            "max_connections": max_conns,
            "usage_pct": round(usage_pct, 2),
            "headroom": max_conns - current_conns
        }
    finally:
        db.close()


if __name__ == "__main__":
    """
    CLI usage:
        python pool_monitor.py
    
    Exit codes:
        0 = OK
        1 = WARN
        2 = CRITICAL
    """
    pool_health = check_pool_health()
    pg_health = check_postgres_connection_health()
    
    print(f"\n=== Connection Pool Health ===")
    print(f"Status: {pool_health['status'].upper()}")
    print(f"Utilization: {pool_health['utilization_pct']}% ({pool_health['checked_out']}/{pool_health['max_capacity']})")
    print(f"Overflow: {pool_health['overflow']}")
    print(f"Message: {pool_health['message']}")
    
    print(f"\n=== Postgres Connection Health ===")
    print(f"Current: {pg_health['current_connections']}/{pg_health['max_connections']} ({pg_health['usage_pct']}%)")
    print(f"Headroom: {pg_health['headroom']} connections")
    
    # Exit with status code for monitoring
    if pool_health['status'] == 'critical':
        sys.exit(2)
    elif pool_health['status'] == 'warn':
        sys.exit(1)
    else:
        sys.exit(0)
