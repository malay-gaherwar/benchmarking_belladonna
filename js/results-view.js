/* EdgeCase Benchmark Explorer — Results Overview */

function reasoningBadge(m) {
    if (m.reasoning === true) {
        const effort = m.reasoning_effort ? `, effort=${m.reasoning_effort}` : '';
        return ` <span class="reasoning-badge" title="Reasoning enabled${effort}">💡</span>`;
    }
    return '';
}

function paramsLabel(m) {
    if (!m.params) return '';
    if (m.params.arch === 'MoE') {
        return `<span class="params-badge" title="${m.params.total}B total, ${m.params.active}B active (MoE)">${m.params.total}B/${m.params.active}B</span>`;
    }
    return `<span class="params-badge" title="${m.params.total}B parameters">${m.params.total}B</span>`;
}

function modelLabel(m) {
    return escapeHtml(m.display_name) + reasoningBadge(m) + paramsLabel(m);
}

function hyperLabel(m) {
    const parts = [];
    if (m.temperature != null) parts.push(`temp=${m.temperature}`);
    if (m.max_tokens != null) parts.push(`max_tok=${formatNumber(m.max_tokens)}`);
    if (m.reasoning === true) {
        parts.push('reasoning=on');
        if (m.reasoning_effort) parts.push(`effort=${m.reasoning_effort}`);
    } else if (m.reasoning === false) {
        parts.push('reasoning=off');
    }
    return parts.join(' · ');
}

function formatCost(usd) {
    if (!usd) return '$0.00';
    if (usd < 0.01) return '<$0.01';
    return '$' + usd.toFixed(2);
}

async function loadSummary() {
    if (App.summaryCache) return App.summaryCache;
    const resp = await fetch('/results/summary.json');
    if (!resp.ok) throw new Error('No results yet');
    App.summaryCache = await resp.json();
    return App.summaryCache;
}

function getPrimaryDataset(model) {
    return (model.datasets || [])[0] || null;
}

function getDatasetForColumn(model, column) {
    if (!column || !column.dataset_id) return null;
    return (model.datasets || []).find(d => d.dataset_id === column.dataset_id) || null;
}

function getHeatmapValue(model, column) {
    const ds = getDatasetForColumn(model, column);
    if (!ds) return null;

    if (column.type === 'dataset') {
        return {
            accuracy: ds.accuracy,
            correct: ds.correct,
            total: ds.total,
            label: ds.dataset_name || column.dataset_id
        };
    }

    if (column.type === 'kind') {
        const kb = (ds.kind_breakdown || []).find(
            x => `${column.dataset_id}::kind::${x.kind}` === column.id
        );
        if (!kb) return null;

        return {
            accuracy: kb.accuracy,
            correct: kb.correct,
            total: kb.total,
            label: kb.kind
        };
    }

    return null;
}

function getKindBreakdown(model) {
    const ds = getPrimaryDataset(model);
    return ds?.kind_breakdown || [];
}

function buildKindBadges(model) {
    const kinds = getKindBreakdown(model);
    if (!kinds.length) return '';

    return kinds.map(k => {
        return `<span class="tile-cat-badge">${escapeHtml(k.kind)} ${k.accuracy.toFixed(1)}%</span>`;
    }).join('');
}

async function renderResultsView(container) {
    container.innerHTML = `
    <div class="results-view">
        <h2>Benchmark Results</h2>
        <p class="view-description">Model performance across the EdgeCase benchmark suite.</p>
        <p class="loading">Loading results…</p>
    </div>`;

    try {
        const summary = await loadSummary();
        renderResultsContent(container, summary);
    } catch (e) {
        container.innerHTML = `
        <div class="results-view">
            <h2>Benchmark Results</h2>
            <p class="view-description">Model performance across the EdgeCase benchmark suite.</p>
            <div class="results-placeholder">
                <p>No benchmark results available yet. Results will appear here once models have been evaluated.</p>
            </div>
        </div>`;
    }
}

