// Stockomgeving: +/- knoppen en bevestiging voor "Geleverd".
document.querySelectorAll("[data-step]").forEach(function (button) {
  button.addEventListener("click", function () {
    var input = document.getElementById("id_delta");
    input.value = (parseInt(input.value, 10) || 0) + parseInt(button.dataset.step, 10);
  });
});
document.querySelectorAll("form[data-confirm]").forEach(function (form) {
  form.addEventListener("submit", function (event) {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});
