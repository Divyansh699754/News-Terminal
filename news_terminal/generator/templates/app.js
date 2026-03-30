/* News Terminal — Ground News inspired UI */

(function () {
  "use strict";

  var allArticles = [];
  var briefData = null;
  var scoreboardData = null;
  var clusterAlerts = [];
  var profileData = null;
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
          profileData = d.profile || null;
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
  function _findArticleBySignal(signal) {
    if (!signal) return null;
    var sigWords = signal.toLowerCase().replace(/[^a-z0-9 ]/g, '').split(' ').filter(function(w) { return w.length > 3; });
    if (sigWords.length < 2) return null;

    var best = null;
    var bestScore = 0;
    for (var i = 0; i < allArticles.length; i++) {
      var a = allArticles[i];
      var target = ((a.title || '') + ' ' + (a.summary || '')).toLowerCase();
      var hits = 0;
      for (var w = 0; w < sigWords.length; w++) {
        if (target.indexOf(sigWords[w]) !== -1) hits++;
      }
      var score = hits / sigWords.length;
      if (score > bestScore && score >= 0.4) {
        bestScore = score;
        best = a;
      }
    }
    return best;
  }

  function renderMeTab() {
    var html = '';

    // ── Profile Header ──
    if (profileData) {
      html += '<div class="me-profile">';
      html += '<div class="me-profile-top">';
      html += '<div class="me-profile-identity">';
      html += '<h2 class="me-profile-name">' + esc(profileData.name || "Your") + '\'s Intelligence Dashboard</h2>';
      html += '<span class="me-profile-role">' + esc(profileData.role || "") + '</span>';
      html += '</div>';
      var personal = allArticles.filter(function(a) { return (a.personal_score || 0) >= 3; });
      html += '<div class="me-profile-stats">';
      html += '<div class="me-stat"><span class="me-stat-num">' + personal.length + '</span><span class="me-stat-label">Signals</span></div>';
      html += '<div class="me-stat"><span class="me-stat-num">' + (profileData.theses || []).length + '</span><span class="me-stat-label">Theses</span></div>';
      html += '<div class="me-stat"><span class="me-stat-num">' + (clusterAlerts || []).length + '</span><span class="me-stat-label">Alerts</span></div>';
      html += '</div></div>';

      // Sectors + Goals as pills
      html += '<div class="me-profile-tags">';
      (profileData.sectors || []).forEach(function(s) { html += '<span class="me-pill me-pill-sector">' + esc(s) + '</span>'; });
      html += '</div>';

      // Building
      if (profileData.building && profileData.building.length) {
        html += '<div class="me-profile-building">';
        (profileData.building || []).forEach(function(b) { html += '<span class="me-building-tag">Building: ' + esc(b) + '</span>'; });
        html += '</div>';
      }
      html += '</div>';
    }

    // ── Split screen: Brief (left) + Scoreboard (right) ──
    html += '<div class="me-split">';

    // LEFT: Decision Brief
    html += '<div class="me-brief">';
    if (briefData) {
      var b = briefData;
      var threatColor = {green: "#16a34a", yellow: "#ca8a04", red: "#dc2626"}[b.threat_level] || "#6b7280";
      var genLabel = b.generated_by === "local" ? "LOCAL ANALYSIS" : "AI BRIEF";
      html += '<div class="me-brief-header"><span class="me-label">DECISION BRIEF</span>';
      html += '<span class="me-gen-badge">' + genLabel + '</span>';
      html += '<span class="me-threat" style="background:' + threatColor + '">' + (b.threat_level || "green").toUpperCase() + '</span></div>';
      html += '<h2 class="me-headline">' + esc(b.headline || "No brief generated yet") + '</h2>';

      if (b.threat_summary && b.threat_level !== "green") {
        html += '<div class="me-threat-detail">' + esc(b.threat_summary) + '</div>';
      }

      if (b.three_things && b.three_things.length) {
        html += '<div class="me-three">';
        for (var i = 0; i < b.three_things.length; i++) {
          var t = b.three_things[i];
          var matchedArticle = _findArticleBySignal(t.signal);
          var signalLink = matchedArticle ? '<a href="' + esc(matchedArticle.url) + '" target="_blank" rel="noopener" class="me-thing-link">' + esc(t.signal || "") + ' &nearr;</a>' : esc(t.signal || "");
          html += '<div class="me-thing">';
          html += '<div class="me-thing-num">' + (i + 1) + '</div>';
          html += '<div class="me-thing-content">';
          html += '<div class="me-thing-signal">' + signalLink + '</div>';
          html += '<div class="me-thing-why">' + esc(t.why_it_matters_to_you || "") + '</div>';
          html += '<div class="me-thing-pivot"><strong>Pivot:</strong> ' + esc(t.pivot || "") + '</div>';
          html += '</div></div>';
        }
        html += '</div>';
      }

      if (b.thesis_updates && b.thesis_updates.length) {
        html += '<div class="me-thesis-updates"><h3>Thesis Updates From Today</h3>';
        for (var j = 0; j < b.thesis_updates.length; j++) {
          var u = b.thesis_updates[j];
          var statusColor = {strengthened: "#16a34a", weakened: "#ca8a04", validated: "#2563eb", killed: "#dc2626"}[u.status] || "#6b7280";
          var evidenceArticle = _findArticleBySignal(u.evidence);
          var evidenceHtml = evidenceArticle
            ? '<a href="' + esc(evidenceArticle.url) + '" target="_blank" rel="noopener" class="me-evidence-link">' + esc(u.evidence || "") + ' &nearr;</a>'
            : '<span class="me-thesis-evidence">' + esc(u.evidence || "") + '</span>';
          html += '<div class="me-thesis-update">';
          html += '<span class="me-thesis-status" style="background:' + statusColor + '">' + esc(u.status || "") + '</span>';
          html += '<span class="me-thesis-id">' + esc(u.thesis_id || "") + '</span>';
          html += evidenceHtml;
          html += '</div>';
        }
        html += '</div>';
      }
    } else {
      html += '<div class="me-brief-header"><span class="me-label">DECISION BRIEF</span></div>';
      html += '<h2 class="me-headline">No brief yet</h2>';
      html += '<p style="color:var(--text-muted);margin-top:8px">Run the pipeline to generate your personal brief</p>';
    }
    html += '</div>';

    // RIGHT: Prediction Scoreboard
    html += '<div class="me-scoreboard">';
    html += '<div class="me-brief-header"><span class="me-label">PREDICTION SCOREBOARD</span></div>';
    if (scoreboardData && scoreboardData.length) {
      for (var k = 0; k < scoreboardData.length; k++) {
        var s = scoreboardData[k];
        var total = (s.evidence_for || 0) + (s.evidence_against || 0);
        var forPct = total > 0 ? Math.round(((s.evidence_for || 0) / total) * 100) : 50;
        var againstPct = 100 - forPct;
        var statusColor = {active: "var(--text-muted)", validated: "#2563eb", killed: "#dc2626"}[s.status] || "var(--text-muted)";

        html += '<div class="me-sb-card">';
        html += '<div class="me-sb-status"><span class="me-thesis-badge" style="border:1px solid ' + statusColor + ';color:' + statusColor + '">' + esc(s.status || "active").toUpperCase() + '</span>';
        html += '<span class="me-sb-id">' + esc(s.thesis_id || "") + '</span></div>';
        html += '<div class="me-sb-thesis">' + esc(s.thesis || "") + '</div>';

        // Evidence bar
        html += '<div class="me-sb-bar-wrap">';
        html += '<div class="me-sb-bar">';
        html += '<div class="me-sb-bar-for" style="width:' + forPct + '%"></div>';
        html += '<div class="me-sb-bar-against" style="width:' + againstPct + '%"></div>';
        html += '</div>';
        html += '<div class="me-sb-bar-labels">';
        html += '<span class="me-count-for">' + (s.evidence_for || 0) + ' supporting</span>';
        html += '<span class="me-count-against">' + (s.evidence_against || 0) + ' contradicting</span>';
        html += '</div></div>';

        // Total + latest
        html += '<div class="me-sb-meta">';
        html += '<span>' + total + ' evidence entries</span>';
        if (s.latest_evidence && s.latest_evidence.length) {
          var latest = s.latest_evidence[0];
          html += '<a href="' + esc(latest.url || "#") + '" target="_blank" rel="noopener" class="me-sb-latest">Latest: ' + esc(latest.title || "").substring(0, 60) + (latest.title && latest.title.length > 60 ? "..." : "") + '</a>';
        }
        html += '</div>';
        html += '</div>';
      }
    } else {
      html += '<div class="me-sb-empty">';
      html += '<p>No predictions tracked yet.</p>';
      html += '<p style="font-size:12px;color:var(--text-muted)">Add theses to <code>config/profile.yaml</code> — the system tracks them against real-world events.</p>';
      html += '</div>';
    }
    html += '</div>';

    html += '</div>'; // close me-split

    // Cluster Alerts (full width below split)
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

    // Personal Articles (sorted by personal_score)
    var personal = allArticles.filter(function(a) { return (a.personal_score || 0) >= 3; });
    personal.sort(function(a, b) { return (b.personal_score || 0) - (a.personal_score || 0); });

    if (personal.length) {
      html += '<h3 class="me-section-title">Your Signals (' + personal.length + ' articles matched your profile)</h3>';
      html += '<div class="me-signals-grid">';
      html += personal.slice(0, 24).map(renderCard).join("");
      if (personal.length > 24) {
        html += '<button class="load-more" onclick="document.querySelector(\'.me-signals-grid\').innerHTML += allArticles.filter(function(a){return (a.personal_score||0)>=3}).sort(function(a,b){return (b.personal_score||0)-(a.personal_score||0)}).slice(24,48).map(renderCard).join(\'\');this.remove();">Load more (' + (personal.length - 24) + ' remaining)</button>';
      }
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
      // ME tab content is sections, not card grid — use a wrapper that overrides parent grid
      container.innerHTML = '<div class="me-container">' + renderMeTab() + '</div>';
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

    // Update priority dropdown with counts
    var priSel = document.getElementById("priority-filter");
    if (priSel) {
      var priCounts = {};
      allArticles.forEach(function(a) { var p = a.priority || "MEDIUM"; priCounts[p] = (priCounts[p] || 0) + 1; });
      priSel.options[0].text = "All Priorities (" + allArticles.length + ")";
      priSel.options[1].text = "Critical (" + (priCounts["CRITICAL"] || 0) + ")";
      priSel.options[2].text = "High (" + (priCounts["HIGH"] || 0) + ")";
      priSel.options[3].text = "Medium (" + (priCounts["MEDIUM"] || 0) + ")";
      priSel.options[4].text = "Low (" + (priCounts["LOW"] || 0) + ")";
    }
  }

  function renderPage(articles, container) {
    var vis = articles.slice(0, currentPage * PAGE_SIZE);
    var rem = articles.length - vis.length;
    container.innerHTML = vis.map(renderCard).join("");
    if (rem > 0) container.innerHTML += '<button class="load-more" onclick="loadMore()">Load more (' + rem + ' remaining)</button>';
  }

  // ── Newspaper Mode ──
  var newspaperMode = false;

  function renderNewspaper() {
    var priOrder = {CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3};
    var personal = allArticles.filter(function(a) { return (a.personal_score || 0) >= 3; });
    // Sort: priority first, then personal score
    personal.sort(function(a, b) {
      var pa = priOrder[a.priority || "MEDIUM"] || 2;
      var pb = priOrder[b.priority || "MEDIUM"] || 2;
      if (pa !== pb) return pa - pb;
      return (b.personal_score || 0) - (a.personal_score || 0);
    });
    var top20 = personal.slice(0, 20);
    if (!top20.length) top20 = allArticles.slice(0, 20);

    var today = new Date();
    var dateStr = today.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

    var html = '<div class="np">';

    // Masthead
    html += '<div class="np-masthead">';
    html += '<div class="np-rule-double"></div>';
    html += '<div class="np-masthead-inner">';
    html += '<span class="np-edition">Personal Edition</span>';
    html += '<h1 class="np-title">NEWS TERMINAL</h1>';
    html += '<span class="np-date">' + dateStr + '</span>';
    html += '</div>';
    html += '<div class="np-rule-double"></div>';
    html += '</div>';

    // Decision brief box
    if (briefData) {
      html += '<div class="np-brief-box">';
      html += '<div class="np-brief-label">INTELLIGENCE BRIEF</div>';
      html += '<div class="np-brief-headline">' + esc(briefData.headline || "") + '</div>';
      if (briefData.three_things) {
        for (var b = 0; b < briefData.three_things.length; b++) {
          html += '<div class="np-brief-item"><strong>' + (b+1) + '.</strong> ' + esc(briefData.three_things[b].signal || "") + '</div>';
        }
      }
      html += '</div>';
    }

    function npPriBadge(p) {
      var colors = {CRITICAL:"#B91C1C",HIGH:"#C2410C",MEDIUM:"#525252",LOW:"#78716C"};
      return '<span class="np-pri-badge" style="background:' + (colors[p] || colors.MEDIUM) + '">' + (p || "MEDIUM") + '</span>';
    }

    // Lead story (#1)
    if (top20.length > 0) {
      var lead = top20[0];
      html += '<div class="np-lead">';
      html += npPriBadge(lead.priority);
      html += '<h2 class="np-lead-headline">' + esc(lead.title) + '</h2>';
      html += '<div class="np-lead-meta">' + esc(lead.source_name) + ' &mdash; ' + timeAgo(lead.published) + '</div>';
      html += '<div class="np-lead-body">' + esc(lead.summary || "") + '</div>';
      html += '</div>';
      html += '<div class="np-rule"></div>';
    }

    // Secondary stories (#2-3) — two columns
    if (top20.length >= 3) {
      html += '<div class="np-two-col">';
      for (var s = 1; s <= 2; s++) {
        var a = top20[s];
        html += '<div class="np-col-story">';
        html += npPriBadge(a.priority);
        html += '<h3 class="np-col-headline">' + esc(a.title) + '</h3>';
        html += '<div class="np-col-meta">' + esc(a.source_name) + '</div>';
        html += '<div class="np-col-body">' + esc(a.summary || "") + '</div>';
        html += '</div>';
      }
      html += '</div>';
      html += '<div class="np-rule"></div>';
    }

    // Remaining stories (#4-20) — three columns
    var remaining = top20.slice(3);
    if (remaining.length) {
      html += '<div class="np-three-col">';
      for (var r = 0; r < remaining.length; r++) {
        var ar = remaining[r];
        html += '<div class="np-compact-story">';
        html += npPriBadge(ar.priority);
        html += '<h4 class="np-compact-headline"><a href="' + esc(ar.url) + '" target="_blank" rel="noopener">' + esc(ar.title) + '</a></h4>';
        html += '<div class="np-compact-meta">' + esc(ar.source_name) + ' &middot; ' + timeAgo(ar.published) + '</div>';
        html += '<div class="np-compact-summary">' + esc((ar.summary || "").substring(0, 120)) + (ar.summary && ar.summary.length > 120 ? "..." : "") + '</div>';
        html += '</div>';
      }
      html += '</div>';
    }

    // Footer
    html += '<div class="np-rule-double" style="margin-top:24px"></div>';
    html += '<div class="np-footer">Generated by News Terminal for Divyansh &mdash; ' + top20.length + ' stories from ' + allArticles.length + ' articles analyzed</div>';

    html += '</div>';
    return html;
  }

  window.toggleNewspaper = function () {
    newspaperMode = !newspaperMode;
    var btn = document.getElementById("newspaper-btn");
    var container = document.getElementById("articles");
    var hero = document.getElementById("hero-section");
    var empty = document.getElementById("empty-state");

    if (newspaperMode) {
      btn.classList.add("active");
      hero.innerHTML = "";
      empty.style.display = "none";
      container.innerHTML = '<div class="me-container">' + renderNewspaper() + '</div>';
    } else {
      btn.classList.remove("active");
      render();
    }
  };

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
      b.classList.add("active"); activeCategory = b.getAttribute("data-category"); activeCluster = null;
      newspaperMode = false; var nbtn = document.getElementById("newspaper-btn"); if (nbtn) nbtn.classList.remove("active");
      render();
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
