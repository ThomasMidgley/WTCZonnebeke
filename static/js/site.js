// YouTube pas laden na een klik, via youtube-nocookie.com.
document.addEventListener("click", function (event) {
  var button = event.target.closest("[data-youtube]");
  if (!button) return;
  var iframe = document.createElement("iframe");
  iframe.src = "https://www.youtube-nocookie.com/embed/" + button.dataset.youtube + "?autoplay=1&rel=0";
  iframe.title = button.dataset.title || "Video";
  iframe.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
  iframe.allowFullscreen = true;
  button.replaceWith(iframe);
});

// Widget van Cyql pas laden na een klik (externe inhoud).
document.addEventListener("click", function (event) {
  var button = event.target.closest("[data-cyql-widget]");
  if (!button) return;
  var src = button.dataset.cyqlWidget;
  if (src.indexOf("https://dashboard.cyql.app/") !== 0) return;
  var script = document.createElement("script");
  script.async = true;
  script.src = src;
  document.body.appendChild(script);
  var note = button.nextElementSibling;
  if (note && note.classList.contains("meta")) note.remove();
  button.remove();
});
