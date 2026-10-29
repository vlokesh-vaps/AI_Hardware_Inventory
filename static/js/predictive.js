/**
 * Predictive Analysis & AI Insights Frontend Script.
 * Coordinates Chart.js rendering, NVIDIA Nemotron AI report updates, and interactive Q&A.
 */

let healthChartInstance = null;
let runwayChartInstance = null;

/**
 * Initializes Health Status Over Time and Storage Runway charts.
 */
function initPredictiveCharts(timelineData, runwayData) {
    // 1. Health Status Over Time (Chart.js)
    const ctxHealth = document.getElementById('healthTimelineChart');
    if (ctxHealth && timelineData && timelineData.dates) {
        if (healthChartInstance) {
            healthChartInstance.destroy();
        }

        healthChartInstance = new Chart(ctxHealth, {
            type: 'line',
            data: {
                labels: timelineData.dates,
                datasets: [
                    {
                        label: 'Healthy',
                        data: timelineData.healthy_series || [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.15)',
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    },
                    {
                        label: 'Warning',
                        data: timelineData.warning_series || [],
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.15)',
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    },
                    {
                        label: 'Critical',
                        data: timelineData.critical_series || [],
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.15)',
                        fill: true,
                        tension: 0.35,
                        pointRadius: 4,
                        pointHoverRadius: 6
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            font: { family: "'Inter', sans-serif", size: 12 }
                        }
                    },
                    tooltip: {
                        backgroundColor: '#1e293b',
                        titleFont: { family: "'Inter', sans-serif", size: 13, weight: 'bold' },
                        bodyFont: { family: "'Inter', sans-serif", size: 12 },
                        padding: 10,
                        cornerRadius: 8
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: "'Inter', sans-serif" } }
                    },
                    y: {
                        beginAtZero: true,
                        ticks: {
                            precision: 0,
                            font: { family: "'Inter', sans-serif" }
                        },
                        grid: { color: 'rgba(226, 232, 240, 0.6)' }
                    }
                }
            }
        });
    }

    // 2. Storage Runway Projection (Horizontal Bar Chart)
    const ctxRunway = document.getElementById('storageRunwayChart');
    if (ctxRunway && runwayData && runwayData.projections) {
        if (runwayChartInstance) {
            runwayChartInstance.destroy();
        }

        const topRunways = (runwayData.projections || []).slice(0, 8);
        const labels = topRunways.map(p => `${p.computer_name} (${p.drive_letter})`);
        const days = topRunways.map(p => Math.min(365, p.days_remaining));
        const colors = topRunways.map(p => {
            if (p.urgency === 'CRITICAL') return '#ef4444';
            if (p.urgency === 'WARNING') return '#f59e0b';
            if (p.urgency === 'ATTENTION') return '#3b82f6';
            return '#10b981';
        });

        runwayChartInstance = new Chart(ctxRunway, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Days of Runway Remaining',
                    data: days,
                    backgroundColor: colors,
                    borderRadius: 6
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#1e293b',
                        callbacks: {
                            label: function(ctx) {
                                const idx = ctx.dataIndex;
                                const item = topRunways[idx];
                                return `Runway: ${item.days_remaining} days (~${item.daily_burn_gb} GB/day burn)`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        beginAtZero: true,
                        title: { display: true, text: 'Estimated Days Remaining (Capped at 365d)', font: { family: "'Inter', sans-serif" } },
                        grid: { color: 'rgba(226, 232, 240, 0.6)' }
                    },
                    y: {
                        grid: { display: false },
                        ticks: { font: { family: "'Inter', sans-serif", weight: '500' } }
                    }
                }
            }
        });
    }
}

/**
 * Parses markdown in the AI insight box on initial page load.
 */
function renderInitialMarkdown() {
    const reportBox = document.getElementById('ai-report-content');
    if (reportBox && typeof marked !== 'undefined') {
        const rawContent = reportBox.textContent.trim();
        if (rawContent && !rawContent.startsWith('<')) {
            reportBox.innerHTML = marked.parse(rawContent);
        }
    }
}

/**
 * Triggers an asynchronous regeneration of AI Insights via NVIDIA Nemotron.
 */
