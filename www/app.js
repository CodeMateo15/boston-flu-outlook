// Shared hover and click layer for the inline-SVG charts.
//  - any element with data-tip shows the tooltip; the first line is the heading
//  - any element with data-area sends that area to Shiny (data-input names the
//    input, default "area_click"), so a map shape, a ranked row and a small
//    multiple all open the same neighborhood view
(function () {
  var tip = null;
  function el() {
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "viz-tip";
      document.body.appendChild(tip);
    }
    return tip;
  }
  function show(target, x, y) {
    var t = el();
    t.textContent = "";
    target.getAttribute("data-tip").split("\n").forEach(function (line, i) {
      var d = document.createElement("div");
      d.textContent = line;
      if (i === 0) d.className = "viz-tip-head";
      t.appendChild(d);
    });
    t.style.display = "block";
    move(x, y);
  }
  function move(x, y) {
    if (!tip || tip.style.display !== "block") return;
    var r = tip.getBoundingClientRect();
    var left = x + 14, top = y + 14;
    if (left + r.width > window.innerWidth - 8) left = x - r.width - 14;
    if (top + r.height > window.innerHeight - 8) top = y - r.height - 14;
    tip.style.left = Math.max(8, left) + "px";
    tip.style.top = Math.max(8, top) + "px";
  }
  function hide() { if (tip) tip.style.display = "none"; }

  document.addEventListener("mouseover", function (e) {
    var t = e.target.closest && e.target.closest("[data-tip]");
    if (!t) return;
    t.classList.add("hover");
    show(t, e.clientX, e.clientY);
  });
  document.addEventListener("mousemove", function (e) { move(e.clientX, e.clientY); });
  document.addEventListener("mouseout", function (e) {
    var t = e.target.closest && e.target.closest("[data-tip]");
    if (!t || (e.relatedTarget && t.contains(e.relatedTarget))) return;
    t.classList.remove("hover");
    hide();
  });
  document.addEventListener("scroll", hide, true);

  function pick(t) {
    if (!window.Shiny || !Shiny.setInputValue) return;
    Shiny.setInputValue(t.getAttribute("data-input") || "area_click",
                        t.getAttribute("data-area"), { priority: "event" });
  }
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest("[data-area]");
    if (t) { hide(); pick(t); }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Enter" && e.key !== " ") return;
    var t = e.target.closest && e.target.closest("[data-area]");
    if (t) { e.preventDefault(); pick(t); }
  });
})();
