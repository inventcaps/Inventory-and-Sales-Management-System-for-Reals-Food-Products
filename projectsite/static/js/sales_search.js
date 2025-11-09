document.addEventListener("DOMContentLoaded", function () {
  // Check for success message after page reload
  const saleSuccess = sessionStorage.getItem('saleSuccess');
  if (saleSuccess) {
    showToast(saleSuccess, 'success');
    sessionStorage.removeItem('saleSuccess');
  }
  
  const categoryFilter = document.getElementById("categoryFilter");
  const dateFilter = document.getElementById("dateFilter");
  const tableBody = document.getElementById("salesTableBody");
  const pagination = document.querySelector(".pagination-container");
  const summaryContainer = document.getElementById("salesSummary");
  const currentMonthDisplay = document.getElementById("currentMonthDisplay");

  let timeout;

  function updateFilterInfo() {
    const now = new Date();
    const monthNames = ["January", "February", "March", "April", "May", "June",
      "July", "August", "September", "October", "November", "December"];
    
    if (dateFilter.value) {
      const [year, month] = dateFilter.value.split('-');
      const monthName = monthNames[parseInt(month) - 1];
      currentMonthDisplay.textContent = `${monthName} ${year}`;
    } else {
      const currentMonth = monthNames[now.getMonth()];
      const currentYear = now.getFullYear();
      currentMonthDisplay.textContent = `${currentMonth} ${currentYear}`;
    }
  }

  updateFilterInfo();

  function fetchSales(resetPage = true) {
    clearTimeout(timeout);
    timeout = setTimeout(() => {
      const params = new URLSearchParams(window.location.search);
      
      // Update or remove category filter
      if (categoryFilter.value) {
        params.set("category", categoryFilter.value);
      } else {
        params.delete("category");
      }
      
      // Update or remove month filter
      if (dateFilter.value) {
        params.set("month", dateFilter.value);
      } else {
        params.delete("month");
      }
      
      // Reset to page 1 when filters change
      if (resetPage) {
        params.delete("page");
      }

      const url = window.location.pathname + "?" + params.toString();
      
      // Use full page reload instead of AJAX to ensure get_queryset() runs
      window.location.href = url;
    }, 300);
  }

  // Event listeners
  categoryFilter.addEventListener("change", () => fetchSales(true));
  dateFilter.addEventListener("change", () => {
    updateFilterInfo();
    fetchSales(true);
  });
  
  // Handle pagination clicks
  document.addEventListener("click", function(e) {
    if (e.target.closest(".pagination a")) {
      e.preventDefault();
      const link = e.target.closest("a");
      const url = link.getAttribute("href");
      
      fetch(url)
        .then(response => response.text())
        .then(html => {
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, "text/html");

          // Replace table body
          const newRows = doc.querySelector("#salesTableBody");
          if (newRows) tableBody.innerHTML = newRows.innerHTML;

          // Replace pagination
          const newPagination = doc.querySelector(".pagination-container");
          if (newPagination && pagination) pagination.innerHTML = newPagination.innerHTML;

          // Replace summary
          const newSummary = doc.querySelector("#salesSummary");
          if (newSummary && summaryContainer) summaryContainer.innerHTML = newSummary.innerHTML;
          
          // Update URL without page reload
          window.history.pushState({}, '', url);
          
          // Scroll to top of table
          document.querySelector(".card").scrollIntoView({ behavior: "smooth" });
        })
        .catch(err => console.error("Error fetching sales:", err));
    }
  });
});
