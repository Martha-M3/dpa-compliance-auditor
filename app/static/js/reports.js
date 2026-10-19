// Small helpers for the reports page. The page still works without this file:
// it only submits the filters when one is changed, and makes whole rows clickable.
(function () {
  // Apply the filters as soon as a drop-down changes (no Apply button needed).
  var form = document.getElementById("filter-form");
  if (form) {
    form.querySelectorAll("select").forEach(function (select) {
      select.addEventListener("change", function () { form.submit(); });
    });
  }

  // Clicking anywhere on a row previews that report.
  document.querySelectorAll(".rp-table tbody tr[data-href]").forEach(function (row) {
    row.addEventListener("click", function (event) {
      if (event.target.closest("a")) { return; }   // a real link was clicked: let it work
      window.location.href = row.dataset.href;
    });
  });
})();