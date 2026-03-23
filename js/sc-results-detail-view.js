/* EdgeCase Benchmark Explorer — Self-Consistency Model Detail View */

async function renderScDetailView(container, slug) {
    container.innerHTML = `
    <div class="results-view">
        <div class="breadcrumb">
            <a href="#/sc-results">Self-Consistency Results</a><span>&rsaquo;</span><span>Loading\u2026</span>
        </div>
        <p class="loading">Loading model details\u2026</p>
    </div>`;

    try {
        const summary = await loadScSummary();
        const model = summary.models.find(m => m.slug === slug);
        if (!model) throw new Error('Model not found');
        renderScDetailContent(container, model, summary);
    } catch (e) {
        container.innerHTML = `
        <div class="results-view">
            <div class="breadcrumb">
                <a href="#/sc-results">Self-Consistency Results</a><span>&rsaquo;</span><span>Not found</span>
            </div>
            <div class="results-placeholder">
                <p>Model not found. <a href="#/sc-results">Back to SC results</a></p>
            </div>
        </div>`;
    }
}

function renderScDetailContent(container, model, summary) {
    const catMap = summary.category_map;
    const totalTokens = model.total_input_tokens + model.total_output_tokens;

    const dsNames = {};
    for (const d of App.datasets) dsNames[d.id] = d.name;

    // Category breakdown cards
    const catCards = Object.entries(model.categories).map(([cat, stats]) => {
        const cm = catMap[cat] || {};
        const catDatasets = model.datasets.filter(d => d.categories.includes(cat));
        const bars = catDatasets.map(d => {
            const pct = d.accuracy;
            return `<div class="cat-ds-row">
                <span class="cat-ds-name">${escapeHtml(d.dataset_name)}</span>
                <div class="cat-ds-bar-bg">
                    <div class="cat-ds-bar" style="width:${pct}%;background:${cm.color || '#10b981'}"></div>
                </div>
                <span class="cat-ds-val">${pct.toFixed(1)}%</span>
            </div>`;
        }).join('');

        return `<div class="category-card" style="border-top-color:${cm.color || '#10b981'}">
            <div class="cat-card-header">
                <h4>${escapeHtml(cat)}</h4>
                <span class="cat-card-acc">${stats.accuracy.toFixed(1)}%</span>
            </div>
            <div class="cat-card-meta">${stats.correct}/${stats.total - stats.errors} correct</div>
            <div class="cat-ds-bars">${bars}</div>
        </div>`;
    }).join('');

    // Dataset table with baseline comparison
    const dsRows = model.datasets.map(d => {
        const acc = d.accuracy;
        const cls = acc >= 70 ? 'acc-high' : acc >= 40 ? 'acc-mid' : 'acc-low';
        const base = d.baseline_accuracy;
        let diffHtml = '<td class="ds-table-num">-</td>';
        if (base != null) {
            const diff = acc - base;
            const sign = diff > 0 ? '+' : '';
            const dcls = diff > 2 ? 'diff-pos' : diff < -2 ? 'diff-neg' : 'diff-neutral';
            diffHtml = `<td class="ds-table-num"><span class="${dcls}">${sign}${diff.toFixed(1)}%</span></td>`;
        }
        const cats = d.categories.map(c => {
            const cm = catMap[c] || {};
            return `<span class="badge" style="background:${cm.bg || '#f3f4f6'};color:${cm.color || '#333'}">${escapeHtml(c)}</span>`;
        }).join(' ');
        const agreePct = d.avg_agreement != null ? d.avg_agreement.toFixed(1) + '%' : '-';
        return `<tr>
            <td class="ds-table-name">${escapeHtml(d.dataset_name)}</td>
            <td class="ds-table-cats">${cats}</td>
            <td class="heatmap-cell ${cls}">${acc.toFixed(1)}%</td>
            <td class="ds-table-num">${base != null ? base.toFixed(1) + '%' : '-'}</td>
            ${diffHtml}
            <td class="ds-table-num">${agreePct}</td>
            <td class="ds-table-num">${d.correct}/${d.total}${d.total_in_dataset && d.total < d.total_in_dataset ? ` <span class="subset-badge" title="${d.total} of ${d.total_in_dataset} assessed">(${Math.round(d.total/d.total_in_dataset*100)}%)</span>` : ''}</td>
            <td class="ds-table-num">${d.errors}</td>
            <td class="ds-table-num">${formatNumber(d.input_tokens + d.output_tokens)}</td>
        </tr>`;
    }).join('');

    // Subset info
    const detailTotalAssessed = model.datasets.reduce((s, d) => s + d.total, 0);
    const detailTotalFull = model.datasets.reduce((s, d) => s + (d.total_in_dataset || d.total), 0);
    const detailIsSubset = detailTotalAssessed < detailTotalFull;
    const detailSubsetPct = Math.round(detailTotalAssessed / detailTotalFull * 100);
    const detailSubsetBanner = detailIsSubset
        ? `<div class="subset-banner">Subset evaluation: ${formatNumber(detailTotalAssessed)} of ${formatNumber(detailTotalFull)} questions assessed (${detailSubsetPct}%)</div>`
        : '';

    const paramsStr = model.params ? model.params.total + 'B params' : '';

    container.innerHTML = `
    <div class="results-view">
        <div class="breadcrumb">
            <a href="#/sc-results">Self-Consistency Results</a><span>&rsaquo;</span><span>${scModelLabel(model)}</span>
        </div>

        <div class="detail-header">
            <div class="detail-rank">#${model.rank}</div>
            <div>
                <h2>${scModelLabel(model)}</h2>
                <p class="detail-model-path">${escapeHtml(model.model)} &middot; Self-Consistency (N=${model.n_samples || 5}, temp=${model.temperature || 0.7}, majority vote)${paramsStr ? ' &middot; ' + paramsStr : ''}</p>
            </div>
        </div>

        ${detailSubsetBanner}

        <div class="detail-stats-inline">
            <div class="stat-inline"><span class="stat-val-inline">${model.overall_accuracy.toFixed(1)}%</span> <span class="stat-lbl-inline">SC Accuracy</span></div>
            ${model.baseline_accuracy != null ? `<div class="stat-inline"><span class="stat-val-inline">${model.baseline_accuracy.toFixed(1)}%</span> <span class="stat-lbl-inline">Zero-Shot Baseline</span></div>` : ''}
            <div class="stat-inline"><span class="stat-val-inline">${model.avg_agreement.toFixed(1)}%</span> <span class="stat-lbl-inline">Agreement</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${formatNumber(model.total_questions)}${detailIsSubset ? '/' + formatNumber(detailTotalFull) : ''}</span> <span class="stat-lbl-inline">Questions</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${formatNumber(totalTokens)}</span> <span class="stat-lbl-inline">Tokens</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${formatCost(model.total_cost_usd)}</span> <span class="stat-lbl-inline">Cost</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${model.total_errors}</span> <span class="stat-lbl-inline">Errors</span></div>
        </div>

        <div class="chart-card">
            <h3>Per-Dataset Accuracy</h3>
            <div class="radar-wrapper">
                <canvas id="scRadarChart"></canvas>
            </div>
        </div>

        <h3 class="section-title">Category Breakdown</h3>
        <div class="category-cards">${catCards}</div>

        <h3 class="section-title">All Datasets</h3>
        <div class="heatmap-wrapper">
            <table class="heatmap-table detail-ds-table">
                <thead>
                    <tr>
                        <th style="text-align:left;padding-left:1rem">Dataset</th>
                        <th style="text-align:left">Categories</th>
                        <th>SC Acc</th>
                        <th>Zero-Shot Acc</th>
                        <th>Diff</th>
                        <th>Agreement</th>
                        <th>Correct/Total</th>
                        <th>Errors</th>
                        <th>Tokens</th>
                    </tr>
                </thead>
                <tbody>${dsRows}</tbody>
            </table>
        </div>
    </div>`;

    buildScRadarChart(model, catMap);
}

