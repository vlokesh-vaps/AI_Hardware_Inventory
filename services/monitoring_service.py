"""
Monitoring Service for Hardware Inventory (Pipeline B).
Coordinates target discovery, live metric normalization, caching, health classification,
and historical time-series retrieval directly from Prometheus.
"""
import re
import time
from typing import Dict, Any, List, Optional, Tuple

from config import (
    CPU_WARNING_PERCENT,
    CPU_CRITICAL_PERCENT,
    MEMORY_WARNING_PERCENT,
    MEMORY_CRITICAL_PERCENT,
    DISK_WARNING_PERCENT,
    DISK_CRITICAL_PERCENT,
    MONITORED_SERVICES,
    MONITORED_PROCESSES,
    MONITORING_CACHE_TTL_SECONDS,
    monitoring_logger
)
from services.prometheus_client import (
    PrometheusClient,
    PrometheusClientError,
    PrometheusConnectionError,
    PrometheusTimeoutError
)


class MonitoringService:
    """
    High-level business service for live Windows monitoring via Prometheus.
    Includes in-memory TTL caching and strict input validation.
    """

    INSTANCE_REGEX = re.compile(r"^[0-9a-zA-Z\.\-_]+:\d+$")

    def __init__(self, client: Optional[PrometheusClient] = None, cache_ttl: Optional[int] = None):
        self.client = client or PrometheusClient()
        self.cache_ttl = cache_ttl if cache_ttl is not None else MONITORING_CACHE_TTL_SECONDS

        # In-memory caches: {cache_key: (timestamp, data)}
        self._targets_cache: Optional[Tuple[float, List[Dict[str, Any]]]] = None
        self._metrics_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}

    @classmethod
    def validate_instance(cls, instance: str) -> bool:
        """Validates instance string format to guard against PromQL injection."""
        return bool(cls.INSTANCE_REGEX.match(instance.strip()))

    @staticmethod
    def _format_uptime(seconds: Optional[float]) -> str:
        """Converts uptime in seconds to a human-readable display string."""
        if seconds is None or seconds < 0:
            return "N/A"
        total_sec = int(seconds)
        days = total_sec // 86400
        hours = (total_sec % 86400) // 3600
        minutes = (total_sec % 3600) // 60
        sec = total_sec % 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0 or days > 0:
            parts.append(f"{hours:02d}h")
        parts.append(f"{minutes:02d}m")
        if days == 0 and hours == 0:
            parts.append(f"{sec:02d}s")
        return " ".join(parts)

    def get_targets(self, bypass_cache: bool = False) -> List[Dict[str, Any]]:
        """
        Dynamically discovers Windows targets from Prometheus using up{job="windows"}.
        """
        now = time.time()
        if not bypass_cache and self._targets_cache:
            cache_time, data = self._targets_cache
            if (now - cache_time) < self.cache_ttl:
                return data

        promql = 'up{job="windows"}'
        result = self.client.query(promql)
        raw_results = result.get("data", {}).get("result", [])

        targets = []
        for item in raw_results:
            metric = item.get("metric", {})
            value_pair = item.get("value", [None, "0"])
            val_str = str(value_pair[1]) if len(value_pair) > 1 else "0"

            instance = metric.get("instance", "unknown")
            name = metric.get("name") or metric.get("instance", "").split(":")[0] or "Unknown"
            job = metric.get("job", "windows")
            is_up = val_str == "1"

            targets.append({
                "name": name,
                "instance": instance,
                "job": job,
                "online": is_up
            })

        # Sort alphabetically by target name
        targets.sort(key=lambda t: t["name"].lower())
        self._targets_cache = (now, targets)
        return targets

    def get_target_by_instance(self, instance: str) -> Optional[Dict[str, Any]]:
        """Finds target discovery metadata for a specific instance."""
        targets = self.get_targets()
        for t in targets:
            if t["instance"] == instance:
                return t
        return None

    def get_current_metrics(self, instance: str, bypass_cache: bool = False) -> Dict[str, Any]:
        """
        Retrieves and normalizes live metrics for a specific Windows instance.
        """
        instance = instance.strip()
        if not self.validate_instance(instance):
            raise ValueError(f"Invalid instance format: '{instance}'. Expected host:port.")

        now = time.time()
        if not bypass_cache and instance in self._metrics_cache:
            cache_time, cached_data = self._metrics_cache[instance]
            if (now - cache_time) < self.cache_ttl:
                return cached_data

        target = self.get_target_by_instance(instance)
        target_name = target["name"] if target else instance.split(":")[0]
        is_online = target["online"] if target else False

        # If target is explicitly offline (up == 0) or unmonitored:
        if target and not is_online:
            offline_payload = {
                "name": target_name,
                "instance": instance,
                "online": False,
                "status": "OFFLINE",
                "status_detail": "Monitoring unreachable / Exporter offline",
                "metrics": {
                    "cpu_percent": None,
                    "memory_percent": None,
                    "memory_available_bytes": None,
                    "memory_total_bytes": None,
                    "disk": [],
                    "disk_percent": None,
                    "disk_io": None,
                    "network": None,
                    "uptime_seconds": None,
                    "uptime_display": "N/A",
                    "services": [],
                    "processes": None,
                    "temperature": None
                },
                "timestamp": int(now)
            }
            self._metrics_cache[instance] = (now, offline_payload)
            return offline_payload

        # Target is online - query live metrics
        metrics: Dict[str, Any] = {
            "cpu_percent": None,
            "memory_percent": None,
            "memory_available_bytes": None,
            "memory_total_bytes": None,
            "disk": [],
            "disk_percent": None,
            "disk_io": {
                "read_bytes_sec": None,
                "write_bytes_sec": None,
                "read_ops_sec": None,
                "write_ops_sec": None,
                "requests_queued": None
            },
            "network": {
                "receive_bytes_sec": None,
                "send_bytes_sec": None,
                "interfaces": []
            },
            "uptime_seconds": None,
            "uptime_display": "N/A",
            "services": [],
            "processes": {
                "total_count": None,
                "monitored": []
            },
            "temperature": None
        }

        # 1. CPU Usage %
        try:
            cpu_q = f'100 - (avg by (instance) (rate(windows_cpu_time_total{{mode="idle", instance="{instance}"}}[5m])) * 100)'
            cpu_res = self.client.query(cpu_q).get("data", {}).get("result", [])
            if cpu_res and len(cpu_res[0].get("value", [])) > 1:
                metrics["cpu_percent"] = max(0.0, min(100.0, round(float(cpu_res[0]["value"][1]), 2)))
        except Exception as e:
            monitoring_logger.warning(f"Error querying CPU for {instance}: {e}")

        # 2. Physical Memory Usage %
        try:
            total_mem_q = f'windows_cs_physical_memory_bytes{{instance="{instance}"}}'
            free_mem_q = f'windows_os_physical_memory_free_bytes{{instance="{instance}"}}'

            total_res = self.client.query(total_mem_q).get("data", {}).get("result", [])
            free_res = self.client.query(free_mem_q).get("data", {}).get("result", [])

            if not free_res:
                # Fallback to windows_memory_available_bytes if free_bytes is absent
                avail_q = f'windows_memory_available_bytes{{instance="{instance}"}}'
                free_res = self.client.query(avail_q).get("data", {}).get("result", [])

            if total_res and free_res:
                total_val = float(total_res[0]["value"][1])
                free_val = float(free_res[0]["value"][1])
                metrics["memory_total_bytes"] = int(total_val)
                metrics["memory_available_bytes"] = int(free_val)
                if total_val > 0:
                    metrics["memory_percent"] = max(0.0, min(100.0, round(100.0 * (1.0 - (free_val / total_val)), 2)))
        except Exception as e:
            monitoring_logger.warning(f"Error querying Memory for {instance}: {e}")

        # 3. Logical Disk Usage (per drive)
        try:
            disk_size_q = f'windows_logical_disk_size_bytes{{instance="{instance}"}}'
            disk_free_q = f'windows_logical_disk_free_bytes{{instance="{instance}"}}'

            size_res = self.client.query(disk_size_q).get("data", {}).get("result", [])
            free_res = self.client.query(disk_free_q).get("data", {}).get("result", [])

            size_map = {}
            for item in size_res:
                vol = item.get("metric", {}).get("volume", "")
                if vol and len(item.get("value", [])) > 1:
                    size_map[vol] = float(item["value"][1])

            free_map = {}
            for item in free_res:
                vol = item.get("metric", {}).get("volume", "")
                if vol and len(item.get("value", [])) > 1:
                    free_map[vol] = float(item["value"][1])

            disk_list = []
            max_disk_percent = None

            # Sort volumes (e.g. C:, D:, E:)
            for vol in sorted(size_map.keys()):
                total_b = size_map[vol]
                free_b = free_map.get(vol, 0.0)
                if total_b > 0:
                    used_pct = max(0.0, min(100.0, round(100.0 * (1.0 - (free_b / total_b)), 2)))
                    disk_list.append({
                        "drive": vol,
                        "total_bytes": int(total_b),
                        "free_bytes": int(free_b),
                        "used_percent": used_pct
                    })
                    if max_disk_percent is None or used_pct > max_disk_percent:
                        max_disk_percent = used_pct

            metrics["disk"] = disk_list
            metrics["disk_percent"] = max_disk_percent
        except Exception as e:
            monitoring_logger.warning(f"Error querying Disk for {instance}: {e}")

        # 4. Disk I/O Rates
        try:
            r_bytes_q = f'sum(rate(windows_logical_disk_read_bytes_total{{instance="{instance}"}}[5m]))'
            w_bytes_q = f'sum(rate(windows_logical_disk_write_bytes_total{{instance="{instance}"}}[5m]))'
            r_ops_q = f'sum(rate(windows_logical_disk_reads_total{{instance="{instance}"}}[5m]))'
            w_ops_q = f'sum(rate(windows_logical_disk_writes_total{{instance="{instance}"}}[5m]))'
            q_req_q = f'sum(windows_logical_disk_requests_queued{{instance="{instance}"}})'

            r_b_res = self.client.query(r_bytes_q).get("data", {}).get("result", [])
            w_b_res = self.client.query(w_bytes_q).get("data", {}).get("result", [])
            r_o_res = self.client.query(r_ops_q).get("data", {}).get("result", [])
            w_o_res = self.client.query(w_ops_q).get("data", {}).get("result", [])
            q_res = self.client.query(q_req_q).get("data", {}).get("result", [])

            metrics["disk_io"]["read_bytes_sec"] = round(float(r_b_res[0]["value"][1]), 2) if r_b_res else None
            metrics["disk_io"]["write_bytes_sec"] = round(float(w_b_res[0]["value"][1]), 2) if w_b_res else None
            metrics["disk_io"]["read_ops_sec"] = round(float(r_o_res[0]["value"][1]), 2) if r_o_res else None
            metrics["disk_io"]["write_ops_sec"] = round(float(w_o_res[0]["value"][1]), 2) if w_o_res else None
            metrics["disk_io"]["requests_queued"] = round(float(q_res[0]["value"][1]), 2) if q_res else None
        except Exception as e:
            monitoring_logger.warning(f"Error querying Disk I/O for {instance}: {e}")

        # 5. Network Traffic
        try:
            rx_q = f'rate(windows_net_bytes_received_total{{instance="{instance}"}}[5m])'
            tx_q = f'rate(windows_net_bytes_sent_total{{instance="{instance}"}}[5m])'

            rx_res = self.client.query(rx_q).get("data", {}).get("result", [])
            tx_res = self.client.query(tx_q).get("data", {}).get("result", [])

            total_rx = 0.0
            total_tx = 0.0
            nic_map = {}

            for item in rx_res:
                nic = item.get("metric", {}).get("nic", "default")
                val = float(item["value"][1])
                total_rx += val
                nic_map.setdefault(nic, {})["receive_bytes_sec"] = round(val, 2)

            for item in tx_res:
                nic = item.get("metric", {}).get("nic", "default")
                val = float(item["value"][1])
                total_tx += val
                nic_map.setdefault(nic, {})["send_bytes_sec"] = round(val, 2)

            metrics["network"]["receive_bytes_sec"] = round(total_rx, 2) if rx_res else None
            metrics["network"]["send_bytes_sec"] = round(total_tx, 2) if tx_res else None
            metrics["network"]["interfaces"] = [
                {"nic": nic, **stats} for nic, stats in sorted(nic_map.items())
            ]
        except Exception as e:
            monitoring_logger.warning(f"Error querying Network for {instance}: {e}")

        # 6. System Uptime
        try:
            uptime_q = f'time() - windows_system_system_up_time{{instance="{instance}"}}'
            uptime_res = self.client.query(uptime_q).get("data", {}).get("result", [])
            if uptime_res and len(uptime_res[0].get("value", [])) > 1:
                secs = max(0.0, float(uptime_res[0]["value"][1]))
                metrics["uptime_seconds"] = int(secs)
                metrics["uptime_display"] = self._format_uptime(secs)
        except Exception as e:
            monitoring_logger.warning(f"Error querying Uptime for {instance}: {e}")

        # 7. Monitored Services State
        try:
            # Query active service states (state=1)
            # Resilient to both exported_name and original name labels
            pattern = "|".join(MONITORED_SERVICES)
            svc_q = f'windows_service_state{{instance="{instance}", exported_name=~"(?i){pattern}"}} == 1'
            svc_res = self.client.query(svc_q).get("data", {}).get("result", [])

            if not svc_res:
                # Fallback to name label if exported_name not found
                svc_fallback_q = f'windows_service_state{{instance="{instance}", name=~"(?i){pattern}"}} == 1'
                svc_res = self.client.query(svc_fallback_q).get("data", {}).get("result", [])

            found_services = {}
            for item in svc_res:
                metric = item.get("metric", {})
                s_name = metric.get("exported_name") or metric.get("name")
                state = metric.get("state", "unknown")
                if s_name:
                    found_services[s_name.lower()] = state

            service_status_list = []
            for svc in MONITORED_SERVICES:
                current_state = found_services.get(svc.lower(), "not found / stopped")
                service_status_list.append({
                    "service": svc,
                    "status": current_state
                })
            metrics["services"] = service_status_list
        except Exception as e:
            monitoring_logger.warning(f"Error querying Services for {instance}: {e}")

        # 8. Processes Count & Configured Process Monitoring
        try:
            proc_q = f'windows_os_processes{{instance="{instance}"}}'
            proc_res = self.client.query(proc_q).get("data", {}).get("result", [])
            if proc_res and len(proc_res[0].get("value", [])) > 1:
                metrics["processes"]["total_count"] = int(float(proc_res[0]["value"][1]))
            metrics["processes"]["monitored"] = [
                {"process": p, "status": "monitored"} for p in MONITORED_PROCESSES
            ]
        except Exception as e:
            monitoring_logger.warning(f"Error querying Processes for {instance}: {e}")

        # 9. Optional Temperature
        # Temperature is null by default as verified against this Prometheus exporter.
        metrics["temperature"] = None

        # 10. Centralized Health Status Evaluation
        status = "ONLINE"
        status_detail = "Operating normally"

        cpu_p = metrics["cpu_percent"]
        mem_p = metrics["memory_percent"]
        disk_p = metrics["disk_percent"]

        if (
            (cpu_p is not None and cpu_p >= CPU_CRITICAL_PERCENT) or
            (mem_p is not None and mem_p >= MEMORY_CRITICAL_PERCENT) or
            (disk_p is not None and disk_p >= DISK_CRITICAL_PERCENT)
        ):
            status = "CRITICAL"
            status_detail = "Critical resource threshold exceeded"
        elif (
            (cpu_p is not None and cpu_p >= CPU_WARNING_PERCENT) or
            (mem_p is not None and mem_p >= MEMORY_WARNING_PERCENT) or
            (disk_p is not None and disk_p >= DISK_WARNING_PERCENT)
        ):
            status = "WARNING"
            status_detail = "Resource utilization warning threshold exceeded"

        response_data = {
            "name": target_name,
            "instance": instance,
            "online": True,
            "status": status,
            "status_detail": status_detail,
            "metrics": metrics,
            "timestamp": int(now)
        }

        self._metrics_cache[instance] = (now, response_data)
        return response_data

    def get_historical_metrics(
        self,
        instance: str,
        metric_name: str = "cpu",
        time_range: str = "1h",
        step: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieves historical time-series metric data using query_range.
        Supported metrics: cpu, memory, disk_io, network.
        """
        instance = instance.strip()
        if not self.validate_instance(instance):
            raise ValueError(f"Invalid instance format: '{instance}'.")

        range_seconds_map = {
            "30m": 1800,
            "1h": 3600,
            "3h": 10800,
            "6h": 21600,
            "12h": 43200,
            "24h": 86400,
            "7d": 604800
        }

        duration_sec = range_seconds_map.get(time_range.lower(), 3600)
        end_time = time.time()
        start_time = end_time - duration_sec

        # Determine reasonable step if not explicitly provided
        if not step:
            if duration_sec <= 3600:
                step = "30s"
            elif duration_sec <= 21600:
                step = "120s"
            elif duration_sec <= 86400:
                step = "300s"
            else:
                step = "1800s"

        promql_map = {
            "cpu": f'100 - (avg by (instance) (rate(windows_cpu_time_total{{mode="idle", instance="{instance}"}}[5m])) * 100)',
            "memory": f'100 * (1 - windows_os_physical_memory_free_bytes{{instance="{instance}"}} / windows_cs_physical_memory_bytes{{instance="{instance}"}})',
            "disk_read": f'sum(rate(windows_logical_disk_read_bytes_total{{instance="{instance}"}}[5m]))',
            "disk_write": f'sum(rate(windows_logical_disk_write_bytes_total{{instance="{instance}"}}[5m]))',
            "network_rx": f'sum(rate(windows_net_bytes_received_total{{instance="{instance}"}}[5m]))',
            "network_tx": f'sum(rate(windows_net_bytes_sent_total{{instance="{instance}"}}[5m]))'
        }

        promql = promql_map.get(metric_name.lower())
        if not promql:
            raise ValueError(
                f"Unsupported metric '{metric_name}'. Allowed: {list(promql_map.keys())}"
            )

        prom_resp = self.client.query_range(promql, start=start_time, end=end_time, step=step)
        data_results = prom_resp.get("data", {}).get("result", [])

        data_points = []
        if data_results:
            raw_values = data_results[0].get("values", [])
            for pt in raw_values:
                if len(pt) == 2:
                    ts = int(pt[0])
                    val = round(float(pt[1]), 2)
                    data_points.append({"timestamp": ts, "value": val})

        return {
            "instance": instance,
            "metric": metric_name,
            "range": time_range,
            "step": step,
            "start": int(start_time),
            "end": int(end_time),
            "points_count": len(data_points),
            "data_points": data_points
        }

    def link_asset_to_target(self, asset: Dict[str, Any], targets: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Associates an existing static asset with a Prometheus monitoring target.
        Matches by primary IP, all IP addresses, or computer name.
        """
        asset_info = asset.get("asset", {})
        comp_name = asset_info.get("computer_name", "").strip().lower()
        ip_addr = asset_info.get("ip_address", "").strip()
        all_ips = [ip.strip() for ip in asset_info.get("all_ip_addresses", "").split(",") if ip.strip()]

        for t in targets:
            inst_ip = t["instance"].split(":")[0].strip()
            target_name = t["name"].strip().lower()

            # Match by primary IP
            if ip_addr and inst_ip == ip_addr:
                return t

            # Match by any IP
            if inst_ip in all_ips:
                return t

            # Match by computer name
            if comp_name and (target_name == comp_name or comp_name in target_name):
                return t

        return None
