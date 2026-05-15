/* Reals Food Products - Staff Dashboard (Chart.js) */
(function () {
  'use strict';
  if (typeof Chart === 'undefined') return;
  var el = document.getElementById('staffInvData');
  if (!el) return;
  var D;
  try { D = JSON.parse(el.textContent); } catch (e) { return; }

  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  Chart.defaults.color = isDark ? '#e5e7eb' : '#374151';
  Chart.defaults.font.family = "'Inter','Segoe UI',system-ui,-apple-system,sans-serif";

  var canvas = document.getElementById('chartStaffInventory');
  if (!canvas) return;
  new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: D.labels,
      datasets: [{ label: 'Stock', data: D.stocks, backgroundColor: D.colors, borderRadius: 4 }]
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: function (c) { return 'Stock: ' + c.parsed.x; } } }
      },
      scales: {
        x: { beginAtZero: true, grid: { color: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)' } },
        y: { grid: { display: false } }
      }
    }
  });
})();
