/**
 * Dashboard Analytics
 */

'use strict';

(function () {
  // Detect dark mode
  const isDarkMode = () => document.documentElement.getAttribute('data-theme') === 'dark';
  
  // Get theme colors
  const getThemeColors = () => {
    if (isDarkMode()) {
      return {
        textColor: '#f1f8f4',
        gridColor: 'rgba(119, 178, 84, 0.2)',
        tooltipBg: 'rgba(26, 31, 32, 0.95)',
        tooltipText: '#f1f8f4'
      };
    }
    return {
      textColor: '#2f3e46',
      gridColor: '#e0e0e0',
      tooltipBg: '#ffffff',
      tooltipText: '#2f3e46'
    };
  };

  // Store chart instances globally so we can update them
  let salesExpensesChart = null;
  let bestSellerChart = null;
  let revenueChart = null;
  let allMonthlyData = null;

  const fmtPeso = v => '₱' + v.toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2});
  const summaryHtml = (cur, prev, hasPrev) => hasPrev
    ? `${fmtPeso(cur)} <span style="color:#b0b8c1;font-weight:400;">this month</span> &nbsp;·&nbsp; ${fmtPeso(prev)} <span style="color:#b0b8c1;font-weight:400;">last month</span>`
    : `${fmtPeso(cur)} <span style="color:#b0b8c1;font-weight:400;">year total</span>`;

  // Function to update all charts with new theme colors
  const updateChartsTheme = () => {
    const themeColors = getThemeColors();
    const commonOptions = {
      chart: {
        foreColor: themeColors.textColor
      },
      xaxis: {
        labels: {
          style: {
            colors: themeColors.textColor
          }
        }
      },
      yaxis: {
        labels: {
          style: {
            colors: themeColors.textColor
          }
        }
      },
      title: {
        style: {
          color: themeColors.textColor
        }
      },
      grid: {
        borderColor: themeColors.gridColor
      },
      tooltip: {
        theme: isDarkMode() ? 'dark' : 'light'
      },
      legend: {
        labels: {
          colors: themeColors.textColor
        }
      }
    };

    if (salesExpensesChart) {
      salesExpensesChart.updateOptions(commonOptions);
    }
    if (bestSellerChart) {
      bestSellerChart.updateOptions(commonOptions);
    }
    if (revenueChart) {
      revenueChart.updateOptions(commonOptions);
    }
  };

  // Listen for theme changes
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && mutation.attributeName === 'data-theme') {
        updateChartsTheme();
      }
    });
  });

  // Start observing theme changes
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['data-theme']
  });

  fetch("/api/sales-vs-expenses/")
    .then(res => res.json())
    .then(data => {
      const themeColors = getThemeColors();
      const hiddenSeries = new Set();

      function syncSummaryVisibility() {
        const salesHidden = hiddenSeries.has(0);
        const expensesHidden = hiddenSeries.has(1);
        const profitEl = document.getElementById('profitContainer');
        const expEl = document.getElementById('expensesContainer');
        const divEl = document.getElementById('summaryDivider');
        if (profitEl) profitEl.style.display = salesHidden ? 'none' : '';
        if (expEl) expEl.style.display = expensesHidden ? 'none' : '';
        if (divEl) divEl.style.display = (salesHidden || expensesHidden) ? 'none' : '';
      }

      const options = { 
        chart: {
          type: "bar",
          height: 350,
          foreColor: themeColors.textColor,
          toolbar: { show: false },
          events: {
            legendClick: function(chartContext, seriesIndex) {
              if (hiddenSeries.has(seriesIndex)) {
                hiddenSeries.delete(seriesIndex);
              } else {
                hiddenSeries.add(seriesIndex);
              }
              syncSummaryVisibility();
            }
          }
        },
        series: [],
        colors: ["#22c55e", "#ef4444"],
        plotOptions: {
          bar: {
            horizontal: false,
            columnWidth: "52%",
            borderRadius: 4,
            grouped: true
          }
        },
        dataLabels: { enabled: false },
        xaxis: {
          categories: [],
          labels: { style: { colors: themeColors.textColor } }
        },
        yaxis: {
          labels: {
            style: { colors: themeColors.textColor },
            formatter: val => "₱" + val.toLocaleString()
          }
        },
        tooltip: {
          theme: isDarkMode() ? 'dark' : 'light',
          y: { formatter: val => "₱" + val.toLocaleString() }
        },
        legend: {
          position: "top",
          labels: { colors: themeColors.textColor }
        },
        grid: { borderColor: themeColors.gridColor }
      };
      salesExpensesChart = new ApexCharts(document.querySelector("#salesExpensesChart"), options);
      salesExpensesChart.render();
      allMonthlyData = data;

      const yearSelect = document.querySelector("#yearFilter");
      const monthSelect = document.querySelector("#monthFilter");
      const revenueYearSelect = document.querySelector("#revenueYearFilter");

      const extractedYears = new Set();
      data.months.forEach(m => {
        if (m) extractedYears.add(m.slice(0, 4));
      });
      data.daily_dates.forEach(d => {
        if (d) extractedYears.add(d.slice(0, 4));
      });

      const now = new Date();
      const currentYearStr = now.getFullYear().toString();
      extractedYears.add(currentYearStr);

      const sortedYears = Array.from(extractedYears)
        .filter(Boolean)
        .sort((a, b) => parseInt(b, 10) - parseInt(a, 10));

      const updateSelectOptions = (selectEl, preferred) => {
        if (!selectEl) return;
        const previous = preferred || selectEl.value;
        selectEl.innerHTML = "";
        sortedYears.forEach(year => {
          const option = document.createElement("option");
          option.value = year;
          option.textContent = year;
          selectEl.appendChild(option);
        });
        const fallback = sortedYears.includes(currentYearStr) ? currentYearStr : sortedYears[0];
        if (sortedYears.includes(previous)) {
          selectEl.value = previous;
        } else if (fallback) {
          selectEl.value = fallback;
        }
      };

      updateSelectOptions(yearSelect);
      updateSelectOptions(revenueYearSelect);

      function updateChart() {
        const selectedYear = yearSelect.value;
        const selectedMonth = monthSelect.value;

        if (selectedMonth === "all") {
          const filteredMonths = data.months.filter(m => m.startsWith(selectedYear));
          const filteredSales = data.sales.filter((_, i) => data.months[i].startsWith(selectedYear));
          const filteredExpenses = data.expenses.filter((_, i) => data.months[i].startsWith(selectedYear));

          salesExpensesChart.updateOptions({
            series: [
              { name: "Sales", data: filteredSales },
              { name: "Expenses", data: filteredExpenses }
            ],
            xaxis: { categories: filteredMonths }
          });

          const tS = filteredSales.reduce((a, b) => a + b, 0);
          const tE = filteredExpenses.reduce((a, b) => a + b, 0);
          const el1 = document.getElementById('profitSummary');
          const el2 = document.getElementById('expensesSummary');
          if (el1) el1.innerHTML = summaryHtml(tS - tE, 0, false);
          if (el2) el2.innerHTML = summaryHtml(tE, 0, false);
        } else {
          const selected = `${selectedYear}-${selectedMonth}`;
          const filteredDates = data.daily_dates.filter(d => d.startsWith(selected));
          const filteredSales = data.sales_daily.filter((_, i) => data.daily_dates[i].startsWith(selected));
          const filteredExpenses = data.expenses_daily.filter((_, i) => data.daily_dates[i].startsWith(selected));

          const dayLabels = filteredDates.map(d => {
            const day = new Date(d).getDate();
            return `${day}`;
          });

          salesExpensesChart.updateOptions({
            series: [
              { name: "Sales", data: filteredSales },
              { name: "Expenses", data: filteredExpenses }
            ],
            xaxis: { categories: dayLabels }
          });

          const mIdx = data.months.indexOf(selected);
          const curS = mIdx >= 0 ? data.sales[mIdx] : filteredSales.reduce((a, b) => a + b, 0);
          const curE = mIdx >= 0 ? data.expenses[mIdx] : filteredExpenses.reduce((a, b) => a + b, 0);
          let pm = parseInt(selectedMonth) - 1, py = parseInt(selectedYear);
          if (pm === 0) { pm = 12; py--; }
          const prevKey = `${py}-${String(pm).padStart(2, '0')}`;
          const pIdx = data.months.indexOf(prevKey);
          const pS = pIdx >= 0 ? data.sales[pIdx] : 0;
          const pE = pIdx >= 0 ? data.expenses[pIdx] : 0;
          const el1 = document.getElementById('profitSummary');
          const el2 = document.getElementById('expensesSummary');
          if (el1) el1.innerHTML = summaryHtml(curS - curE, pS - pE, true);
          if (el2) el2.innerHTML = summaryHtml(curE, pE, true);
        }
      }

      yearSelect.addEventListener("change", updateChart);
      monthSelect.addEventListener("change", updateChart);

      const currentYear = now.getFullYear().toString();
      const currentMonth = String(now.getMonth() + 1).padStart(2, "0");

      if ([...yearSelect.options].some(opt => opt.value === currentYear)) {
        yearSelect.value = currentYear;
      }
      if ([...monthSelect.options].some(opt => opt.value === currentMonth)) {
        monthSelect.value = currentMonth;
      } else {
        monthSelect.value = "all";
      }

      updateChart();
    });


  function fetchBestSellers() {
    const now = new Date();
    const currentYear = now.getFullYear();
    const currentMonth = now.getMonth() + 1;
    
    fetch(`/api/best-sellers/?year=${currentYear}&month=${currentMonth}`)
      .then(res => res.json())
      .then(data => {
        const themeColors = getThemeColors();
        
        if (bestSellerChart) {
          bestSellerChart.updateSeries(data.data);
          bestSellerChart.updateOptions({
            labels: data.labels
          });
        } else {
          bestSellerChart = new ApexCharts(document.querySelector("#bestSellerChart"), {
            chart: { 
              type: "pie", 
              height: 300,
              foreColor: themeColors.textColor
            },
            series: data.data,
            labels: data.labels,
            legend: { 
              position: "bottom",
              labels: {
                colors: themeColors.textColor
              }
            },
            tooltip: {
              theme: isDarkMode() ? 'dark' : 'light'
            }
          });
          bestSellerChart.render();
        }
      });
  }
  
  fetchBestSellers();

  document.addEventListener("DOMContentLoaded", function () {
  const yearSelect = document.querySelector("#revenueYearFilter");
  const monthSelect = document.querySelector("#revenueMonthFilter");
  const now = new Date();
  const defaultYear = now.getFullYear().toString();

  const themeColors = getThemeColors();
  const options = {
    chart: {
      type: "bar",
      height: 350,
      toolbar: { show: true },
      zoom: { enabled: true },
      foreColor: themeColors.textColor
    },
    series: [{ name: "Revenue Change", data: [] }],
    xaxis: {
      categories: [],
      tickPlacement: "on",
      labels: {
        style: {
          colors: themeColors.textColor
        }
      }
    },
    yaxis: {
      labels: {
        style: {
          colors: themeColors.textColor
        }
      }
    },
    plotOptions: {
      bar: {
        columnWidth: "40%",
        distributed: false
      }
    },
    dataLabels: {
      enabled: true,
      formatter: val => `₱${val.toLocaleString()}`,
      style: {
        colors: [themeColors.textColor]
      }
    },
    title: { 
      text: "Revenue Change",
      style: {
        color: themeColors.textColor
      }
    },
    tooltip: {
      theme: isDarkMode() ? 'dark' : 'light',
      x: {
        formatter: val => val
      }
    },
    grid: {
      borderColor: themeColors.gridColor
    },
    legend: {
      labels: {
        colors: themeColors.textColor
      }
    }
  };
  revenueChart = new ApexCharts(document.querySelector("#revenueChangeChart"), options);
  revenueChart.render();

  function updateChart() {
    let selectedYear = yearSelect.value;
    let selectedMonth = monthSelect.value || "all";

    if (!selectedYear) {
      if (yearSelect.options.length) {
        selectedYear = yearSelect.options[0].value;
        yearSelect.value = selectedYear;
      } else {
        selectedYear = defaultYear;
      }
    }

    fetch(`/api/revenue-change/?year=${selectedYear}&month=${selectedMonth}`)
      .then(res => res.json())
      .then(data => {
        const labels = data.labels;
        const revenues = data.revenues;
        const formattedLabels = selectedMonth !== "all"
          ? labels.map(d => `${parseInt(d.split("-")[2], 10)}`)
          : labels.map(d => d);
        const monthNames = ["","January","February","March","April","May","June","July","August","September","October","November","December"];
        revenueChart.updateOptions({
          series: [{ name: "Sales", data: revenues }],
          xaxis: { categories: formattedLabels },
          title: {
            text: selectedMonth === "all"
              ? `Monthly Overview - ${selectedYear}`
              : `${monthNames[parseInt(selectedMonth, 10)]} ${selectedYear}`
          }
        });

        const totalRev = revenues.reduce((a, b) => a + b, 0);
        const el = document.getElementById('revenueSummary');
        if (el) {
          if (selectedMonth !== "all" && allMonthlyData) {
            let pm = parseInt(selectedMonth) - 1, py = parseInt(selectedYear);
            if (pm === 0) { pm = 12; py--; }
            const prevKey = `${py}-${String(pm).padStart(2, '0')}`;
            const pIdx = allMonthlyData.months.indexOf(prevKey);
            const prevRev = pIdx >= 0 ? allMonthlyData.sales[pIdx] : 0;
            el.innerHTML = summaryHtml(totalRev, prevRev, true);
          } else {
            el.innerHTML = summaryHtml(totalRev, 0, false);
          }
        }
      });
  }

  yearSelect.addEventListener("change", updateChart);
  monthSelect.addEventListener("change", updateChart);

  const currentYear = defaultYear;

  if ([...yearSelect.options].some(opt => opt.value === currentYear)) {
    yearSelect.value = currentYear;
  }
  monthSelect.value = "all";

  updateChart();
});

})();