function renderResultsContent(container, summary) {
    const models = summary.models;
    if (!models || models.length === 0) {
        container.querySelector('.loading').textContent = 'No results available yet.';
        return;
    }

    const dsOrder = summary.dataset_order || [];
    const catMap = summary.category_map || {};
    const heatmapColumns = summary.heatmap_columns || [];

    const dsNames = {};
    for (const d of (App.datasets || [])) dsNames[d.id] = d.name;

    const ts = summary.generated ? new Date(summary.generated).toLocaleString() : '';

    const chartHeight = Math.max(300, models.length * 52 + 60);

    const tiles = models.map((m, i) => {
        const catBadges = buildKindBadges(m);
        const totalTokens = (m.total_input_tokens || 0) + (m.total_output_tokens || 0);
        const hyper = hyperLabel(m);

        return `<a href="#/results/${m.slug}" class="model-tile">
            <div class="tile-info">
                <div class="tile-top-row">
                    <span class="tile-rank">#${m.rank}</span>
                    <span class="tile-name">${modelLabel(m)}</span>
                </div>
                <div class="tile-accuracy">${m.overall_accuracy.toFixed(1)}<span class="tile-pct">%</span></div>
                <div class="tile-categories">${catBadges}</div>
                ${hyper ? `<div class="tile-hyper">${hyper}</div>` : ''}
                <div class="tile-meta">
                    <span>${formatNumber(totalTokens)} tok</span>
                    <span>${formatCost(m.total_cost_usd)}</span>
                    <span>${m.total_errors} err</span>
                </div>
            </div>
            <div class="tile-radar">
                <canvas id="tileRadar${i}" width="140" height="140"></canvas>
            </div>
        </a>`;
    }).join('');

    const headerCells = heatmapColumns.map(col =>
        `<th class="heatmap-ds" title="${escapeHtml(col.label)}">${escapeHtml(col.label)}</th>`
    ).join('');

    const rows = models.map(m => {
        const cells = heatmapColumns.map(col => {
            const v = getHeatmapValue(m, col);
            if (!v) return '<td class="heatmap-cell">-</td>';

            const acc = v.accuracy;
            const cls = acc >= 70 ? 'acc-high' : acc >= 40 ? 'acc-mid' : 'acc-low';
            return `<td class="heatmap-cell ${cls}" title="${escapeHtml(m.display_name)} on ${escapeHtml(v.label)}: ${acc.toFixed(1)}% (${v.correct}/${v.total})">${Math.round(acc)}</td>`;
        }).join('');

        return `<tr>
            <td class="heatmap-model"><a href="#/results/${m.slug}">${modelLabel(m)}</a></td>
            <td class="heatmap-cell overall">${m.overall_accuracy.toFixed(1)}%</td>
            ${cells}
        </tr>`;
    }).join('');

    container.innerHTML = `
    <div class="results-view">
        <h2>Benchmark Results</h2>
        <p class="view-description">
            Model performance across the available benchmark results.
            ${ts ? `<span class="results-ts">Last updated: ${escapeHtml(ts)}</span>` : ''}
        </p>

        <div class="hero-chart-section">
            <h3>Overall Comparison</h3>
            <div style="height:${chartHeight}px">
                <canvas id="heroChart"></canvas>
            </div>
        </div>

        <h3 class="section-title">Accuracy Heatmap</h3>
        <div class="heatmap-wrapper">
            <table class="heatmap-table">
                <thead>
                    <tr>
                        <th class="heatmap-model-header">Model</th>
                        <th class="heatmap-overall-header">Overall</th>
                        ${headerCells}
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>

        <div class="results-legend">
            <span class="legend-item"><span class="legend-swatch acc-high"></span> ≥70%</span>
            <span class="legend-item"><span class="legend-swatch acc-mid"></span> 40-70%</span>
            <span class="legend-item"><span class="legend-swatch acc-low"></span> <40%</span>
        </div>

        <div class="hero-chart-section">
            <h3>Cost vs Performance</h3>
            <p class="chart-subtitle">Each point is one model. Panels split by dataset.</p>
            <div class="cost-perf-grid">
                ${dsOrder.map(id => `<div class="cost-perf-panel">
                    <div class="cost-perf-panel-title">${escapeHtml(dsNames[id] || id)}</div>
                    <canvas id="costPerf_${id}" width="520" height="320"></canvas>
                </div>`).join('')}
            </div>
        </div>

        <h3 class="section-title">Model Overview</h3>
        <div class="model-tiles">${tiles}</div>

        <div class="methods-section">
            <h3>Methods</h3>
            <p>Each model receives a zero-shot multiple-choice prompt with no chain-of-thought or examples. The model must reply with only the answer letter.</p>

            <h4>System Prompt</h4>
            <pre><code>You are an expert answering multiple-choice questions.
Reply with ONLY the letter of the correct answer (e.g. A).
Do not include any explanation.</code></pre>

            <h4>User Prompt Template</h4>
            <pre><code>{question}

A) {option_A}
B) {option_B}
C) {option_C}
D) {option_D}
...</code></pre>

            <h4>Hyperparameters</h4>
            <ul>
                <li><strong>Temperature:</strong> 0.7</li>
                <li><strong>Max tokens:</strong> 32 (no reasoning) / 4096 (reasoning-enabled models)</li>
                <li><strong>API:</strong> OpenRouter (<code>openrouter.ai/api/v1/chat/completions</code>)</li>
            </ul>
        </div>
    </div>`;

    buildHeroChart(models, catMap);
    buildCostPerfCharts(models, dsOrder, dsNames);
    buildTileRadars(models);
}

