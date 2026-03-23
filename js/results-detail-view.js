/* EdgeCase Benchmark Explorer — Model Detail View */

async function renderResultsDetailView(container, slug) {
    container.innerHTML = `
    <div class="results-view">
        <div class="breadcrumb">
            <a href="#/results">Results</a><span>&rsaquo;</span><span>Loading\u2026</span>
        </div>
        <p class="loading">Loading model details\u2026</p>
    </div>`;

    try {
        const summary = await loadSummary();
        const model = summary.models.find(m => m.slug === slug);
        if (!model) throw new Error('Model not found');
        renderDetailContent(container, model, summary);
    } catch (e) {
        container.innerHTML = `
        <div class="results-view">
            <div class="breadcrumb">
                <a href="#/results">Results</a><span>&rsaquo;</span><span>Not found</span>
            </div>
            <div class="results-placeholder">
                <p>Model not found. <a href="#/results">Back to results</a></p>
            </div>
        </div>`;
    }
}

function renderDetailContent(container, model, summary) {
    const catMap = summary.category_map;
    const totalTokens = model.total_input_tokens + model.total_output_tokens;

    // Dataset display names
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
                    <div class="cat-ds-bar" style="width:${pct}%;background:${cm.color || '#7c3aed'}"></div>
                </div>
                <span class="cat-ds-val">${pct.toFixed(1)}%</span>
            </div>`;
        }).join('');

        return `<div class="category-card" style="border-top-color:${cm.color || '#7c3aed'}">
            <div class="cat-card-header">
                <h4>${escapeHtml(cat)}</h4>
                <span class="cat-card-acc">${stats.accuracy.toFixed(1)}%</span>
            </div>
            <div class="cat-card-meta">${stats.correct}/${stats.total - stats.errors} correct</div>
            <div class="cat-ds-bars">${bars}</div>
        </div>`;
    }).join('');

    // Full dataset table
    const dsRows = model.datasets.map(d => {
        const acc = d.accuracy;
        const cls = acc >= 70 ? 'acc-high' : acc >= 40 ? 'acc-mid' : 'acc-low';
        const cats = d.categories.map(c => {
            const cm = catMap[c] || {};
            return `<span class="badge" style="background:${cm.bg || '#f3f4f6'};color:${cm.color || '#333'}">${escapeHtml(c)}</span>`;
        }).join(' ');
        return `<tr>
            <td class="ds-table-name">${escapeHtml(d.dataset_name)}</td>
            <td class="ds-table-cats">${cats}</td>
            <td class="heatmap-cell ${cls}">${acc.toFixed(1)}%</td>
            <td class="ds-table-num">${d.correct}/${d.total}</td>
            <td class="ds-table-num">${d.errors}</td>
            <td class="ds-table-num">${formatNumber(d.input_tokens + d.output_tokens)}</td>
        </tr>`;
    }).join('');

    container.innerHTML = `
    <div class="results-view">
        <div class="breadcrumb">
            <a href="#/results">Results</a><span>&rsaquo;</span><span>${modelLabel(model)}</span>
        </div>

        <div class="detail-header">
            <div class="detail-rank">#${model.rank}</div>
            <div>
                <h2>${modelLabel(model)}</h2>
                <p class="detail-model-path">${escapeHtml(model.model)}${model.reasoning === true ? ' &middot; reasoning on' + (model.reasoning_effort ? ' (effort: ' + escapeHtml(model.reasoning_effort) + ')' : '') : model.reasoning === false ? ' &middot; reasoning off' : ''}${model.params ? ' &middot; ' + model.params.total + 'B' + (model.params.arch === 'MoE' ? ' (' + model.params.active + 'B active, MoE)' : ' dense') : ''}</p>
            </div>
        </div>

        <div class="detail-stats-inline">
            <div class="stat-inline"><span class="stat-val-inline">${model.overall_accuracy.toFixed(1)}%</span> <span class="stat-lbl-inline">Accuracy</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${formatNumber(model.total_questions)}</span> <span class="stat-lbl-inline">Questions</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${formatNumber(totalTokens)}</span> <span class="stat-lbl-inline">Tokens</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${formatCost(model.total_cost_usd)}</span> <span class="stat-lbl-inline">Cost</span></div>
            <div class="stat-inline"><span class="stat-val-inline">${model.total_errors}</span> <span class="stat-lbl-inline">Errors</span></div>
            ${model.params ? `<div class="stat-inline"><span class="stat-val-inline">${model.params.total}B${model.params.arch === 'MoE' ? '/' + model.params.active + 'B' : ''}</span> <span class="stat-lbl-inline">Params${model.params.arch === 'MoE' ? ' (MoE)' : ''}</span></div>` : ''}
            ${model.temperature != null ? `<div class="stat-inline"><span class="stat-val-inline">${model.temperature}</span> <span class="stat-lbl-inline">Temp</span></div>` : ''}
            ${model.max_tokens != null ? `<div class="stat-inline"><span class="stat-val-inline">${formatNumber(model.max_tokens)}</span> <span class="stat-lbl-inline">Max Tokens</span></div>` : ''}
        </div>

        <div class="chart-card">
            <h3>Per-Dataset Accuracy</h3>
            <div class="radar-wrapper">
                <canvas id="radarChart"></canvas>
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
                        <th>Accuracy</th>
                        <th>Correct/Total</th>
                        <th>Errors</th>
                        <th>Tokens</th>
                    </tr>
                </thead>
                <tbody>${dsRows}</tbody>
            </table>
        </div>
    </div>`;

    // Radar chart
    buildRadarChart(model, catMap);
}

function buildRadarChart(model, catMap) {
    const ctx = document.getElementById('radarChart');
    if (!ctx || typeof Chart === 'undefined') return;

    const dsNames = {};
    for (const d of App.datasets) dsNames[d.id] = d.name;

    const labels = model.datasets.map(d => d.dataset_name);
    const data = model.datasets.map(d => d.accuracy);

    const chart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels,
            datasets: [{
                label: model.display_name,
                data,
                backgroundColor: 'rgba(124, 58, 237, 0.15)',
                borderColor: '#7c3aed',
                borderWidth: 2,
                pointBackgroundColor: '#7c3aed',
                pointRadius: 4,
                pointHoverRadius: 6,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: { display: false },
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
