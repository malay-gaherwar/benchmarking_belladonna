/* EdgeCase Benchmark Explorer — Self-Consistency Results Overview */

async function loadScSummary() {
    if (App.scSummaryCache) return App.scSummaryCache;
    const resp = await fetch('/results-sc/summary.json');
    if (!resp.ok) throw new Error('No SC results yet');
    App.scSummaryCache = await resp.json();
    return App.scSummaryCache;
}

function scModelLabel(m) {
    return escapeHtml(m.display_name) + paramsLabel(m);
}

function scHyperLabel(m) {
    const parts = [];
    if (m.temperature != null) parts.push(`temp=${m.temperature}`);
    parts.push(`SC: ${m.n_samples || 5} samples, majority vote`);
    return parts.join(' \u00b7 ');
}

async function renderScResultsView(container) {
    container.innerHTML = `
    <div class="results-view">
        <h2>Self-Consistency Benchmark Results</h2>
        <p class="view-description">N=5 samples per question at temperature 0.7, majority-vote final answer.</p>
        <p class="loading">Loading results\u2026</p>
    </div>`;

    try {
        const summary = await loadScSummary();
        renderScResultsContent(container, summary);
    } catch (e) {
        container.innerHTML = `
        <div class="results-view">
            <h2>Self-Consistency Benchmark Results</h2>
            <p class="view-description">N=5 samples per question at temperature 0.7, majority-vote final answer.</p>
            <div class="results-placeholder">
                <p>No self-consistency results available yet. Run <code>python3 bench/run_sc.py</code> to generate results.</p>
            </div>
        </div>`;
    }
}