function buildScRadarChart(model, catMap) {
    const ctx = document.getElementById('scRadarChart');
    if (!ctx || typeof Chart === 'undefined') return;

    const labels = model.datasets.map(d => d.dataset_name);
    const scData = model.datasets.map(d => d.accuracy);
    const baseData = model.datasets.map(d => d.baseline_accuracy ?? null);

    const chartDatasets = [{
        label: 'Self-Consistency',
        data: scData,
        backgroundColor: 'rgba(16, 185, 129, 0.15)',
        borderColor: '#10b981',
        borderWidth: 2,
        pointBackgroundColor: '#10b981',
        pointRadius: 4,
        pointHoverRadius: 6,
    }];

    if (baseData.some(v => v != null)) {
        chartDatasets.push({
            label: 'Zero-Shot Baseline',
            data: baseData,
            backgroundColor: 'rgba(156, 163, 175, 0.08)',
            borderColor: '#9ca3af',
            borderWidth: 1.5,
            borderDash: [5, 5],
            pointBackgroundColor: '#9ca3af',
            pointRadius: 3,
            pointHoverRadius: 5,
        });
    }

    const chart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels,
            datasets: chartDatasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: chartDatasets.length > 1, position: 'top' },
                tooltip: {
                    callbacks: {
                        label: item => `${item.label}: ${item.raw.toFixed(1)}%`
                    }
                }
            },
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        stepSize: 20,
                        callback: v => v + '%',
                        font: { size: 10 }
                    },
                    pointLabels: {
                        font: { family: "'Inter', sans-serif", size: 11 }
                    },
                    grid: { color: '#e5e7eb' },
                    angleLines: { color: '#e5e7eb' }
                }
            }
        }
    });
    App.chartInstances.push(chart);
}
