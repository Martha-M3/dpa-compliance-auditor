// Small helpers for the upload page. The page still works without this file:
// it only adds drag-and-drop, shows the chosen file name, and stops double clicks.
(function () {
  var form = document.getElementById("upload-form");
  var input = document.getElementById("dataset-input");
  var zone = document.getElementById("dropzone");
  var chosen = document.getElementById("chosen-file");
  var button = document.getElementById("upload-button");
  if (!form || !input || !zone) { return; }

  // Show "Selected: filename.csv" under the Browse button.
  function showChosenFile() {
    chosen.textContent = input.files.length ? "Selected: " + input.files[0].name : "";
  }
  input.addEventListener("change", showChosenFile);

  // Highlight the drop zone while a file is dragged over it.
  ["dragenter", "dragover"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.add("dragging");
    });
  });
  ["dragleave", "drop"].forEach(function (name) {
    zone.addEventListener(name, function (event) {
      event.preventDefault();
      zone.classList.remove("dragging");
    });
  });

  // When a file is dropped, hand it to the hidden file input.
  zone.addEventListener("drop", function (event) {
    if (event.dataTransfer.files.length) {
      input.files = event.dataTransfer.files;
      showChosenFile();
    }
  });

  // Disable the button once the form is sent, so it cannot be submitted twice.
  form.addEventListener("submit", function () {
    button.disabled = true;
    button.textContent = "Uploading...";
  });
})();