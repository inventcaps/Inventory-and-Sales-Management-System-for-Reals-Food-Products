'use strict';

let bestSellerChart = null;
let inventoryChart  = null;

function isDarkMode() {
  return document.body.classList.contains('dark-layout');
}

function getThemeColors() {
  const dark = isDarkMode();
  return {
    text: dark ? '#b4b7bd' : '#5e5873',
    grid: dark ? '#3b4253' : '#ebe9f1'
  };
}

/* ── 1. Best Selling Products (horizontal bar, from API) ── */
(function loadBestSellers() {
  const now = new Date();
  fetch('/api/best-sellers/?year=' + now.getFullYear() + '&month=' + (now.getMonth() + 1))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      const el = document.querySelector('#bestSellerChart');
      if (!el) return;
      const t = getThemeColors();
      if (!data.data || !data.data.length) {
        el.innerHTML = '<p style="text-align:center;color:#9ca3af;padding:24px;font-size:0.85rem;">No sales data this month.</p>';
        return;
      }
      bestSellerChart = new ApexCharts(el, {
        chart: {
          type: 'pie',
          height: 300,
          foreColor: t.text
        },
        series: data.data,
        labels: data.labels,
        legend: {
          position: 'bottom',
          labels: { colors: t.text }
        },
        tooltip: {
          theme: isDarkMode() ? 'dark' : 'light'
        }
      });
      bestSellerChart.render();
    })
    .catch(function () {});
})();

/* ── 2. Inventory Overview (vertical bar, per-bar color) ── */
document.addEventListener('DOMContentLoaded', function () {
  const d  = window._inventoryData;
  const el = document.querySelector('#inventoryChart');
  if (!el || !d || !d.labels || !d.labels.length) return;

  const t = getThemeColors();

  inventoryChart = new ApexCharts(el, {
    chart: {
      type: 'bar',
      height: 380,
      foreColor: t.text,
      toolbar: { show: false },
      animations: { enabled: false }
    },
    series: [{ name: 'Stock', data: d.stocks }],
    colors: d.colors,
    plotOptions: {
      bar: {
        horizontal: false,
        columnWidth: '42%',
        borderRadius: 4,
        distributed: true
      }
    },
    dataLabels: {
      enabled: true,
      formatter: function (val) { return val > 0 ? val : 'Out'; },
      style: { fontSize: '13px', fontWeight: 700 },
      offsetY: -2
    },
    xaxis: {
      categories: d.labels,
      labels: {
        style: { colors: t.text, fontSize: '12px', fontWeight: 600 },
        rotate: -42,
        hideOverlappingLabels: true,
        trim: true,
        maxHeight: 100
      }
    },
    yaxis: {
      title: { text: 'Units', style: { color: t.text, fontSize: '13px', fontWeight: 700 } },
      labels: { style: { colors: t.text, fontSize: '12px', fontWeight: 600 } }
    },
    grid: { borderColor: t.grid },
    tooltip: {
      theme: isDarkMode() ? 'dark' : 'light',
      y: { formatter: function (val) { return val > 0 ? val + ' units' : 'Out of stock'; } }
    },
    legend: { show: false }
  });
  inventoryChart.render();
});
