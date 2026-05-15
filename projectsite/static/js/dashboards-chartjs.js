/* Reals Food Products - Superuser Dashboard (Chart.js) */
(function () {
  'use strict';

  if (typeof Chart === 'undefined') {
    console.error('Chart.js not loaded');
    return;
  }

  var dataEl = document.getElementById('dashData');
  if (!dataEl) return;
  var D;
  try { D = JSON.parse(dataEl.textContent); } catch (e) { console.error('dashData parse', e); return; }

  // Theme defaults
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  var textColor = isDark ? '#e5e7eb' : '#374151';
  var gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';
  Chart.defaults.color = textColor;
  Chart.defaults.font.family = "'Inter','Segoe UI',system-ui,-apple-system,sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;

  var PALETTE = {
    primary: '#77b254', primary2: '#5a9340',
    blue: '#2563eb', blueLight: '#93c5fd',
    orange: '#ea580c', orangeLight: '#fdba74',
    green: '#16a34a', greenLight: '#86efac',
    red: '#dc2626', redLight: '#fca5a5',
    yellow: '#d97706', yellowLight: '#fcd34d',
    purple: '#9333ea', purpleLight: '#d8b4fe',
    teal: '#0d9488', pink: '#db2777', slate: '#64748b'
  };
  var CYCLE = [PALETTE.blue, PALETTE.primary, PALETTE.orange, PALETTE.purple, PALETTE.teal, PALETTE.pink, PALETTE.yellow, PALETTE.red, PALETTE.slate];

  var PH = '\u20B1';
  function peso(v) { try { return PH + Number(v).toLocaleString('en-PH', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); } catch (e) { return PH + v; } }
  function num(v) { try { return Number(v).toLocaleString('en-PH'); } catch (e) { return v; } }

  var moneyTickOpts = {
    ticks: { callback: function (v) { if (Math.abs(v) >= 1000) return PH + (v / 1000).toFixed(v >= 100000 ? 0 : 1) + 'k'; return PH + v; } },
    grid: { color: gridColor }
  };

  function mount(id, cfg) {
    var c = document.getElementById(id);
    if (!c) return null;
    return new Chart(c.getContext('2d'), cfg);
  }

  // 1) Sales vs Expenses (12mo) — bar + line combo
  mount('chartSalesExpenses', {
    type: 'bar',
    data: {
      labels: D.s12.labels,
      datasets: [
        { type: 'bar', label: 'Sales', data: D.s12.sales, backgroundColor: PALETTE.blue, borderRadius: 4, maxBarThickness: 22 },
        { type: 'bar', label: 'Expenses', data: D.s12.expenses, backgroundColor: PALETTE.orange, borderRadius: 4, maxBarThickness: 22 },
        { type: 'line', label: 'Profit', data: D.s12.profit, borderColor: PALETTE.green, backgroundColor: 'rgba(22,163,74,0.1)', tension: 0.35, borderWidth: 2.5, pointRadius: 3, pointBackgroundColor: PALETTE.green, fill: false, yAxisID: 'y' }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ': ' + peso(ctx.parsed.y); } } }
      },
      scales: { y: moneyTickOpts, x: { grid: { display: false } } }
    }
  });

  // 2) Stock Health doughnut
  mount('chartStockHealth', {
    type: 'doughnut',
    data: { labels: ['Healthy', 'Low', 'Out of Stock'], datasets: [{ data: D.stock, backgroundColor: [PALETTE.green, PALETTE.yellow, PALETTE.red], borderWidth: 0, hoverOffset: 6 }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '65%',
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: function (ctx) { return ctx.label + ': ' + num(ctx.parsed); } } }
      }
    }
  });

  // 3) Revenue Trend (30d) — line + MA7
  mount('chartRevenue30', {
    type: 'line',
    data: {
      labels: D.rev30.labels,
      datasets: [
        { label: 'Daily Revenue', data: D.rev30.values, borderColor: PALETTE.blue, backgroundColor: 'rgba(37,99,235,0.12)', tension: 0.35, fill: true, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2 },
        { label: '7-day MA', data: D.rev30.ma7, borderColor: PALETTE.orange, borderDash: [5, 4], tension: 0.3, fill: false, pointRadius: 0, pointHoverRadius: 3, borderWidth: 2 }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ': ' + peso(ctx.parsed.y); } } }
      },
      scales: { y: moneyTickOpts, x: { grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 8 } } }
    }
  });

  // 4) Top 10 Best Sellers — horizontal bar (revenue)
  mount('chartBestSellers', {
    type: 'bar',
    data: {
      labels: D.best.labels,
      datasets: [{ label: 'Revenue', data: D.best.revenue, backgroundColor: PALETTE.primary, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: function (ctx) { var q = D.best.qty[ctx.dataIndex] || 0; return peso(ctx.parsed.x) + '  (' + num(q) + ' units)'; }
        } }
      },
      scales: { x: moneyTickOpts, y: { grid: { display: false } } }
    }
  });

  // 5) Withdrawal Reasons — stacked bar (last 6 months)
  var reasonColors = { SOLD: PALETTE.green, EXPIRED: PALETTE.red, DAMAGED: PALETTE.orange, REPLACEMENT_FOR_RETURNED: PALETTE.purple, OTHERS: PALETTE.slate };
  mount('chartReasons', {
    type: 'bar',
    data: {
      labels: D.reasons.labels,
      datasets: D.reasons.datasets.map(function (ds) { return { label: ds.label, data: ds.data, backgroundColor: reasonColors[ds.key] || PALETTE.slate, borderRadius: 3, maxBarThickness: 34 }; })
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ': ' + num(ctx.parsed.y) + ' units'; } } } },
      scales: { x: { stacked: true, grid: { display: false } }, y: { stacked: true, grid: { color: gridColor }, beginAtZero: true } }
    }
  });

  // 6) Sales Channels pie
  mount('chartChannels', {
    type: 'pie',
    data: { labels: D.channels.labels, datasets: [{ data: D.channels.values, backgroundColor: CYCLE, borderWidth: 2, borderColor: isDark ? '#1b2228' : '#fff' }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: function (ctx) { return ctx.label + ': ' + peso(ctx.parsed); } } } }
    }
  });

  // 7) Expenses by Category — doughnut
  mount('chartExpCat', {
    type: 'doughnut',
    data: { labels: D.expcat.labels, datasets: [{ data: D.expcat.values, backgroundColor: CYCLE, borderWidth: 2, borderColor: isDark ? '#1b2228' : '#fff' }] },
    options: {
      responsive: true, maintainAspectRatio: false, cutout: '55%',
      plugins: { legend: { position: 'right' }, tooltip: { callbacks: { label: function (ctx) { return ctx.label + ': ' + peso(ctx.parsed); } } } }
    }
  });

  // 8) Payment Status — horizontal stacked bar (single row)
  mount('chartPayment', {
    type: 'bar',
    data: {
      labels: ['MTD Revenue'],
      datasets: [
        { label: 'Paid', data: [D.payment.values[0]], backgroundColor: PALETTE.green, borderRadius: 4 },
        { label: 'Partial', data: [D.payment.values[1]], backgroundColor: PALETTE.yellow, borderRadius: 4 },
        { label: 'Unpaid', data: [D.payment.values[2]], backgroundColor: PALETTE.red, borderRadius: 4 }
      ]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ': ' + peso(ctx.parsed.x); } } } },
      scales: { x: Object.assign({ stacked: true }, moneyTickOpts), y: { stacked: true, grid: { display: false } } }
    }
  });

  // 9) Low-Stock Watchlist — hbar with threshold overlay
  mount('chartLowStock', {
    type: 'bar',
    data: {
      labels: D.lowstock.labels,
      datasets: [
        { label: 'Current Stock', data: D.lowstock.stock, backgroundColor: D.lowstock.colors, borderRadius: 4 },
        { label: 'Threshold', data: D.lowstock.threshold, type: 'line', borderColor: PALETTE.slate, borderDash: [4, 4], backgroundColor: 'transparent', pointRadius: 0, borderWidth: 2 }
      ]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: function (ctx) { return ctx.dataset.label + ': ' + num(ctx.parsed.x); } } } },
      scales: { x: { beginAtZero: true, grid: { color: gridColor } }, y: { grid: { display: false } } }
    }
  });

  // 10) Raw Materials stock — hbar
  mount('chartRawMats', {
    type: 'bar',
    data: { labels: D.rawmats.labels, datasets: [{ label: 'Stock', data: D.rawmats.stock, backgroundColor: D.rawmats.colors, borderRadius: 4 }] },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: function (ctx) { return num(ctx.parsed.x); } } } },
      scales: { x: { beginAtZero: true, grid: { color: gridColor } }, y: { grid: { display: false } } }
    }
  });
})();