function renderScResultsContent(container, summary) {
    const models = summary.models;
    if (!models || models.length === 0) {
        container.querySelector('.loading').textContent = 'No results available yet.';
        return;
    }

    const dsOrder = summary.dataset_order;
    const catMap = summary.category_map;

    const dsNames = {};
    for (const d of App.datasets) dsNames[d.id] = d.name;

    const dsShort = {
        'mmlu-e': 'ML-E', 'triage': 'TRI', 'truthfulqa': 'TQA',
        'medbullets': 'MBul', 'medcalc': 'MCal', 'metamedqa': 'MMQ',
        'mmlu-m': 'ML-M', 'pubmedqa': 'PMQ', 'bbq': 'BBQ',
        'casehold': 'CSH', 'mmlu-s': 'ML-S', 'mmlupro-s': 'MLP',
    };

    const ts = summary.generated ? new Date(summary.generated).toLocaleString() : '';
    const chartHeight = Math.max(300, models.length * 52 + 60);

    // --- Helper: subset info ---
    function subsetInfo(m) {
        const totalAssessed = m.datasets.reduce((s, d) => s + d.total, 0);
        const totalFull = m.datasets.reduce((s, d) => s + (d.total_in_dataset || d.total), 0);
        const isSubset = totalAssessed < totalFull;
        const pct = Math.round(totalAssessed / totalFull * 100);
        return { totalAssessed, totalFull, isSubset, pct };
    }

    // --- Model tiles ---
    const tiles = models.map((m, i) => {
        const catBadges = Object.entries(m.categories).map(([cat, stats]) => {
            const cm = catMap[cat] || {};
            return `<span class="tile-cat-badge" style="background:${cm.bg || '#f3f4f6'};color:${cm.color || '#333'}">${escapeHtml(cat)} ${stats.accuracy.toFixed(1)}%</span>`;
        }).join('');

        const totalTokens = m.total_input_tokens + m.total_output_tokens;
        const baselineHtml = m.baseline_accuracy != null
            ? (() => {
                const diff = m.overall_accuracy - m.baseline_accuracy;
                const sign = diff > 0 ? '+' : '';
                const cls = diff > 2 ? 'diff-pos' : diff < -2 ? 'diff-neg' : 'diff-neutral';
                return `<div class="tile-baseline">vs zero-shot: ${m.baseline_accuracy.toFixed(1)}% <span class="${cls}">(${sign}${diff.toFixed(1)}%)</span></div>`;
            })()
            : '';

        const si = subsetInfo(m);
        const subsetBadge = si.isSubset
            ? `<div class="subset-label">Subset: ${formatNumber(si.totalAssessed)}/${formatNumber(si.totalFull)} questions (${si.pct}%)</div>`
            : '';

        return `<a href="#/sc-results/${m.slug}" class="model-tile">
            <div class="tile-info">
                <div class="tile-top-row">
                    <span class="tile-rank">#${m.rank}</span>
                    <span class="tile-name">${scModelLabel(m)}</span>
                </div>
                <div class="tile-accuracy">${m.overall_accuracy.toFixed(1)}<span class="tile-pct">%</span></div>
                ${baselineHtml}
                ${subsetBadge}
                <div class="tile-categories">${catBadges}</div>
                <div class="tile-mas-meta">
                    <span title="Average agreement across samples">Agreement: ${m.avg_agreement.toFixed(1)}%</span>
                </div>
                <div class="tile-meta">
                    <span>${formatNumber(totalTokens)} tok</span>
                    <span>${formatCost(m.total_cost_usd)}</span>
                    <span>${m.total_errors} err</span>
                </div>
            </div>
            <div class="tile-radar">
                <canvas id="scTileRadar${i}" width="140" height="140"></canvas>
            </div>
        </a>`;
    }).join('');

    // --- Heatmap table ---
    const headerCells = dsOrder.map(id =>
        `<th class="heatmap-ds" title="${escapeHtml(dsNames[id] || id)}">${escapeHtml(dsShort[id] || dsNames[id] || id)}</th>`
    ).join('');

    const rows = models.map(m => {
        const dsLookup = {};
        for (const d of m.datasets) dsLookup[d.dataset_id] = d;

        const cells = dsOrder.map(dsId => {
            const r = dsLookup[dsId];
            if (!r) return '<td class="heatmap-cell">-</td>';
            const acc = r.accuracy;
            const base = r.baseline_accuracy;
            const cls = acc >= 70 ? 'acc-high' : acc >= 40 ? 'acc-mid' : 'acc-low';
            const baseTitle = base != null ? ` (zero-shot: ${base.toFixed(1)}%)` : '';
            const isSubset = r.total_in_dataset && r.total < r.total_in_dataset;
            const subsetTitle = isSubset ? ` [${r.total}/${r.total_in_dataset} assessed]` : '';
            const subsetMark = isSubset ? '<span class="subset-dot" title="Subset assessed">*</span>' : '';
            return `<td class="heatmap-cell ${cls}" title="${escapeHtml(m.display_name)} on ${escapeHtml(dsNames[dsId])}: SC ${acc.toFixed(1)}%${baseTitle} (${r.correct}/${r.total})${subsetTitle}">${Math.round(acc)}${subsetMark}</td>`;
        }).join('');

        const baseOverall = m.baseline_accuracy != null ? ` (zero-shot: ${m.baseline_accuracy.toFixed(1)}%)` : '';
        const hsi = (() => {
            const a = m.datasets.reduce((s, d) => s + d.total, 0);
            const f = m.datasets.reduce((s, d) => s + (d.total_in_dataset || d.total), 0);
            return a < f ? ` <span class="subset-label-inline">${Math.round(a/f*100)}%</span>` : '';
        })();
        return `<tr>
            <td class="heatmap-model"><a href="#/sc-results/${m.slug}">${scModelLabel(m)}</a>${hsi}</td>
            <td class="heatmap-cell overall" title="SC: ${m.overall_accuracy.toFixed(1)}%${baseOverall}">${m.overall_accuracy.toFixed(1)}%</td>
            ${cells}
        </tr>`;
    }).join('');

    container.innerHTML = `
    <div class="results-view">
        <h2>Self-Consistency Benchmark Results</h2>
        <p class="view-description">
            N=5 samples per question at temperature 0.7 with majority voting. Only models completing all 12 datasets are shown.
            ${ts ? `<span class="results-ts">Last updated: ${escapeHtml(ts)}</span>` : ''}
        </p>

        <div class="hero-chart-section">
            <h3>Overall Comparison</h3>
            <div style="height:${chartHeight}px">
                <canvas id="scHeroChart"></canvas>
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
            <span class="legend-item"><span class="legend-swatch acc-high"></span> &ge;70%</span>
            <span class="legend-item"><span class="legend-swatch acc-mid"></span> 40-70%</span>
            <span class="legend-item"><span class="legend-swatch acc-low"></span> &lt;40%</span>
            <span class="legend-item"><span class="subset-dot">*</span> subset assessed</span>
        </div>

        <h3 class="section-title">Model Overview</h3>
        <div class="model-tiles">${tiles}</div>

        <div class="methods-section">
            <h3>Methods</h3>
            <p>Each question is sampled N=5 times at temperature 0.7. Each sample uses the same zero-shot prompt. The final answer is determined by majority vote across the 5 samples. Agreement is the fraction of samples that voted for the winning answer.</p>

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

            <h4>Voting</h4>
            <pre><code>For each question:
  1. Sample 5 independent completions (temperature=0.7)
  2. Parse each completion for answer letter
  3. Majority vote across valid predictions
  4. Agreement = count(winner) / N_samples</code></pre>

            <h4>Hyperparameters</h4>
            <ul>
                <li><strong>N samples:</strong> 5 per question</li>
                <li><strong>Temperature:</strong> 0.7</li>
                <li><strong>Max tokens:</strong> 32</li>
                <li><strong>Voting method:</strong> Majority vote (ties broken by first mode)</li>
                <li><strong>API:</strong> OpenRouter (<code>openrouter.ai/api/v1/chat/completions</code>)</li>
            </ul>
        </div>
    </div>`;

    buildScHeroChart(models, catMap);
    buildScTileRadars(models);
}

