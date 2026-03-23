/* EdgeCase Benchmark Explorer — Table View */

function categoryBadges(categories) {
    return (categories || []).map(cat => {
        let cls = 'badge ';
        const low = String(cat).toLowerCase();
        if (low === 'ethics') cls += 'badge-ethics';
        else if (low === 'reasoning') cls += 'badge-reasoning';
        else if (low === 'safety') cls += 'badge-safety';
        else if (low === 'regulation') cls += 'badge-regulation';
        else cls += 'badge-reasoning';
        return `<span class="${cls}">${escapeHtml(cat)}</span>`;
    }).join(' ');
}

function renderTableView(container) {
    const datasetCount = App.datasets.length;

    const rows = App.datasets.map(d => {
        const sourceLine = d.sourceNote
            ? `<div class="dataset-source">${escapeHtml(d.source || '')} ${escapeHtml(d.sourceNote || '')}</div>`
            : `<div class="dataset-source">${escapeHtml(d.source || '')}</div>`;

        const abbrev = d.abbrev || '';
        const license = d.license || '—';
        const description = d.description || '—';
        const taskType = d.taskType || '—';
        const questionCount = d.questionCount || 0;
        const categories = Array.isArray(d.categories) ? d.categories : [];

        return `<tr onclick="location.hash='#/explore/${d.id}'">
            <td>
                <div class="dataset-name">${escapeHtml(d.name || d.id)}</div>
                ${sourceLine}
            </td>
            <td class="abbrev-cell"><code>${escapeHtml(abbrev)}</code></td>
            <td class="license-text">${escapeHtml(license)}</td>
            <td class="dataset-description">${escapeHtml(description)}</td>
            <td>${escapeHtml(taskType)}</td>
            <td class="num">${formatNumber(questionCount)}</td>
            <td>${categoryBadges(categories)}</td>
        </tr>`;
    }).join('');

    const attributionItems = App.datasets
        .filter(d => d.source || d.license)
        .map(d => {
            const source = d.source || d.name || d.id;
            const sourceNote = d.sourceNote ? ` ${escapeHtml(d.sourceNote)}` : '';
            const license = d.license || '—';
            return `<li><strong>${escapeHtml(source)}</strong>${sourceNote} &middot; ${escapeHtml(license)}</li>`;
        })
        .join('');

    container.innerHTML = `
    <div class="table-view">
        <h2>Benchmark Datasets</h2>
        <p class="view-description">
            ${formatNumber(datasetCount)} dataset${datasetCount === 1 ? '' : 's'} currently loaded.
            Click any dataset to explore individual questions.
        </p>

        <div class="table-wrapper">
            <table class="dataset-table">
                <thead>
                    <tr>
                        <th>Dataset</th>
                        <th>Abbrev</th>
                        <th>License</th>
                        <th>Description</th>
                        <th>Task Type</th>
                        <th class="num">Questions</th>
                        <th>Category</th>
                    </tr>
                </thead>
                <tbody>${rows}</tbody>
            </table>
        </div>

        <div class="attribution">
            <h3>Sources &amp; Licenses</h3>
            <ul>
                ${attributionItems || '<li>No source metadata available.</li>'}
            </ul>
        </div>
    </div>`;
}