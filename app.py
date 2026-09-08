"""
Flask Application for Hardware Inventory Dashboard.
Provides web UI routes, REST API endpoints, and centralized request handling.
"""
from pathlib import Path
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    abort
)
from werkzeug.utils import secure_filename

from config import (
    SECRET_KEY,
    MAX_CONTENT_LENGTH,
    ALLOWED_EXTENSIONS,
    UPLOADS_DIR,
    app_logger,
    monitoring_logger,
    error_logger
)
from services.inventory_service import InventoryService
from services.monitoring_service import MonitoringService
from services.prometheus_client import PrometheusClientError

def create_app() -> Flask:
    """Application factory for Flask app."""
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

    inventory_service = InventoryService()
    monitoring_service = MonitoringService()

    def allowed_file(filename: str) -> bool:
        return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

    # -------------------------------------------------------------
    # WEB UI ROUTES
    # -------------------------------------------------------------

    @app.route("/")
    @app.route("/dashboard")
    def dashboard():
        """Main organization dashboard."""
        try:
            assets = inventory_service.get_assets()
            kpis = inventory_service.get_kpis()
            recent_changes = inventory_service.get_changes()[:6]
            storage_alerts = inventory_service.get_storage_alerts()

            # Map monitoring targets for asset table badges
            monitoring_map = {}
            try:
                targets = monitoring_service.get_targets()
                for a in assets:
                    t = monitoring_service.link_asset_to_target(a, targets)
                    c_name = a.get("asset", {}).get("computer_name")
                    if c_name and t:
                        monitoring_map[c_name] = t
            except Exception as e:
                monitoring_logger.warning(f"Failed to load monitoring map for dashboard: {e}")

            return render_template(
                "dashboard.html",
                assets=assets,
                kpis=kpis,
                recent_changes=recent_changes,
                storage_alerts=storage_alerts,
                monitoring_map=monitoring_map
            )
        except Exception as e:
            error_logger.exception("Error rendering dashboard")
            flash(f"Error loading dashboard: {str(e)}", "error")
            return render_template("dashboard.html", assets=[], kpis={}, recent_changes=[], storage_alerts=[], monitoring_map={})

    @app.route("/pc/<computer_name>")
    def pc_details(computer_name: str):
        """Detailed specification and health page for an individual PC."""
        asset_data = inventory_service.get_asset_by_name(computer_name) if hasattr(inventory_service, "get_asset_by_name") else inventory_service.get_latest_snapshot(computer_name)
        if not asset_data:
            flash(f"Computer '{computer_name}' not found in inventory.", "warning")
            return redirect(url_for("dashboard"))

        history = inventory_service.get_snapshot_history(computer_name)
        health = asset_data.get("health", {})

        # Find matching monitoring target if available
        monitoring_target = None
        try:
            targets = monitoring_service.get_targets()
            monitoring_target = monitoring_service.link_asset_to_target(asset_data, targets)
        except Exception as e:
            monitoring_logger.warning(f"Failed to fetch monitoring targets for pc_details: {e}")

        return render_template(
            "pc_details.html",
            asset=asset_data.get("asset", {}),
            os=asset_data.get("os", {}),
            cpu=asset_data.get("cpu", []),
            ram=asset_data.get("ram", []),
            total_ram_gb=asset_data.get("total_ram_gb", "N/A"),
            storage=asset_data.get("storage", []),
            drives=asset_data.get("drives", []),
            gpu=asset_data.get("gpu", []),
            monitors=asset_data.get("monitors", []),
            keyboards=asset_data.get("keyboards", []),
            mice=asset_data.get("mice", []),
            usb_devices=asset_data.get("usb_devices", []),
            network_adapters=asset_data.get("network_adapters", []),
            motherboard=asset_data.get("motherboard", {}),
            bios=asset_data.get("bios", {}),
            installed_software=asset_data.get("installed_software", []),
            software_count=asset_data.get("software_count", len(asset_data.get("installed_software", []))),
            health=health,
            history=history,
            monitoring_target=monitoring_target
        )

    @app.route("/monitoring")
    def monitoring_dashboard():
        """Live Hardware Monitoring Dashboard (Pipeline B)."""
        selected_target = request.args.get("instance", "").strip()
        selected_pc = request.args.get("pc", "").strip()

        targets = []
        try:
            targets = monitoring_service.get_targets()
        except Exception as e:
            monitoring_logger.warning(f"Failed to fetch monitoring targets for dashboard UI: {e}")
            flash(f"Prometheus monitoring status notice: {str(e)}", "warning")

        # Resolve selected target
        active_target = None
        if selected_target:
            for t in targets:
                if t["instance"] == selected_target:
                    active_target = t
                    break
        elif selected_pc:
            for t in targets:
                if t["name"].lower() == selected_pc.lower():
                    active_target = t
                    break

        if not active_target and targets:
            # Pick first online target, or first target
            online_targets = [t for t in targets if t.get("online")]
            active_target = online_targets[0] if online_targets else targets[0]

        return render_template(
            "monitoring.html",
            targets=targets,
            active_target=active_target
        )

    @app.route("/changes")
    def changes():
        """Hardware changes audit log with filtering."""
        comp_filter = request.args.get("computer", "").strip()
        comp_type_filter = request.args.get("component", "").strip()
        change_type_filter = request.args.get("change_type", "").strip()
        date_filter = request.args.get("date", "").strip()

        filters = {
            "computer_name": comp_filter,
            "component_type": comp_type_filter,
            "change_type": change_type_filter,
            "date": date_filter
        }

        changes_list = inventory_service.get_changes(filters)
        return render_template("changes.html", changes=changes_list, filters=filters)

    @app.route("/alerts")
    def alerts():
        """Storage capacity alerts and upgrade recommendations."""
        storage_alerts = inventory_service.get_storage_alerts()
        recommendations = inventory_service.get_upgrade_recommendations()
        return render_template("alerts.html", storage_alerts=storage_alerts, recommendations=recommendations)

    @app.route("/upload", methods=["GET"])
    def upload_page():
        """Upload interface for health check reports."""
        return render_template("upload.html")

    @app.route("/upload", methods=["POST"])
    def upload_files():
        """Processes one or multiple uploaded TXT files."""
        if "files" not in request.files:
            flash("No file part in upload request.", "error")
            return redirect(url_for("upload_page"))

        uploaded_files = request.files.getlist("files")
        if not uploaded_files or uploaded_files[0].filename == "":
            flash("No files selected for upload.", "warning")
            return redirect(url_for("upload_page"))

        success_count = 0
        duplicate_count = 0
        error_count = 0

        for file in uploaded_files:
            if not file or not file.filename:
                continue

            filename = secure_filename(file.filename)
            if not allowed_file(filename):
                flash(f"File '{filename}' rejected: Only .txt files are allowed.", "warning")
                error_count += 1
                continue

            try:
                # Read content safely
                content = file.read().decode("utf-8", errors="replace")
                if not content.strip():
                    flash(f"File '{filename}' is empty.", "error")
                    error_count += 1
                    continue

                # Save copy to uploads/
                temp_path = UPLOADS_DIR / filename
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(content)

                ok, msg, _ = inventory_service.process_report_file(temp_path, filename)
                if ok:
                    success_count += 1
                elif "duplicate" in msg.lower():
                    duplicate_count += 1
                    flash(msg, "warning")
                else:
                    error_count += 1
                    flash(msg, "error")

            except Exception as e:
                error_count += 1
                err = f"Failed to process '{filename}': {str(e)}"
                error_logger.exception(err)
                flash(err, "error")

        if success_count > 0:
            flash(f"Successfully processed {success_count} report(s).", "success")

        if duplicate_count > 0 and success_count == 0 and error_count == 0:
            flash(f"{duplicate_count} report(s) were recognized as existing duplicate snapshots.", "info")

        return redirect(url_for("dashboard"))

    @app.route("/import-dir", methods=["POST"])
    def import_directory():
        """Scans and imports reports from a directory on the local machine."""
        dir_path_str = request.form.get("dir_path", "C:\\healthcheck").strip()
        dir_path = Path(dir_path_str)

        if not dir_path.exists() or not dir_path.is_dir():
            flash(f"Directory '{dir_path_str}' does not exist or is not a directory.", "error")
            return redirect(url_for("upload_page"))

        txt_files = list(dir_path.glob("*.txt"))
        if not txt_files:
            flash(f"No .txt files found in directory '{dir_path_str}'.", "warning")
            return redirect(url_for("upload_page"))

        imported = 0
        duplicates = 0
        errors = 0

        for file_path in txt_files:
            try:
                ok, msg, _ = inventory_service.process_report_file(file_path, file_path.name)
                if ok:
                    imported += 1
                elif "duplicate" in msg.lower():
                    duplicates += 1
                else:
                    errors += 1
            except Exception as e:
                errors += 1
                error_logger.exception(f"Error scanning file {file_path}: {e}")

        flash(
            f"Directory scan finished: {imported} imported, {duplicates} duplicates skipped, {errors} errors.",
            "success" if imported > 0 else "info"
        )
        return redirect(url_for("dashboard"))

    # -------------------------------------------------------------
    # REST API ENDPOINTS
    # -------------------------------------------------------------

    @app.route("/api/assets", methods=["GET"])
    def api_assets():
        """Returns JSON list of all assets with latest specs and health."""
        assets = inventory_service.get_assets()
        return jsonify({"count": len(assets), "assets": assets})

    @app.route("/api/assets/<computer_name>", methods=["GET"])
    def api_asset_detail(computer_name: str):
        """Returns JSON for a specific computer and its snapshot history."""
        asset = inventory_service.get_latest_snapshot(computer_name)
        if not asset:
            return jsonify({"error": f"Computer '{computer_name}' not found"}), 404
        history = inventory_service.get_snapshot_history(computer_name)
        return jsonify({"asset": asset, "history": history})

    @app.route("/api/changes", methods=["GET"])
    def api_changes():
        """Returns JSON list of hardware changes with optional query filters."""
        filters = {
            "computer_name": request.args.get("computer", "").strip(),
            "component_type": request.args.get("component", "").strip(),
            "change_type": request.args.get("change_type", "").strip(),
            "date": request.args.get("date", "").strip()
        }
        changes_list = inventory_service.get_changes(filters)
        return jsonify({"count": len(changes_list), "changes": changes_list})

    @app.route("/api/alerts", methods=["GET"])
    def api_alerts():
        """Returns JSON list of storage alerts and upgrade recommendations."""
        storage_alerts = inventory_service.get_storage_alerts()
        recommendations = inventory_service.get_upgrade_recommendations()
        return jsonify({
            "storage_alerts": storage_alerts,
            "upgrade_recommendations": recommendations
        })

    @app.route("/api/upload", methods=["POST"])
    def api_upload():
        """API endpoint for automated report ingestion."""
        if "file" not in request.files and "files" not in request.files:
            return jsonify({"error": "No file uploaded in form-data"}), 400

        files = request.files.getlist("files") or [request.files["file"]]
        results = []

        for file in files:
            filename = secure_filename(file.filename)
            if not allowed_file(filename):
                results.append({"filename": filename, "success": False, "message": "Invalid file extension"})
                continue

            content = file.read().decode("utf-8", errors="replace")
            ok, msg, data = inventory_service.process_report_file(content, filename)
            results.append({
                "filename": filename,
                "success": ok,
                "message": msg,
                "computer_name": data.get("asset", {}).get("computer_name") if data else None
            })

        return jsonify({"processed": len(results), "results": results})

    # -------------------------------------------------------------
    # LIVE MONITORING REST API ENDPOINTS (Pipeline B)
    # -------------------------------------------------------------

    @app.route("/api/monitoring/targets", methods=["GET"])
    def api_monitoring_targets():
        """
        Discovers active and inactive Windows monitoring targets from Prometheus.
        Returns: { "data": [ { "name": ..., "instance": ..., "online": ... } ] }
        """
        try:
            bypass_cache = request.args.get("refresh", "").lower() in ("1", "true")
            targets = monitoring_service.get_targets(bypass_cache=bypass_cache)
            # Format normalized response
            data = [
                {
                    "name": t["name"],
                    "instance": t["instance"],
                    "job": t.get("job", "windows"),
                    "online": t["online"]
                }
                for t in targets
            ]
            return jsonify({"data": data, "count": len(data)})
        except PrometheusClientError as pce:
            return jsonify(pce.to_dict()), pce.status_code
        except Exception as e:
            monitoring_logger.exception("Unexpected error discovering monitoring targets")
            return jsonify({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to discover monitoring targets"
                }
            }), 500

    @app.route("/api/monitoring/<path:instance>/current", methods=["GET"])
    def api_monitoring_current(instance: str):
        """
        Returns normalized live metrics for a specific Windows machine.
        If the endpoint is offline (up=0), returns online=false without error.
        """
        instance = instance.strip()
        if not monitoring_service.validate_instance(instance):
            return jsonify({
                "error": {
                    "code": "INVALID_INSTANCE",
                    "message": f"Invalid instance format: '{instance}'. Expected host:port."
                }
            }), 400

        try:
            bypass_cache = request.args.get("refresh", "").lower() in ("1", "true")
            metrics_data = monitoring_service.get_current_metrics(instance, bypass_cache=bypass_cache)

            # Flatten network fields for backwards/convenience compatibility
            net_dict = metrics_data.get("metrics", {}).get("network") or {}
            metrics_obj = dict(metrics_data.get("metrics", {}))
            metrics_obj["network_receive_bytes_sec"] = net_dict.get("receive_bytes_sec")
            metrics_obj["network_send_bytes_sec"] = net_dict.get("send_bytes_sec")

            return jsonify({
                "name": metrics_data.get("name"),
                "instance": metrics_data.get("instance"),
                "online": metrics_data.get("online"),
                "status": metrics_data.get("status"),
                "status_detail": metrics_data.get("status_detail"),
                "metrics": metrics_obj,
                "timestamp": metrics_data.get("timestamp")
            })
        except PrometheusClientError as pce:
            return jsonify(pce.to_dict()), pce.status_code
        except ValueError as ve:
            return jsonify({"error": {"code": "INVALID_PARAMETER", "message": str(ve)}}), 400
        except Exception as e:
            monitoring_logger.exception(f"Unexpected error retrieving current metrics for {instance}")
            return jsonify({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to retrieve live monitoring metrics"
                }
            }), 500

    @app.route("/api/monitoring/<path:instance>/history", methods=["GET"])
    def api_monitoring_history(instance: str):
        """
        Returns historical time-series metric data from Prometheus /api/v1/query_range.
        Query params: metric (cpu, memory, disk_read, disk_write, network_rx, network_tx), range (1h, 6h, 24h), step.
        """
        instance = instance.strip()
        if not monitoring_service.validate_instance(instance):
            return jsonify({
                "error": {
                    "code": "INVALID_INSTANCE",
                    "message": f"Invalid instance format: '{instance}'. Expected host:port."
                }
            }), 400

        metric_name = request.args.get("metric", "cpu").strip().lower()
        time_range = request.args.get("range", "1h").strip()
        step = request.args.get("step")

        try:
            history_data = monitoring_service.get_historical_metrics(
                instance=instance,
                metric_name=metric_name,
                time_range=time_range,
                step=step
            )
            return jsonify(history_data)
        except PrometheusClientError as pce:
            return jsonify(pce.to_dict()), pce.status_code
        except ValueError as ve:
            return jsonify({"error": {"code": "INVALID_PARAMETER", "message": str(ve)}}), 400
        except Exception as e:
            monitoring_logger.exception(f"Unexpected error retrieving history for {instance}: {e}")
            return jsonify({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Failed to retrieve historical monitoring metrics"
                }
            }), 500

    # -------------------------------------------------------------
    # ERROR HANDLERS
    # -------------------------------------------------------------

    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Resource not found", "status_code": 404}), 404
        return render_template("base.html"), 404

    @app.errorhandler(500)
    def handle_500(e):
        error_logger.exception("Internal Server Error")
        if request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error", "status_code": 500}), 500
        return "Internal Server Error", 500

    return app

if __name__ == "__main__":
    application = create_app()
    app_logger.info("Starting Hardware Inventory web server on http://127.0.0.1:5000")
    application.run(host="0.0.0.0", port=5000, debug=True)