function buildScTileRadars(models) {
    if (typeof Chart === 'undefined') return;

    const shortLabels = {
        'mmlu-e': 'ML-E', 'triage': 'TRI', 'truthfulqa': 'TQA',
        'medbullets': 'MBul', 'medcalc': 'MCal', 'metamedqa': 'MMQ',
        'mmlu-m': 'ML-M', 'pubmedqa': 'PMQ', 'bbq': 'BBQ',
        'casehold': 'CSH', 'mmlu-s': 'ML-S', 'mmlupro-s': 'MLP',
    };

    models.forEach((m, i) => {
        const ctx = document.getElementById(`scTileRadar${i}`);
        if (!ctx) return;

        const labels = m.datasets.map(d => shortLabels[d.dataset_id] || d.dataset_name);
        const scData = m.datasets.map(d => d.accuracy);
        const baseData = m.datasets.map(d => d.baseline_accuracy ?? null);

        const chartDatasets = [{
            label: 'SC',
            data: scData,
            backgroundColor: 'rgba(16, 185, 129, 0.12)',
            borderColor: '#10b981',
            borderWidth: 1.5,
            pointRadius: 0,
        }];

        if (baseData.some(v => v != null)) {
            chartDatasets.push({
                label: 'Zero-Shot',
                data: baseData,
                backgroundColor: 'rgba(156, 163, 175, 0.08)',
                borderColor: '#9ca3af',
                borderWidth: 1,
                borderDash: [3, 3],
                pointRadius: 0,
            });
        }

        const chart = new Chart(ctx, {
            type: 'radar',
            data: { labels, datasets: chartDatasets },
            options: {
                responsive: false,
                animation: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: item => `${item.dataset.label}: ${item.raw?.toFixed(1) ?? 'n/a'}%`
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

function buildScHeroChart(models, catMap) {
    const ctx = document.getElementById('scHeroChart');
    if (!ctx || typeof Chart === 'undefined') return;

    const labels = models.map(m => {
        const si = (() => {
            const a = m.datasets.reduce((s, d) => s + d.total, 0);
            const f = m.datasets.reduce((s, d) => s + (d.total_in_dataset || d.total), 0);
            return a < f ? ` (${Math.round(a/f*100)}% subset)` : '';
        })();
        return m.display_name + si;
    });

    const datasets = [
        {
            label: 'SC Overall',
            data: models.map(m => m.overall_accuracy),
            backgroundColor: '#10b981cc',
            borderColor: '#10b981',
            borderWidth: 1,
        },
        {
            label: 'Zero-Shot Baseline',
            data: models.map(m => m.baseline_accuracy || 0),
            backgroundColor: '#9ca3af88',
            borderColor: '#9ca3af',
            borderWidth: 1,
            borderDash: [4, 4],
        },
        {
            label: 'Ethics',
            data: models.map(m => m.categories.Ethics?.accuracy || 0),
            backgroundColor: (catMap.Ethics?.bg || '#ede9fe') + '',
            borderColor: catMap.Ethics?.color || '#7c3aed',
            borderWidth: 1,
        },
        {
            label: 'Reasoning',
            data: models.map(m => m.categories.Reasoning?.accuracy || 0),
            backgroundColor: (catMap.Reasoning?.bg || '#dbeafe') + '',
            borderColor: catMap.Reasoning?.color || '#1e40af',
            borderWidth: 1,
        },
        {
            label: 'Safety',
            data: models.map(m => m.categories.Safety?.accuracy || 0),
            backgroundColor: (catMap.Safety?.bg || '#fce7f3') + '',
            borderColor: catMap.Safety?.color || '#9d174d',
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