function buildHeroChart(models, catMap) {
    const ctx = document.getElementById('heroChart');
    if (!ctx || typeof Chart === 'undefined') return;

    const labels = models.map(m => m.display_name + (m.reasoning === true ? ' 💡' : ''));

    const datasets = [
        {
            label: 'Overall',
            data: models.map(m => m.overall_accuracy),
            backgroundColor: '#7c3aedcc',
            borderColor: '#7c3aed',
            borderWidth: 1,
        },
        {
            label: 'Expert',
            data: models.map(m => m.categories?.Expert?.accuracy || 0),
            backgroundColor: (catMap.Expert?.bg || '#ccfbf1') + '',
            borderColor: catMap.Expert?.color || '#0f766e',
            borderWidth: 1,
        },
    ];

    const chart = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { font: { family: "'Inter', sans-serif", size: 12 } }
                },
                tooltip: {
                    callbacks: {
                        label: item => `${item.dataset.label}: ${item.raw.toFixed(1)}%`
                    }
                }
            },
            scales: {
                x: {
                    beginAtZero: true,
                    max: 100,
                    title: { display: true, text: 'Accuracy (%)' },
                    ticks: { callback: v => v + '%' }
                },
                y: {
                    ticks: { font: { family: "'Inter', sans-serif", weight: 600 } }
                }
            }
        }
    });
    App.chartInstances.push(chart);
}

/**
 * Simple linear regression: y = alpha + beta * x
 * Returns { alpha, beta, r, p, n }
 */
function linRegress(xs, ys) {
    const n = xs.length;
    if (n < 3) return null;
    const sx = xs.reduce((a, b) => a + b, 0);
    const sy = ys.reduce((a, b) => a + b, 0);
    const sxx = xs.reduce((a, b, i) => a + b * b, 0);
    const sxy = xs.reduce((a, b, i) => a + b * ys[i], 0);
    const syy = ys.reduce((a, b) => a + b * b, 0);
    const mx = sx / n, my = sy / n;
    const denom = sxx - sx * sx / n;
    if (Math.abs(denom) < 1e-12) return null;
    const beta = (sxy - sx * sy / n) / denom;
    const alpha = my - beta * mx;
    const ssRes = ys.reduce((s, y, i) => s + (y - alpha - beta * xs[i]) ** 2, 0);
    const ssTot = syy - sy * sy / n;
    const r2 = ssTot > 0 ? 1 - ssRes / ssTot : 0;
    const r = Math.sign(beta) * Math.sqrt(Math.max(0, r2));
    const se = Math.sqrt(ssRes / (n - 2) / denom);
    const t = se > 0 ? beta / se : 0;
    const df = n - 2;
    const p = tToP(Math.abs(t), df);
    return { alpha, beta, r, p, n };
}

