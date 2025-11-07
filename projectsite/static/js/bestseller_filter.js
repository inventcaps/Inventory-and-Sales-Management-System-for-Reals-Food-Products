document.addEventListener("DOMContentLoaded", function () {
  const monthFilter = document.getElementById("monthFilter");
  const contentContainer = document.getElementById("bestsellerContent");
  const filterInfo = document.getElementById("filterInfo");

  let timeout;

  function fetchBestsellers() {
    clearTimeout(timeout);
    timeout = setTimeout(() => {
      let url = "/best-seller-products/?";
      const params = new URLSearchParams(window.location.search);

      if (monthFilter && monthFilter.value) {
        params.set("month", monthFilter.value);
        params.delete("show_all");
      } else {
        params.delete("month");
      }

      if (!monthFilter.value && params.get('show_all')) {
        params.set('show_all', '1');
      }

      url += params.toString();

      fetch(url)
        .then(response => response.text())
        .then(html => {
          const parser = new DOMParser();
          const doc = parser.parseFromString(html, "text/html");

          const newContent = doc.querySelector("#bestsellerContent");
          if (newContent && contentContainer) {
            contentContainer.innerHTML = newContent.innerHTML;
          }

          const newFilterInfo = doc.querySelector("#filterInfo");
          if (newFilterInfo && filterInfo) {
            filterInfo.textContent = newFilterInfo.textContent;
          }
        })
        .catch(err => console.error("Error fetching bestsellers:", err));
    }, 300);
  }

  if (monthFilter) monthFilter.addEventListener("change", fetchBestsellers);
});

function toggleShowAll() {
  const params = new URLSearchParams(window.location.search);
  if (params.get('show_all')) {
    params.delete('show_all');
  } else {
    params.set('show_all', '1');
    params.delete('month');
  }
  window.location.href = window.location.pathname + '?' + params.toString();
}