async function refreshAIInsights() {
    const btn = document.getElementById('btn-refresh-ai');
    const spinner = document.getElementById('ai-spinner');
    const btnText = document.getElementById('ai-btn-text');
    const reportContent = document.getElementById('ai-report-content');
    const timestampElem = document.getElementById('ai-timestamp');
    const elapsedElem = document.getElementById('ai-elapsed');

    if (btn) btn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (btnText) btnText.textContent = 'Generating Nemotron AI Insights...';

    // Show temporary pulsing indicator in report body
    if (reportContent) {
        reportContent.style.opacity = '0.5';
    }

    try {
        const response = await fetch('/api/ai/insights', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ refresh: true })
        });

        if (!response.ok) {
            throw new Error(`Server returned HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.content && reportContent) {
            if (typeof marked !== 'undefined') {
                reportContent.innerHTML = marked.parse(data.content);
            } else {
                reportContent.textContent = data.content;
            }
        }

        if (data.generated_at && timestampElem) {
            timestampElem.textContent = data.generated_at;
        }

        if (data.elapsed_seconds !== undefined && elapsedElem) {
            elapsedElem.textContent = `${data.elapsed_seconds}s`;
        }

        // Show toast feedback if available
        if (window.showToast) {
            window.showToast('NVIDIA Nemotron AI insights updated successfully.', 'success');
        }

    } catch (err) {
        console.error('Failed to refresh AI insights:', err);
        if (window.showToast) {
            window.showToast(`Failed to generate insights: ${err.message}`, 'error');
        } else {
            alert(`Error generating AI insights: ${err.message}`);
        }
    } finally {
        if (btn) btn.disabled = false;
        if (spinner) spinner.style.display = 'none';
        if (btnText) btnText.textContent = 'Refresh AI Insights';
        if (reportContent) reportContent.style.opacity = '1';
    }
}

/**
 * Copies the raw markdown of the AI diagnostic report to clipboard.
 */
function copyAIReport() {
    const reportBox = document.getElementById('ai-report-content');
    if (!reportBox) return;

    const textToCopy = reportBox.innerText;
    navigator.clipboard.writeText(textToCopy).then(() => {
        const copyBtn = document.getElementById('btn-copy-ai');
        if (copyBtn) {
            const orig = copyBtn.innerHTML;
            copyBtn.innerHTML = '✓ Copied!';
            setTimeout(() => { copyBtn.innerHTML = orig; }, 2000);
        }
    }).catch(err => {
        console.error('Copy failed:', err);
    });
}

/**
 * Pre-fills question input from recommendation chips.
 */
function setQuickQuestion(q) {
    const input = document.getElementById('ai-question-input');
    if (input) {
        input.value = q;
        input.focus();
    }
}

/**
 * Submits an ad-hoc question to NVIDIA Nemotron.
 */
async function submitAIQuestion(e) {
    if (e) e.preventDefault();

    const input = document.getElementById('ai-question-input');
    const submitBtn = document.getElementById('btn-ask-submit');
    const spinner = document.getElementById('ask-spinner');
    const btnText = document.getElementById('ask-btn-text');
    const responseArea = document.getElementById('qa-response-area');
    const questionEcho = document.getElementById('qa-question-echo');
    const answerBox = document.getElementById('qa-answer-box');

    if (!input || !input.value.trim()) return;
    const question = input.value.trim();

    if (submitBtn) submitBtn.disabled = true;
    if (spinner) spinner.style.display = 'inline-block';
    if (btnText) btnText.textContent = 'Consulting AI...';

    if (responseArea) responseArea.style.display = 'block';
    if (questionEcho) questionEcho.textContent = `Q: ${question}`;
    if (answerBox) answerBox.innerHTML = '<div class="ai-typing"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span> Analyzing fleet telemetry...</div>';

    try {
        const resp = await fetch('/api/ai/ask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: question })
        });

        if (!resp.ok) {
            throw new Error(`Server returned HTTP ${resp.status}`);
        }

        const result = await resp.json();
        const answerMarkdown = result.answer || 'No response returned.';

        if (answerBox) {
            if (typeof marked !== 'undefined') {
                answerBox.innerHTML = marked.parse(answerMarkdown);
            } else {
                answerBox.textContent = answerMarkdown;
            }
        }

    } catch (err) {
        console.error('Ask AI failed:', err);
        if (answerBox) {
            answerBox.innerHTML = `<div class="text-danger">⚠️ Request error: ${err.message}. Please verify connectivity.</div>`;
        }
    } finally {
        if (submitBtn) submitBtn.disabled = false;
        if (spinner) spinner.style.display = 'none';
        if (btnText) btnText.textContent = 'Ask AI';
    }
}