function tToP(t, df) {
    const x = df / (df + t * t);
    if (df > 30) {
        const z = t * (1 - 1 / (4 * df)) / Math.sqrt(1 + t * t / (2 * df));
        return 2 * (1 - normalCDF(Math.abs(z)));
    }
    return betaReg(x, df / 2, 0.5);
}

function normalCDF(z) {
    const a1 = 0.254829592, a2 = -0.284496736, a3 = 1.421413741, a4 = -1.453152027, a5 = 1.061405429;
    const p = 0.3275911;
    const t = 1 / (1 + p * Math.abs(z));
    const y = 1 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * Math.exp(-z * z / 2);
    return z >= 0 ? y : 1 - y;
}

function betaReg(x, a, b) {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    const lnBeta = lgamma(a) + lgamma(b) - lgamma(a + b);
    const front = Math.exp(Math.log(x) * a + Math.log(1 - x) * b - lnBeta);
    let f = 1, c = 1, d = 1 - (a + b) * x / (a + 1);
    if (Math.abs(d) < 1e-30) d = 1e-30;
    d = 1 / d; f = d;
    for (let m = 1; m <= 100; m++) {
        let num = m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m));
        d = 1 + num * d; if (Math.abs(d) < 1e-30) d = 1e-30; d = 1 / d;
        c = 1 + num / c; if (Math.abs(c) < 1e-30) c = 1e-30;
        f *= d * c;
        num = -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1));
        d = 1 + num * d; if (Math.abs(d) < 1e-30) d = 1e-30; d = 1 / d;
        c = 1 + num / c; if (Math.abs(c) < 1e-30) c = 1e-30;
        const delta = d * c; f *= delta;
        if (Math.abs(delta - 1) < 1e-8) break;
    }
    return front * f / a;
}

function lgamma(x) {
    const c = [76.18009172947146, -86.50532032941677, 24.01409824083091,
        -1.231739572450155, 0.001208650973866179, -5.395239384953e-06];
    let y = x, tmp = x + 5.5;
    tmp -= (x + 0.5) * Math.log(tmp);
    let ser = 1.000000000190015;
    for (let j = 0; j < 6; j++) ser += c[j] / ++y;
    return -tmp + Math.log(2.5066282746310005 * ser / x);
}

