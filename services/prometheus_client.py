"""
Reusable Prometheus HTTP API Client.
Executes instant and range PromQL queries with timeout handling, error normalization,
and structured logging.
"""
import json
import time
import urllib.parse
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from config import PROMETHEUS_URL, PROMETHEUS_TIMEOUT, monitoring_logger


class PrometheusClientError(Exception):
    """Base exception for Prometheus client errors."""
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message
            }
        }


class PrometheusConnectionError(PrometheusClientError):
    """Raised when Prometheus server is unreachable or connection fails."""
    def __init__(self, message: str = "Unable to connect to Prometheus server"):
        super().__init__("PROMETHEUS_UNAVAILABLE", message, status_code=503)


class PrometheusTimeoutError(PrometheusClientError):
    """Raised when Prometheus request times out."""
    def __init__(self, message: str = "Prometheus request timed out"):
        super().__init__("PROMETHEUS_TIMEOUT", message, status_code=504)


class PrometheusQueryError(PrometheusClientError):
    """Raised when Prometheus returns a query execution error."""
    def __init__(self, message: str, code: str = "PROMETHEUS_QUERY_ERROR", status_code: int = 400):
        super().__init__(code, message, status_code=status_code)


class PrometheusClient:
    """
    Dedicated client for communicating directly with Prometheus HTTP API v1.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        self.base_url = (base_url or PROMETHEUS_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else PROMETHEUS_TIMEOUT

    def _execute_http(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes an HTTP GET request to the specified Prometheus API endpoint.
        """
        query_string = urllib.parse.urlencode(params)
        url = f"{self.base_url}/api/v1/{endpoint}?{query_string}"
        start_time = time.time()
        promql_summary = params.get("query", "")

        # Truncate logged query if excessively long
        logged_query = promql_summary[:120] + "..." if len(promql_summary) > 120 else promql_summary

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "HardwareInventory-PrometheusClient/1.0",
                "Accept": "application/json"
            }
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                status_code = resp.status
                raw_data = resp.read().decode("utf-8")

            duration_ms = round((time.time() - start_time) * 1000, 2)

            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError as jde:
                monitoring_logger.error(
                    f"Invalid JSON from Prometheus [{url}]: {jde} (Duration: {duration_ms}ms)"
                )
                raise PrometheusClientError("INVALID_RESPONSE", "Prometheus returned invalid non-JSON payload")

            if data.get("status") != "success":
                err_type = data.get("errorType", "UNKNOWN")
                err_msg = data.get("error", "Prometheus query did not succeed")
                monitoring_logger.warning(
                    f"Prometheus query failure [{err_type}]: {err_msg} for query: {logged_query}"
                )
                raise PrometheusQueryError(f"{err_type}: {err_msg}")

            monitoring_logger.info(
                f"Prometheus GET {endpoint} SUCCESS ({duration_ms}ms) query: {logged_query}"
            )
            return data

        except urllib.error.HTTPError as he:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            err_body = ""
            try:
                err_body = he.read().decode("utf-8")
                parsed = json.loads(err_body)
                err_msg = parsed.get("error", str(he))
            except Exception:
                err_msg = f"HTTP {he.code}: {he.reason}"

            monitoring_logger.error(
                f"Prometheus HTTP Error {he.code} ({duration_ms}ms) for query: {logged_query} -> {err_msg}"
            )
            if he.code in (400, 422):
                raise PrometheusQueryError(f"Bad PromQL request: {err_msg}", code="INVALID_QUERY", status_code=400)
            elif he.code == 504:
                raise PrometheusTimeoutError("Prometheus execution timeout")
            else:
                raise PrometheusClientError("PROMETHEUS_HTTP_ERROR", f"Prometheus HTTP error {he.code}: {err_msg}", status_code=he.code)

        except urllib.error.URLError as ue:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            reason_str = str(ue.reason).lower()
            monitoring_logger.error(
                f"Prometheus Connection Error ({duration_ms}ms) to {self.base_url}: {ue.reason}"
            )
            if "timed out" in reason_str or "timeout" in reason_str:
                raise PrometheusTimeoutError(f"Connection to Prometheus timed out after {self.timeout}s")
            raise PrometheusConnectionError(f"Unable to reach Prometheus server at {self.base_url}")

        except (TimeoutError, TimeoutException) if "TimeoutException" in globals() else TimeoutError:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            monitoring_logger.error(f"Prometheus Request Timeout ({duration_ms}ms) after {self.timeout}s")
            raise PrometheusTimeoutError(f"Request to Prometheus timed out after {self.timeout}s")

    def query(self, promql: str, timestamp: Optional[float] = None) -> Dict[str, Any]:
        """
        Executes an instant PromQL query (GET /api/v1/query).
        """
        params = {"query": promql}
        if timestamp is not None:
            params["time"] = timestamp
        return self._execute_http("query", params)

    def query_range(
        self,
        promql: str,
        start: float,
        end: float,
        step: str = "60s"
    ) -> Dict[str, Any]:
        """
        Executes a range PromQL query (GET /api/v1/query_range).
        """
        params = {
            "query": promql,
            "start": start,
            "end": end,
            "step": step
        }
        return self._execute_http("query_range", params)
