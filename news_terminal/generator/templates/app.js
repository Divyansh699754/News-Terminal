/* News Terminal — Ground News inspired UI */

(function () {
  "use strict";

  var allArticles = [];
  var briefData = null;
  var scoreboardData = null;
  var clusterAlerts = [];
  var activeCategory = "me";  // Start on ME tab
  var activePriority = "all";
  var searchQuery = "";
  var activeCluster = null;
  var currentPage = 1;
  var PAGE_SIZE = 18;

  // ── Theme ──
  function initTheme() {
    var saved = localStorage.getItem("nt-theme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    else if (window.matchMedia("(prefers-color-scheme: dark)").matches) document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.setAttribute("data-theme", "light");
  }

  function toggleTheme() {
    var cur = document.documentElement.getAttribute("data-theme");
    var next = cur === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("nt-theme", next);
  }

  // ── Data ──
  async function loadData() {
    for (var s of ["morning", "evening"]) {
      try {
        var r = await fetch("data/" + s + ".json");
        if (r.ok) {
          var d = await r.json();
          allArticles = d.articles || [];
          briefData = d.brief || null;
          scoreboardData = d.thesis_scoreboard || null;
          clusterAlerts = d.cluster_alerts || [];
          return;
        }
      } catch (e) {}
    }
    allArticles = [];
  }

  // ── Helpers ──
  function timeAgo(d) {
    if (!d) return "";
    var s = Math.floor((new Date() - new Date(d)) / 1000);
    if (s < 60) return "just now";
    if (s < 3600) return Math.floor(s / 60) + "m";
    if (s < 86400) return Math.floor(s / 3600) + "h";
    return Math.floor(s / 86400) + "d";
  }

  function esc(s) { var d = document.createElement("div"); d.textContent = s || ""; return d.innerHTML; }

  function biasToPercents(bias) {
    if (!bias) return null;
    var rating = (bias.source_rating || "center").toLowerCase();
    var map = {
      "left": [70, 20, 10], "center-left": [50, 35, 15], "center": [25, 50, 25],
      "center-right": [15, 35, 50], "right": [10, 20, 70], "neutral": [30, 40, 30], "unknown": [33, 34, 33]
    };
    return map[rating] || map["center"];
  }

  // ── Hero Card ──
  function renderHeroCard(a) {
    var p = (a.priority || "MEDIUM").toUpperCase();
    var img = a.image_url ? '<div class="hero-img-wrap"><img src="' + esc(a.image_url) + '" alt="" loading="lazy" onerror="this.parentElement.style.display=\'none\'"></div>' : '';
    return '<div class="hero-card">' + img +
      '<div class="hero-content">' +
        '<div class="card-source-row"><span class="card-priority-flag ' + p.toLowerCase() + '" style="position:static">' + p + '</span> <span class="card-source-name">' + esc(a.source_name) + '</span> <span>' + timeAgo(a.published) + '</span></div>' +
        '<div class="hero-title"><a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></div>' +
        '<div class="hero-summary">' + esc(a.summary || "") + '</div>' +
      '</div></div>';
  }

  // ── Standard Card ──
  function renderCard(a) {
    var p = (a.priority || "MEDIUM").toUpperCase();
    var bias = a.bias || {};
    var biasRating = bias.source_rating || a.source_bias_rating || "unknown";
    var cs = a.cluster_size || 1;

    // LOW: compact
    if (p === "LOW") {
      return '<div class="article-card compact">' +
        '<span class="card-priority-flag low">LOW</span>' +
        '<span class="compact-source">' + esc(a.source_name) + '</span>' +
        '<a href="' + esc(a.url) + '" target="_blank" rel="noopener" class="compact-title">' + esc(a.title) + '</a>' +
        '<span class="compact-time">' + timeAgo(a.published) + '</span></div>';
    }

    // Image
    var img = a.image_url
      ? '<div class="card-img-wrap"><span class="card-priority-flag ' + p.toLowerCase() + '">' + p + '</span><img src="' + esc(a.image_url) + '" alt="" loading="lazy" onerror="this.parentElement.style.display=\'none\'"></div>'
      : '<div class="card-img-wrap" style="aspect-ratio:3/1;background:linear-gradient(135deg,var(--border),var(--bg))"><span class="card-priority-flag ' + p.toLowerCase() + '">' + p + '</span></div>';

    // Bias bar
    var bp = biasToPercents(bias);
    var biasBar = '';
    if (bp) {
      biasBar = '<div class="bias-bar-wrap">' +
        '<div class="bias-bar"><div class="bias-seg-left" style="width:' + bp[0] + '%"></div><div class="bias-seg-center" style="width:' + bp[1] + '%"></div><div class="bias-seg-right" style="width:' + bp[2] + '%"></div></div>' +
        '<div class="bias-labels"><span class="lbl-left">L ' + bp[0] + '%</span><span>' + esc(biasRating) + '</span><span class="lbl-right">R ' + bp[2] + '%</span></div></div>';
    }

    // Cluster
    var clusterTag = cs > 1
      ? '<span class="tag cluster-tag" onclick="filterByCluster(\'' + (a.cluster_id || "") + '\')">' + cs + ' outlets \u2014 compare</span>'
      : '';

    // Tags
    var tags = (a.country_tags || []).map(function(t) { return '<span class="tag">' + esc(t) + '</span>'; }).join('');
    if (a.weapon_category) tags += '<span class="tag">' + esc(a.weapon_category) + '</span>';

    // Framing
    var fHtml = "";
    if (bias.framing || (bias.loaded_language && bias.loaded_language.length) || bias.missing_context) {
      var fid = "f-" + a.id;
      fHtml = '<div class="card-actions"><button class="btn-link" onclick="toggleFraming(\'' + fid + '\')">View Framing Details</button></div>' +
        '<div class="framing-details" id="' + fid + '">' +
          (bias.framing ? '<dt>Framing</dt><dd>' + esc(bias.framing) + '</dd>' : '') +
          ((bias.loaded_language || []).length ? '<dt>Loaded Language</dt><dd>' + bias.loaded_language.map(esc).join(", ") + '</dd>' : '') +
          (bias.missing_context ? '<dt>Missing Context</dt><dd>' + esc(bias.missing_context) + '</dd>' : '') +
          (bias.emotional_intensity ? '<dt>Emotional Intensity</dt><dd>' + esc(bias.emotional_intensity) + '</dd>' : '') +
          (bias.note ? '<p style="margin-top:8px;font-size:11px;color:var(--text-muted)">' + esc(bias.note) + '</p>' : '') +
        '</div>';
    }

    return '<div class="article-card">' + img +
      '<div class="card-inner">' +
        '<div class="card-source-row"><span class="card-source-name">' + esc(a.source_name) + '</span> <span>\u00b7 ' + timeAgo(a.published) + '</span></div>' +
        '<div class="card-title"><a href="' + esc(a.url) + '" target="_blank" rel="noopener">' + esc(a.title) + '</a></div>' +
        '<div class="card-summary">' + esc(a.summary || "") + '</div>' +
        biasBar +
        '<div class="card-meta">' + tags + clusterTag + '<span>Relevance ' + (a.relevance_score || "?") + '/10</span></div>' +
      '</div>' +
      fHtml +
    '</div>';
  }

  // ── ME Tab Rendering ──
  function renderMeTab() {
    var html = '';

    // Decision Brief
    if (briefData) {
      var b = briefData;
      var threatColor = {green: "#16a34a", yellow: "#ca8a04", red: "#dc2626"}[b.threat_level] || "#6b7280";
      html += '<div class="me-brief">';
      html += '<div class="me-brief-header"><span class="me-label">DECISION BRIEF</span>';
      html += '<span class="me-threat" style="background:' + threatColor + '">' + (b.threat_level || "green").toUpperCase() + '</span></div>';
      html += '<h2 class="me-headline">' + esc(b.headline || "No brief generated yet") + '</h2>';

      if (b.threat_summary && b.threat_level !== "green") {
        html += '<div class="me-threat-detail">' + esc(b.threat_summary) + '</div>';
      }

      // Three Things
      if (b.three_things && b.three_things.length) {
        html += '<div class="me-three">';
        for (var i = 0; i < b.three_things.length; i++) {
          var t = b.three_things[i];
          html += '<div class="me-thing">';
          html += '<div class="me-thing-num">' + (i + 1) + '</div>';
          html += '<div class="me-thing-content">';
          html += '<div class="me-thing-signal">' + esc(t.signal || "") + '</div>';
          html += '<div class="me-thing-why">' + esc(t.why_it_matters_to_you || "") + '</div>';
          html += '<div class="me-thing-pivot"><strong>Pivot:</strong> ' + esc(t.pivot || "") + '</div>';
          html += '</div></div>';
        }
        html += '</div>';
      }

      // Thesis Updates
      if (b.thesis_updates && b.thesis_updates.length) {
        html += '<div class="me-thesis-updates"><h3>Thesis Updates</h3>';
        for (var j = 0; j < b.thesis_updates.length; j++) {
          var u = b.thesis_updates[j];
          var statusColor = {strengthened: "#16a34a", weakened: "#ca8a04", validated: "#2563eb", killed: "#dc2626"}[u.status] || "#6b7280";
          html += '<div class="me-thesis-update">';
          html += '<span class="me-thesis-status" style="background:' + statusColor + '">' + esc(u.status || "") + '</span>';
          html += '<span class="me-thesis-id">' + esc(u.thesis_id || "") + '</span>';
          html += '<span class="me-thesis-evidence">' + esc(u.evidence || "") + '</span>';
          html += '</div>';
        }
        html += '</div>';
      }

      html += '</div>';
    } else {
      html += '<div class="me-brief"><div class="me-brief-header"><span class="me-label">DECISION BRIEF</span></div>';
      html += '<h2 class="me-headline">No brief yet — run with Gemini API key to generate</h2>';
      html += '<p style="color:var(--text-muted);margin-top:8px">The brief is generated when articles match your profile in <code>config/profile.yaml</code></p></div>';
    }

    // Cluster Alerts
    if (clusterAlerts && clusterAlerts.length) {
      html += '<div class="me-cluster-alerts">';
      for (var ca = 0; ca < clusterAlerts.length; ca++) {
        var alert = clusterAlerts[ca];
        html += '<div class="me-cluster-alert">';
        html += '<div class="me-cluster-alert-header">';
        html += '<span class="me-threat" style="background:#dc2626">CLUSTER ALERT</span>';
        html += '<strong>' + alert.hit_count + ' signals</strong> in <strong>' + esc(alert.sector) + '</strong> within ' + alert.window_hours + 'h';
        html += '</div>';
        html += '<div class="me-cluster-articles">';
        for (var al = 0; al < (alert.articles || []).length; al++) {
          var art = alert.articles[al];
          html += '<a href="' + esc(art.url || "#") + '" target="_blank" rel="noopener" class="me-cluster-article-link">' + esc(art.title || "") + '</a>';
        }
        html += '</div></div>';
      }
      html += '</div>';
    }

    // Thesis Scoreboard
    if (scoreboardData && scoreboardData.length) {
      html += '<div class="me-scoreboard"><h3>Your Prediction Scoreboard</h3>';
      for (var k = 0; k < scoreboardData.length; k++) {
        var s = scoreboardData[k];
        html += '<div class="me-thesis-row">';
        html += '<div class="me-thesis-text">' + esc(s.thesis || "") + '</div>';
        html += '<div class="me-thesis-counts">';
        html += '<span class="me-count-for">+' + (s.evidence_for || 0) + ' for</span>';
        html += '<span class="me-count-against">-' + (s.evidence_against || 0) + ' against</span>';
        html += '<span class="me-thesis-badge">' + esc(s.status || "active") + '</span>';
        html += '</div></div>';
      }
      html += '</div>';
    }

    // Personal Articles (sorted by personal_score)
    var personal = allArticles.filter(function(a) { return (a.personal_score || 0) >= 3; });
    personal.sort(function(a, b) { return (b.personal_score || 0) - (a.personal_score || 0); });

    if (personal.length) {
      html += '<h3 class="me-section-title">Your Signals (' + personal.length + ' articles matched your profile)</h3>';
      html += '<div class="article-grid">';
      html += personal.slice(0, 20).map(renderCard).join("");
      html += '</div>';
    }

    return html;
  }

  // ── Filter ──
  function filterArticles() {
    return allArticles.filter(function (a) {
      if (activeCluster) return a.cluster_id === activeCluster;
      if (activeCategory !== "all" && a.category !== activeCategory) return false;
      if (activePriority !== "all" && (a.priority || "MEDIUM") !== activePriority) return false;
      if (searchQuery) {
        var q = searchQuery.toLowerCase();
        var s = [a.title, a.summary, a.source_name, (a.country_tags || []).join(" "), a.weapon_category, ((a.entities || {}).organizations || []).join(" ")].join(" ").toLowerCase();
        if (s.indexOf(q) === -1) return false;
      }
      return true;
    });
  }

  // ── Render ──
  function render() {
    var container = document.getElementById("articles");
    var empty = document.getElementById("empty-state");
    var hero = document.getElementById("hero-section");
    var filtered = filterArticles();
    currentPage = 1;

    // ME tab: special rendering
    if (activeCategory === "me" && !searchQuery) {
      hero.innerHTML = "";
      container.innerHTML = renderMeTab();
      empty.style.display = "none";
      // Update ME tab count
      var meCount = allArticles.filter(function(a) { return (a.personal_score || 0) >= 3; }).length;
      var meEl = document.querySelector('[data-count-for="me"]');
      if (meEl) meEl.textContent = meCount;
      // Update other tab counts
      document.querySelectorAll("[data-count-for]").forEach(function (el) {
        var c = el.getAttribute("data-count-for");
        if (c === "me") return;
        el.textContent = c === "all" ? allArticles.length : allArticles.filter(function (a) { return a.category === c; }).length;
      });
      return;
    }

    if (!filtered.length) { container.innerHTML = ""; hero.innerHTML = ""; empty.style.display = "block"; return; }
    empty.style.display = "none";

    if (!activeCluster && activeCategory === "all" && !searchQuery && activePriority === "all") {
      hero.innerHTML = filtered.slice(0, 3).map(renderHeroCard).join("");
      renderPage(filtered.slice(3), container);
    } else {
      hero.innerHTML = "";
      if (activeCluster) {
        container.innerHTML = '<div class="cluster-back"><button class="btn-link" onclick="clearCluster()">\u2190 Back to all articles</button> | ' + filtered.length + ' outlets covering this story</div>' + filtered.map(renderCard).join("");
      } else {
        renderPage(filtered, container);
      }
    }

    document.querySelectorAll("[data-count-for]").forEach(function (el) {
      var c = el.getAttribute("data-count-for");
      el.textContent = c === "all" ? allArticles.length : allArticles.filter(function (a) { return a.category === c; }).length;
    });
  }

  function renderPage(articles, container) {
    var vis = articles.slice(0, currentPage * PAGE_SIZE);
    var rem = articles.length - vis.length;
    container.innerHTML = vis.map(renderCard).join("");
    if (rem > 0) container.innerHTML += '<button class="load-more" onclick="loadMore()">Load more (' + rem + ' remaining)</button>';
  }

  // ── Globals ──
  window.toggleFraming = function (id) { var e = document.getElementById(id); if (e) e.classList.toggle("open"); };
  window.filterByCluster = function (c) { if (c) { activeCluster = c; render(); } };
  window.clearCluster = function () { activeCluster = null; render(); };
  window.loadMore = function () {
    currentPage++;
    var f = filterArticles();
    var off = (!activeCluster && activeCategory === "all" && !searchQuery && activePriority === "all") ? 3 : 0;
    renderPage(f.slice(off), document.getElementById("articles"));
  };

  function initEvents() {
    document.getElementById("theme-toggle").addEventListener("click", toggleTheme);
    document.getElementById("tabs").addEventListener("click", function (e) {
      var b = e.target.closest(".tab"); if (!b) return;
      document.querySelectorAll(".tab").forEach(function (t) { t.classList.remove("active"); });
      b.classList.add("active"); activeCategory = b.getAttribute("data-category"); activeCluster = null; render();
    });
    var st;
    document.getElementById("search").addEventListener("input", function (e) {
      clearTimeout(st); st = setTimeout(function () { searchQuery = e.target.value.trim(); activeCluster = null; render(); }, 200);
    });
    document.getElementById("priority-filter").addEventListener("change", function (e) {
      activePriority = e.target.value; activeCluster = null; render();
    });
  }

  async function init() { initTheme(); initEvents(); await loadData(); render(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