function buildCostPerfCharts(models, dsOrder, dsNames) {
    if (typeof Chart === 'undefined') return;

    const palette = [
        '#7c3aed', '#1e40af', '#9d174d', '#059669', '#d97706',
        '#dc2626', '#4f46e5', '#0891b2', '#be185d', '#65a30d',
        '#c026d3', '#ea580c', '#2563eb', '#16a34a', '#e11d48', '#7c2d12',
    ];

    for (const dsId of dsOrder) {
        const ctx = document.getElementById(`costPerf_${dsId}`);
        if (!ctx) continue;

        const allPoints = [];
        const datasets = [];
        models.forEach((m, i) => {
            const color = palette[i % palette.length];
            const label = m.display_name + (m.reasoning === true ? ' 💡' : '');
            const d = (m.datasets || []).find(d => d.dataset_id === dsId);
            if (!d || d.cost_usd === 0) return;

            allPoints.push({ logCost: Math.log10(d.cost_usd), cost: d.cost_usd, acc: d.accuracy });
            datasets.push({
                label,
                data: [{ x: d.cost_usd, y: d.accuracy, correct: d.correct, total: d.total }],
                backgroundColor: color + 'cc',
                borderColor: color,
                borderWidth: 1.5,
                pointRadius: 5,
                pointHoverRadius: 8,
            });
        });

        const reg = allPoints.length >= 3
            ? linRegress(allPoints.map(p => p.logCost), allPoints.map(p => p.acc))
            : null;

        if (reg) {
            const minLog = Math.min(...allPoints.map(p => p.logCost));
            const maxLog = Math.max(...allPoints.map(p => p.logCost));
            const trendPoints = [];
            for (let l = minLog; l <= maxLog + 0.001; l += (maxLog - minLog) / 50) {
                trendPoints.push({ x: Math.pow(10, l), y: reg.alpha + reg.beta * l });
            }
            datasets.push({
                label: 'Trend',
                data: trendPoints,
                type: 'line',
                borderColor: '#ef444488',
                borderWidth: 1.5,
                borderDash: [4, 3],
                pointRadius: 0,
                pointHoverRadius: 0,
                fill: false,
                order: 1,
            });
        }

        const statsText = reg
            ? `r=${reg.r.toFixed(2)} β=${reg.beta.toFixed(1)} p=${reg.p < 0.001 ? '<.001' : reg.p.toFixed(3)}`
            : '';

        const chart = new Chart(ctx, {
            type: 'scatter',
            data: { datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        filter: item => item.dataset.label !== 'Trend',
                        callbacks: {
                            label: item => {
                                const p = item.raw;
                                return `${item.dataset.label}: ${p.y.toFixed(1)}% (${p.correct}/${p.total}) — $${p.x.toFixed(3)}`;
                            }
                        }
                    },
                    statsAnnotation: { text: statsText },
                },
                scales: {
                    x: {
                        type: 'logarithmic',
                        title: { display: false },
                        ticks: {
                            callback: (v) => {
                                const log = Math.log10(v);
                                if (Math.abs(log - Math.round(log)) < 0.01) {
                                    return v >= 1 ? '$' + v : '$' + v.toFixed(Math.max(0, -Math.round(log)));
                                }
                                return null;
                            },
                            font: { size: 8 },
                            maxTicksLimit: 5,
                        },
                        grid: { color: '#f3f4f6' },
                    },
                    y: {
                        beginAtZero: true,
                        max: 100,
                        title: { display: false },
                        ticks: {
                            callback: v => v + '%',
                            font: { size: 8 },
                            stepSize: 25,
                        },
                        grid: { color: '#f3f4f6' },
                    }
                }
            },
            plugins: [{
                id: 'statsAnnotation',
                afterDraw(chart) {
                    const text = chart.options.plugins.statsAnnotation?.text;
                    if (!text) return;
                    const { ctx, chartArea } = chart;
                    ctx.save();
                    ctx.font = "600 9px 'Inter', sans-serif";
                    ctx.fillStyle = '#ef4444';
                    ctx.textAlign = 'right';
                    ctx.fillText(text, chartArea.right - 2, chartArea.top + 10);
                    ctx.restore();
                }
            }],
        });
        App.chartInstances.push(chart);
    }
}

function buildTileRadars(models) {
    if (typeof Chart === 'undefined') return;

    models.forEach((m, i) => {
        const ctx = document.getElementById(`tileRadar${i}`);
        if (!ctx) return;

        const breakdown = getKindBreakdown(m);
        if (!breakdown.length) return;

        const labels = ['Overall', ...breakdown.map(k => k.kind)];
        const data = [m.overall_accuracy, ...breakdown.map(k => k.accuracy)];

        const chart = new Chart(ctx, {
            type: 'radar',
            data: {
                labels,
                datasets: [{
                    data,
                    backgroundColor: 'rgba(124, 58, 237, 0.12)',
                    borderColor: '#7c3aed',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    pointHoverRadius: 3,
                }]
            },
            options: {
                responsive: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: true,
                        callbacks: {
                            label: item => `${item.label}: ${item.raw.toFixed(1)}%`
                        }
                    }
                },
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 100,
                        ticks: { display: false },
                        pointLabels: {
                            font: { size: 7, family: "'Inter', sans-serif" },
                            color: '#9ca3af'
                        },
                        grid: { color: '#e5e7eb' },
                        angleLines: { color: '#e5e7eb' }
                    }
                }
            }
        });
        App.chartInstances.push(chart);
    });
}