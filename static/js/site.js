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
