import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from contextvars import ContextVar
from collections import defaultdict
from threading import Lock

request_id_var: ContextVar[Optional[str]] = ContextVar('request_id', default=None)

class StructuredLogger:
    """
    Structured JSON logger for observability.
    Emits log lines with consistent fields for all events.
    """
    
    def __init__(self, name: str = "mdm"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(handler)
    
    def _base_fields(self) -> Dict[str, Any]:
        """Common fields for all log events"""
        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "request_id": request_id_var.get(),
        }
    
    def log_event(
        self,
        event: str,
        level: str = "INFO",
        **fields
    ) -> None:
        """
        Log a structured event with additional fields.
        
        Args:
            event: Event name (e.g., "register.success", "heartbeat.ingest")
            level: Log level (INFO, WARN, ERROR)
            **fields: Additional event-specific fields
        """
        log_entry = self._base_fields()
        log_entry["level"] = level
        log_entry["event"] = event
        log_entry.update(fields)
        
        log_line = json.dumps(log_entry, default=str)
        
        if level == "ERROR":
            self.logger.error(log_line)
        elif level == "WARN":
            self.logger.warning(log_line)
        else:
            self.logger.info(log_line)


class MetricsCollector:
    """
    Lightweight in-memory metrics collector for Prometheus-compatible exposition.
    Tracks counters and histogram buckets with minimal overhead.
    """
    
    def __init__(self):
        self._lock = Lock()
        self._counters: Dict[str, Dict[tuple, int]] = defaultdict(lambda: defaultdict(int))
        self._histograms: Dict[str, Dict[tuple, list]] = defaultdict(lambda: defaultdict(list))
        
        self.latency_buckets = [5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000]
    
    def inc_counter(self, metric_name: str, labels: Optional[Dict[str, str]] = None, value: int = 1):
        """Increment a counter metric"""
        label_tuple = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._counters[metric_name][label_tuple] += value
    
    def observe_histogram(self, metric_name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a histogram observation"""
        label_tuple = tuple(sorted((labels or {}).items()))
        with self._lock:
            self._histograms[metric_name][label_tuple].append(value)
    
    def get_prometheus_text(self) -> str:
        """
        Generate Prometheus-compatible text format exposition.
        Returns metrics in plain text format.
        """
        lines = []
        
        with self._lock:
            for metric_name, label_data in sorted(self._counters.items()):
                lines.append(f"# TYPE {metric_name} counter")
                for label_tuple, count in sorted(label_data.items()):
                    if label_tuple:
                        label_str = ",".join(f'{k}="{v}"' for k, v in label_tuple)
                        lines.append(f"{metric_name}{{{label_str}}} {count}")
                    else:
                        lines.append(f"{metric_name} {count}")
            
            for metric_name, label_data in sorted(self._histograms.items()):
                lines.append(f"# TYPE {metric_name}_bucket histogram")
                for label_tuple, observations in sorted(label_data.items()):
                    label_dict = dict(label_tuple) if label_tuple else {}
                    
                    for bucket in self.latency_buckets:
                        count = sum(1 for obs in observations if obs <= bucket)
                        bucket_labels = {**label_dict, "le": str(bucket)}
                        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(bucket_labels.items()))
                        lines.append(f"{metric_name}_bucket{{{label_str}}} {count}")
                    
                    inf_labels = {**label_dict, "le": "+Inf"}
                    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(inf_labels.items()))
                    lines.append(f"{metric_name}_bucket{{{label_str}}} {len(observations)}")
                    
                    label_str_base = ",".join(f'{k}="{v}"' for k, v in sorted(label_dict.items())) if label_dict else ""
                    if label_str_base:
                        lines.append(f"{metric_name}_count{{{label_str_base}}} {len(observations)}")
                        if observations:
                            lines.append(f"{metric_name}_sum{{{label_str_base}}} {sum(observations)}")
                    else:
                        lines.append(f"{metric_name}_count {len(observations)}")
                        if observations:
                            lines.append(f"{metric_name}_sum {sum(observations)}")
        
        return "\n".join(lines) + "\n"


structured_logger = StructuredLogger()
metrics = MetricsCollector()
