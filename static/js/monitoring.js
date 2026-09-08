/**
 * Hardware Inventory Live Monitoring - Vanilla JavaScript
 * Manages live telemetry polling, Chart.js time-series charts, auto-refresh scheduling,
 * and dynamic target switching.
 */

(function () {
    let currentInstance = '';
    let currentRange = '1h';
    let refreshIntervalSec = 10;
    let pollTimer = null;
    let isPolling = false;

    // Chart.js instances
    let chartCpu = null;
    let chartMemory = null;
    let chartNetwork = null;
    let chartDisk = null;

    document.addEventListener('DOMContentLoaded', () => {
        initTargetSelector();
        initRefreshControls();
        initRangeControls();
        initCharts();

        // Check if there is an active target selected
        const selector = document.getElementById('target-selector');
        if (selector && selector.value) {
            currentInstance = selector.value;
            loadTargetData(currentInstance, true);
        }

        startAutoRefresh();

        // Page Visibility API - stop polling if user switches tab to reduce Prometheus load
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                stopAutoRefresh();
            } else {
                startAutoRefresh();
                if (currentInstance) {
                    fetchCurrentMetrics(currentInstance);
                }
            }
        });
    });

    /**
     * Target dropdown selection handler
     */
    function initTargetSelector() {
        const selector = document.getElementById('target-selector');
        if (!selector) return;

        selector.addEventListener('change', () => {
            currentInstance = selector.value;
            if (currentInstance) {
                // Update URL parameter without full page reload
                const url = new URL(window.location);
                url.searchParams.set('instance', currentInstance);
                window.history.replaceState({}, '', url);

                loadTargetData(currentInstance, true);
            }
        });
    }

    /**
     * Auto-refresh dropdown & manual refresh button
     */
    function initRefreshControls() {
        const intervalSelect = document.getElementById('refresh-interval-select');
        const manualBtn = document.getElementById('btn-manual-refresh');

        if (intervalSelect) {
            intervalSelect.addEventListener('change', () => {
                refreshIntervalSec = parseInt(intervalSelect.value, 10);
                startAutoRefresh();
            });
        }

        if (manualBtn) {
            manualBtn.addEventListener('click', () => {
                if (currentInstance) {
                    manualBtn.classList.add('rotating');
                    fetchCurrentMetrics(currentInstance, true).finally(() => {
                        setTimeout(() => manualBtn.classList.remove('rotating'), 500);
                    });
                    fetchHistoricalMetrics(currentInstance);
                }
            });
        }
    }

    /**
     * Time-range filter buttons for historical charts
     */
    function initRangeControls() {
        const buttons = document.querySelectorAll('#chart-range-group .btn-filter');
        buttons.forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                buttons.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentRange = btn.getAttribute('data-range') || '1h';
                if (currentInstance) {
                    fetchHistoricalMetrics(currentInstance);
                }
            });
        });
    }

    /**
     * Start/Restart polling timer
     */
    function startAutoRefresh() {
        stopAutoRefresh();
        if (refreshIntervalSec > 0) {
            pollTimer = setInterval(() => {
                if (currentInstance && !document.hidden) {
                    fetchCurrentMetrics(currentInstance);
                }
            }, refreshIntervalSec * 1000);
        }
    }

    function stopAutoRefresh() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    /**
     * Load all telemetry for a given target
     */
    function loadTargetData(instance, reloadHistory = false) {
        document.getElementById('target-instance-display').textContent = instance;

        // Update static specs link
        const selector = document.getElementById('target-selector');
        const selectedOpt = selector ? selector.options[selector.selectedIndex] : null;
        const targetName = selectedOpt ? selectedOpt.getAttribute('data-name') : '';
        const specsLink = document.getElementById('link-static-specs');
        if (specsLink) {
            specsLink.href = targetName ? `/pc/${encodeURIComponent(targetName)}` : '/dashboard';
        }

        fetchCurrentMetrics(instance, false);
        if (reloadHistory) {
            fetchHistoricalMetrics(instance);
        }
    }

    /**
     * Fetch live normalized metrics from GET /api/monitoring/{instance}/current
     */
    async function fetchCurrentMetrics(instance, bypassCache = false) {
        if (isPolling) return;
        isPolling = true;

        try {
            const url = `/api/monitoring/${encodeURIComponent(instance)}/current${bypassCache ? '?refresh=1' : ''}`;
            const res = await fetch(url);
            const data = await res.json();

            if (!res.ok) {
                handleFetchError(data.error || { message: 'Failed to fetch metrics' });
                return;
            }

            renderCurrentMetrics(data);
        } catch (err) {
            console.error('Error polling current metrics:', err);
            handleFetchError({ message: 'Network connection to API failed' });
        } finally {
            isPolling = false;
        }
    }

    /**
     * Render live metrics into dashboard UI
     */
    function renderCurrentMetrics(data) {
        const isOnline = data.online === true;
        const status = data.status || (isOnline ? 'ONLINE' : 'OFFLINE');
        const metrics = data.metrics || {};

        // 1. Status Badge & Offline Banner
        const badge = document.getElementById('target-status-badge');
        const offlineBanner = document.getElementById('offline-alert-banner');
        const nowStr = new Date().toLocaleTimeString();
        document.getElementById('target-last-poll').textContent = nowStr;

        if (badge) {
            badge.className = `status-pill status-${status.toLowerCase()}`;
            badge.innerHTML = `<span class="status-dot"></span> ${status}`;
        }

        if (offlineBanner) {
            offlineBanner.style.display = isOnline ? 'none' : 'flex';
        }

        // 2. CPU
        const cpuVal = metrics.cpu_percent;
        const cpuEl = document.getElementById('val-cpu-percent');
        const cpuBar = document.getElementById('bar-cpu');
        const cpuSub = document.getElementById('sub-cpu-status');

        if (cpuVal !== null && cpuVal !== undefined) {
            cpuEl.textContent = cpuVal.toFixed(1);
            cpuBar.style.width = `${Math.min(100, Math.max(0, cpuVal))}%`;
            cpuBar.className = 'progress-bar ' + getProgressBarClass(cpuVal, 80, 95);
            cpuSub.textContent = cpuVal > 95 ? 'Critical CPU Load' : (cpuVal > 80 ? 'High CPU Load' : 'Nominal Load');
        } else {
            cpuEl.textContent = '--';
            cpuBar.style.width = '0%';
            cpuSub.textContent = isOnline ? 'Metric pending' : 'Endpoint unreachable';
        }

        // 3. RAM
        const memVal = metrics.memory_percent;
        const memEl = document.getElementById('val-memory-percent');
        const memBar = document.getElementById('bar-memory');
        const memSub = document.getElementById('sub-memory-details');

        if (memVal !== null && memVal !== undefined) {
            memEl.textContent = memVal.toFixed(1);
            memBar.style.width = `${Math.min(100, Math.max(0, memVal))}%`;
            memBar.className = 'progress-bar ' + getProgressBarClass(memVal, 85, 95);

            const totalGb = metrics.memory_total_bytes ? (metrics.memory_total_bytes / (1024 ** 3)).toFixed(1) : '--';
            const availGb = metrics.memory_available_bytes ? (metrics.memory_available_bytes / (1024 ** 3)).toFixed(1) : '--';
            memSub.textContent = `Avail: ${availGb} GB / Total: ${totalGb} GB`;
        } else {
            memEl.textContent = '--';
            memBar.style.width = '0%';
            memSub.textContent = isOnline ? 'Metric pending' : 'Endpoint unreachable';
        }

        // 4. Primary Storage
        const diskVal = metrics.disk_percent;
        const diskEl = document.getElementById('val-disk-percent');
        const diskBar = document.getElementById('bar-disk');
        const diskSub = document.getElementById('sub-disk-details');
        const disks = metrics.disk || [];

        if (diskVal !== null && diskVal !== undefined) {
            diskEl.textContent = diskVal.toFixed(1);
            diskBar.style.width = `${Math.min(100, Math.max(0, diskVal))}%`;
            diskBar.className = 'progress-bar ' + getProgressBarClass(diskVal, 85, 95);
            diskSub.textContent = `${disks.length} drive(s) monitored`;
        } else {
            diskEl.textContent = '--';
            diskBar.style.width = '0%';
            diskSub.textContent = isOnline ? 'Metric pending' : 'Endpoint unreachable';
        }

        // 5. Network
        const netRx = metrics.network_receive_bytes_sec ?? metrics.network?.receive_bytes_sec;
        const netTx = metrics.network_send_bytes_sec ?? metrics.network?.send_bytes_sec;
        document.getElementById('val-net-rx').textContent = netRx !== null && netRx !== undefined ? formatRate(netRx) : '-- KB/s';
        document.getElementById('val-net-tx').textContent = netTx !== null && netTx !== undefined ? formatRate(netTx) : '-- KB/s';

        // 6. Uptime
        const uptimeStr = metrics.uptime_display || 'N/A';
        document.getElementById('val-uptime').textContent = uptimeStr;

        // 7. Temperature
        document.getElementById('val-temp').textContent = metrics.temperature !== null && metrics.temperature !== undefined ? `${metrics.temperature}°C` : 'N/A';

        // 8. Disk Volumes Table
        renderDisksTable(disks);

        // 9. Monitored Services Table
        renderServicesTable(metrics.services || []);

        // 10. Disk I/O Breakdown
        const io = metrics.disk_io || {};
        document.getElementById('io-read-bytes').textContent = io.read_bytes_sec !== null && io.read_bytes_sec !== undefined ? formatRate(io.read_bytes_sec) : '-- KB/s';
        document.getElementById('io-write-bytes').textContent = io.write_bytes_sec !== null && io.write_bytes_sec !== undefined ? formatRate(io.write_bytes_sec) : '-- KB/s';
        document.getElementById('io-read-ops').textContent = io.read_ops_sec !== null && io.read_ops_sec !== undefined ? `${io.read_ops_sec.toFixed(1)} ops/s` : '-- ops/s';
        document.getElementById('io-write-ops').textContent = io.write_ops_sec !== null && io.write_ops_sec !== undefined ? `${io.write_ops_sec.toFixed(1)} ops/s` : '-- ops/s';
        document.getElementById('io-queued').textContent = io.requests_queued !== null && io.requests_queued !== undefined ? io.requests_queued.toFixed(0) : '--';

        // 11. Processes
        const proc = metrics.processes || {};
        document.getElementById('proc-total-count').textContent = proc.total_count !== null && proc.total_count !== undefined ? proc.total_count : '--';
    }

    /**
     * Render logical disk drive breakdown
     */
    function renderDisksTable(disks) {
        const tbody = document.getElementById('tbody-disks');
        const badge = document.getElementById('disk-count-badge');
        if (!tbody) return;

        if (badge) badge.textContent = `${disks.length} Volume(s)`;

        if (!disks || disks.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No disk telemetry available</td></tr>';
            return;
        }

        let html = '';
        disks.forEach(d => {
            const totalGb = (d.total_bytes / (1024 ** 3)).toFixed(1);
            const freeGb = (d.free_bytes / (1024 ** 3)).toFixed(1);
            const usedPct = d.used_percent !== null ? d.used_percent.toFixed(1) : '--';
            const barClass = getProgressBarClass(d.used_percent, 85, 95);

            html += `
                <tr>
                    <td><strong>${escapeHtml(d.drive)}</strong></td>
                    <td>${totalGb} GB</td>
                    <td>${freeGb} GB</td>
                    <td>${usedPct}%</td>
                    <td>
                        <div class="progress-bar-container progress-bar-sm">
                            <div class="progress-bar ${barClass}" style="width: ${d.used_percent || 0}%;"></div>
                        </div>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    }

    /**
     * Render services list with status badges
     */
    function renderServicesTable(services) {
        const tbody = document.getElementById('tbody-services');
        if (!tbody) return;

        if (!services || services.length === 0) {
            tbody.innerHTML = '<tr><td colspan="2" class="text-center text-muted">No service telemetry reported</td></tr>';
            return;
        }

        let html = '';
        services.forEach(s => {
            const stateLower = (s.status || '').toLowerCase();
            const isRunning = stateLower === 'running';
            const badgeClass = isRunning ? 'badge-healthy' : 'badge-neutral';
            const icon = isRunning ? '●' : '○';

            html += `
                <tr>
                    <td><code>${escapeHtml(s.service)}</code></td>
                    <td>
                        <span class="status-badge ${badgeClass}">
                            ${icon} ${escapeHtml(s.status.toUpperCase())}
                        </span>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    }

    /**
     * Fetch historical metric data for charts
     */
    async function fetchHistoricalMetrics(instance) {
        try {
            const [cpuData, memData, rxData, txData, rIoData, wIoData] = await Promise.all([
                fetchHistory(instance, 'cpu'),
                fetchHistory(instance, 'memory'),
                fetchHistory(instance, 'network_rx'),
                fetchHistory(instance, 'network_tx'),
                fetchHistory(instance, 'disk_read'),
                fetchHistory(instance, 'disk_write')
            ]);

            updateCpuChart(cpuData);
            updateMemoryChart(memData);
            updateNetworkChart(rxData, txData);
            updateDiskChart(rIoData, wIoData);
        } catch (err) {
            console.error('Error updating charts:', err);
        }
    }

    async function fetchHistory(instance, metric) {
        try {
            const url = `/api/monitoring/${encodeURIComponent(instance)}/history?metric=${metric}&range=${currentRange}`;
            const res = await fetch(url);
            if (!res.ok) return [];
            const data = await res.json();
            return data.data_points || [];
        } catch (e) {
            return [];
        }
    }

    /**
     * Initialize Chart.js instances
     */
    function initCharts() {
        if (typeof Chart === 'undefined') {
            console.warn('Chart.js library not detected');
            return;
        }

        const commonOptions = {
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 400 },
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { display: true, position: 'top', labels: { boxWidth: 12, color: '#94a3b8' } },
                tooltip: { backgroundColor: 'rgba(15, 23, 42, 0.95)', titleColor: '#f8fafc', bodyColor: '#cbd5e1' }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b', maxTicksLimit: 8 }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b' }
                }
            }
        };

        // 1. CPU Chart
        const ctxCpu = document.getElementById('chart-cpu')?.getContext('2d');
        if (ctxCpu) {
            chartCpu = new Chart(ctxCpu, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'CPU %', data: [], borderColor: '#38bdf8', backgroundColor: 'rgba(56, 189, 248, 0.1)', fill: true, tension: 0.3 }] },
                options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, min: 0, max: 100 } } }
            });
        }

        // 2. Memory Chart
        const ctxMem = document.getElementById('chart-memory')?.getContext('2d');
        if (ctxMem) {
            chartMemory = new Chart(ctxMem, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'RAM %', data: [], borderColor: '#a855f7', backgroundColor: 'rgba(168, 85, 247, 0.1)', fill: true, tension: 0.3 }] },
                options: { ...commonOptions, scales: { ...commonOptions.scales, y: { ...commonOptions.scales.y, min: 0, max: 100 } } }
            });
        }

        // 3. Network Chart
        const ctxNet = document.getElementById('chart-network')?.getContext('2d');
        if (ctxNet) {
            chartNetwork = new Chart(ctxNet, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Rx (KB/s)', data: [], borderColor: '#10b981', backgroundColor: 'transparent', tension: 0.3 },
                        { label: 'Tx (KB/s)', data: [], borderColor: '#f59e0b', backgroundColor: 'transparent', tension: 0.3 }
                    ]
                },
                options: commonOptions
            });
        }

        // 4. Disk I/O Chart
        const ctxDisk = document.getElementById('chart-disk-io')?.getContext('2d');
        if (ctxDisk) {
            chartDisk = new Chart(ctxDisk, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [
                        { label: 'Read (KB/s)', data: [], borderColor: '#06b6d4', backgroundColor: 'transparent', tension: 0.3 },
                        { label: 'Write (KB/s)', data: [], borderColor: '#f43f5e', backgroundColor: 'transparent', tension: 0.3 }
                    ]
                },
                options: commonOptions
            });
        }
    }

    function updateCpuChart(points) {
        if (!chartCpu) return;
        const labels = points.map(p => formatTimestamp(p.timestamp));
        const data = points.map(p => p.value);
        chartCpu.data.labels = labels;
        chartCpu.data.datasets[0].data = data;
        chartCpu.update();
    }

    function updateMemoryChart(points) {
        if (!chartMemory) return;
        const labels = points.map(p => formatTimestamp(p.timestamp));
        const data = points.map(p => p.value);
        chartMemory.data.labels = labels;
        chartMemory.data.datasets[0].data = data;
        chartMemory.update();
    }

    function updateNetworkChart(rxPoints, txPoints) {
        if (!chartNetwork) return;
        const labels = rxPoints.map(p => formatTimestamp(p.timestamp));
        const rxData = rxPoints.map(p => (p.value / 1024).toFixed(1)); // Convert to KB/s
        const txData = txPoints.map(p => (p.value / 1024).toFixed(1));

        chartNetwork.data.labels = labels;
        chartNetwork.data.datasets[0].data = rxData;
        chartNetwork.data.datasets[1].data = txData;
        chartNetwork.update();
    }

    function updateDiskChart(rPoints, wPoints) {
        if (!chartDisk) return;
        const labels = rPoints.map(p => formatTimestamp(p.timestamp));
        const rData = rPoints.map(p => (p.value / 1024).toFixed(1)); // Convert to KB/s
        const wData = wPoints.map(p => (p.value / 1024).toFixed(1));

        chartDisk.data.labels = labels;
        chartDisk.data.datasets[0].data = rData;
        chartDisk.data.datasets[1].data = wData;
        chartDisk.update();
    }

    // Helper functions
    function formatRate(bytesPerSec) {
        if (bytesPerSec === null || bytesPerSec === undefined) return '--';
        if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`;
        if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
        return `${(bytesPerSec / (1024 * 1024)).toFixed(2)} MB/s`;
    }

    function formatTimestamp(ts) {
        const d = new Date(ts * 1000);
        return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    }

    function getProgressBarClass(val, warningThresh, critThresh) {
        if (val === null || val === undefined) return '';
        if (val >= critThresh) return 'progress-critical';
        if (val >= warningThresh) return 'progress-warning';
        return 'progress-healthy';
    }

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function handleFetchError(err) {
        const badge = document.getElementById('target-status-badge');
        if (badge) {
            badge.className = 'status-pill status-error';
            badge.innerHTML = `<span class="status-dot"></span> ERROR`;
        }
        console.warn('Monitoring API Error:', err.message || err);
    }
})();
