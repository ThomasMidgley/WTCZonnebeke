// Sprongregels: verbergt de vragen die door een antwoord overgeslagen worden.
// Werkt ook zonder JavaScript: dan zie je alle vragen en negeert de server de overgeslagen antwoorden.
(function () {
  document.querySelectorAll("form[data-jumps]").forEach(function (form) {
    var blocks = Array.prototype.slice.call(form.querySelectorAll(".question"));
    if (!blocks.length) return;

    function answerOf(block) {
      var inputs = block.querySelectorAll("input, select, textarea");
      var values = [];
      inputs.forEach(function (input) {
        if ((input.type === "radio" || input.type === "checkbox") && !input.checked) return;
        if (input.value) values.push(input.value.trim());
      });
      return values;
    }

    function rule(block) {
      var el = block.querySelector("[data-jump-to]");
      return el ? { answer: el.getAttribute("data-jump-answer"), to: parseInt(el.getAttribute("data-jump-to"), 10) } : null;
    }

    function update() {
      var visible = {};
      var index = 0;
      var guard = 0;
      while (index >= 0 && index < blocks.length && guard++ < 500) {
        visible[index] = true;
        var r = rule(blocks[index]);
        if (r && answerOf(blocks[index]).indexOf(r.answer) !== -1) {
          if (r.to === 0) break;
          index = Math.max(r.to - 1, index + 1);
        } else {
          index += 1;
        }
      }
      blocks.forEach(function (block, i) { block.hidden = !visible[i]; });
    }

    form.addEventListener("change", update);
    update();
  });
})();
