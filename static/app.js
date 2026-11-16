const state = {
  page: "dashboard",
  user: null,
  dashboard: null,
  waste: [],
  carbon: [],
  recycling: null,
  analytics: null,
  reports: [],
  collections: [],
  categories: [],
  authMode: "login",
};

const pageContent = document.getElementById("page-content");
const modalBackdrop = document.getElementById("modal-backdrop");
const modalContent = document.getElementById("modal-content");
const modalTitle = document.getElementById("modal-title");
const activityLabels = {
  car: "Car travel",
  bus: "Bus travel",
  electricity: "Electricity",
  flight: "Air travel",
};

const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character]);

const formatDate = (value, options = { month: "short", day: "numeric", year: "numeric" }) => {
  if (!value) return "—";
  const date = new Date(value.length === 10 ? `${value}T12:00:00` : value);
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, options).format(date);
};

const formatNumber = (value, digits = 1) => new Intl.NumberFormat(undefined, {
  maximumFractionDigits: digits,
}).format(Number(value) || 0);

const statusLabel = (status) => ({
  open: "Open", scheduled: "Scheduled", resolved: "Resolved",
  in_progress: "In progress", completed: "Completed",
}[status] || status);

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, {
      ...options,
      credentials: "same-origin",
      headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
    });
  } catch {
    throw new Error("Cannot reach EcoTrack. Check that the local server is running.");
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(payload.error || `Request failed (${response.status}).`);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function showAuth(mode = "login", message = "") {
  state.authMode = mode;
  document.body.classList.remove("authenticated");
  const isRegister = mode === "register";
  document.getElementById("auth-screen").innerHTML = `
    <div class="auth-shell">
      <section class="auth-story">
        <a class="brand auth-brand" href="/" aria-label="EcoTrack home">
          <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 32 32" fill="none"><path d="M25.6 6.4C15 6.4 8.1 10.8 8.1 18.1c0 3.7 2.8 6.2 6.1 6.2 7.6 0 11.4-7.9 11.4-17.9Z" fill="currentColor"/><path d="M6.5 26.4c-3-6.7 7.2-10.2 13.2-13.4" stroke="#fff" stroke-width="1.8" stroke-linecap="round"/></svg></span>
          <span class="brand-copy"><strong>ecotrack</strong><small>PERSONAL SUSTAINABILITY</small></span>
        </a>
        <div class="auth-story-content">
          <span class="auth-kicker"><span></span> YOUR IMPACT, MADE VISIBLE</span>
          <h1>A lighter footprint starts with knowing yours.</h1>
          <p>Bring your everyday choices into focus. Track waste, estimate your carbon footprint, and find your next practical step.</p>
          <div class="auth-highlights">
            <div><span class="auth-highlight-icon">↗</span><span><strong>See your progress</strong><small>Personal trends, not guesswork.</small></span></div>
            <div><span class="auth-highlight-icon">♧</span><span><strong>Find small wins</strong><small>Helpful ideas for everyday life.</small></span></div>
            <div><span class="auth-highlight-icon">⌂</span><span><strong>Your data stays yours</strong><small>Private, local-first tracking.</small></span></div>
          </div>
        </div>
        <span class="auth-story-foot">A little better, a little greener, every day.</span>
        <span class="auth-decoration auth-decoration-one"></span><span class="auth-decoration auth-decoration-two"></span>
      </section>
      <section class="auth-form-side">
        <div class="auth-mobile-brand"><span class="brand-mark">♧</span><strong>ecotrack</strong></div>
        <div class="auth-card">
          <span class="eyebrow">${isRegister ? "YOUR OWN PERSONAL ECO SPACE" : "WELCOME TO YOUR ECO SPACE"}</span>
          <h2>${isRegister ? "Create your account" : "Welcome back"}</h2>
          <p class="auth-intro">${isRegister ? "Start tracking the changes that matter to you." : "Sign in to pick up where you left off."}</p>
          ${message ? `<div class="auth-error" role="alert">${escapeHtml(message)}</div>` : ""}
          <form id="auth-form" data-auth-form="${isRegister ? "register" : "login"}">
            ${isRegister ? `<label class="form-field"><span>Your name</span><input name="display_name" maxlength="80" autocomplete="name" placeholder="How should we address you?" required></label>` : ""}
            <label class="form-field"><span>Email address</span><input name="email" type="email" maxlength="254" autocomplete="email" placeholder="you@example.com" required></label>
            <label class="form-field"><span>Password</span><input name="password" type="password" minlength="10" maxlength="128" autocomplete="${isRegister ? "new-password" : "current-password"}" placeholder="${isRegister ? "At least 10 characters" : "Your password"}" required></label>
            <p class="form-hint">${isRegister ? "Use at least 10 characters. Your password is stored as a secure hash." : "Your personal environmental data is private to your account."}</p>
            <button class="button button-primary auth-submit" type="submit">${isRegister ? "Create my account" : "Sign in"} <span aria-hidden="true">→</span></button>
          </form>
          <p class="auth-switch">${isRegister ? "Already have an account?" : "New to EcoTrack?"} <button type="button" data-auth-mode="${isRegister ? "login" : "register"}">${isRegister ? "Sign in" : "Create an account"}</button></p>
          <p class="auth-privacy">Your records are stored in the local EcoTrack database on this device.</p>
        </div>
      </section>
    </div>`;
  document.body.classList.remove("authenticated");
  document.querySelector("#auth-form input")?.focus();
}

async function bootstrap() {
  try {
    const result = await api("/api/auth/me");
    if (!result.user) {
      showAuth(result.registration_required ? "register" : "login");
      return;
    }
    state.user = result.user;
    await enterWorkspace();
  } catch (error) {
    if (error.status === 401) {
      showAuth("login");
      return;
    }
    showAuth("login", error.message);
  }
}

async function enterWorkspace() {
  document.body.classList.add("authenticated");
  document.getElementById("profile-name").textContent = state.user.display_name;
  document.getElementById("profile-email").textContent = state.user.email;
  document.getElementById("profile-avatar").textContent = state.user.display_name
    .split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  pageContent.innerHTML = '<div class="loading-state"><span class="spinner"></span> Preparing your personal dashboard…</div>';
  try {
    await refresh();
  } catch (error) {
    if (error.status === 401) {
      state.user = null;
      showAuth("login", "Your session expired. Please sign in again.");
      return;
    }
    pageContent.innerHTML = `${emptyState("!", "We couldn't load your workspace", error.message, '<button class="button button-secondary" type="button" id="retry">Try again</button>')}`;
    document.getElementById("retry").addEventListener("click", () => enterWorkspace());
  }
}

async function refresh() {
  const [dashboard, waste, carbon, recycling, analytics, reports, collections, categories] =
    await Promise.all([
      api("/api/dashboard"), api("/api/waste"), api("/api/carbon"), api("/api/recycling"),
      api("/api/analytics"), api("/api/reports"), api("/api/collections"), api("/api/categories"),
    ]);
  Object.assign(state, { dashboard, waste, carbon, recycling, analytics, reports, collections, categories });
  render();
}

function render() {
  const titles = {
    dashboard: "Overview", waste: "Waste log", carbon: "Carbon footprint",
    recycling: "Recycling", analytics: "Reports & analytics", reports: "Waste reports",
    recommendations: "Eco recommendations", collections: "Collections", profile: "Settings",
  };
  if (!state.user || !state.dashboard) return;
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.page === state.page);
  });
  document.getElementById("breadcrumb").textContent = titles[state.page] || "Overview";
  const action = document.getElementById("topbar-action");
  action.dataset.action = state.page === "carbon" ? "carbon"
    : state.page === "reports" ? "report"
      : state.page === "collections" ? "collection" : "waste";
  const actionNames = {
    carbon: "Log emissions", reports: "New report", collections: "Schedule pickup",
  };
  action.lastChild.textContent = ` ${actionNames[state.page] || "Log activity"}`;
  updateNotifications();
  if (state.page === "dashboard") renderDashboard();
  else if (state.page === "waste") renderWaste();
  else if (state.page === "carbon") renderCarbon();
  else if (state.page === "recycling") renderRecycling();
  else if (state.page === "analytics") renderAnalytics();
  else if (state.page === "recommendations") renderRecommendations();
  else if (state.page === "reports") renderReports();
  else if (state.page === "collections") renderCollections();
  else if (state.page === "profile") renderProfile();
}

function heading(kicker, title, subtitle, action = "") {
  return `<div class="page-heading"><div><div class="eyebrow">${kicker}</div><h1>${title}</h1><p>${subtitle}</p></div><div class="heading-actions">${action}</div></div>`;
}

function emptyState(icon, title, text, action = "") {
  return `<div class="empty-state"><div class="empty-illustration" aria-hidden="true">${icon}</div><h3>${title}</h3><p>${escapeHtml(text)}</p>${action}</div>`;
}

function metricCard(label, value, note, icon, color, suffix = "") {
  return `<article class="metric-card"><div class="metric-top"><span class="metric-label">${label}</span><span class="metric-icon ${color}" aria-hidden="true">${icon}</span></div>
    <div class="metric-value">${value}<span class="metric-suffix">${suffix}</span></div><div class="metric-note">${note}</div></article>`;
}

function renderDashboard() {
  const { summary, monthly, category_breakdown: categories, recent_activities: activities, recommendations: ideas } = state.dashboard;
  const score = summary.sustainability_score === null ? "—" : summary.sustainability_score;
  const cards = [
    metricCard("Sustainability score", score, summary.sustainability_score === null ? "Log activity to begin" : "Personal progress indicator", "✳", "green", summary.sustainability_score === null ? "" : "/100"),
    metricCard("Carbon this month", formatNumber(summary.month_carbon_kg), "Estimated kg CO₂e", "↗", "amber", " kg"),
    metricCard("Waste recorded", formatNumber(summary.waste_kg), `${summary.waste_entries} logged ${summary.waste_entries === 1 ? "entry" : "entries"}`, "♧", "blue", " kg"),
    metricCard("Waste diverted", `${formatNumber(summary.diversion_rate, 0)}%`, `${formatNumber(summary.recycled_kg)} kg recycled`, "⟳", "pink"),
  ].join("");
  const recommendationsHtml = ideas.map((idea, index) => `
    <article class="recommendation"><span class="recommendation-number">0${index + 1}</span><div class="recommendation-copy"><strong>${escapeHtml(idea.title)}</strong><p>${escapeHtml(idea.detail)}</p><button class="text-button" type="button" data-recommendation="${escapeHtml(idea.action)}">${escapeHtml(idea.action)} →</button></div></article>`).join("");
  const recent = activities.length ? activities.map((item) => {
    const title = item.kind === "carbon" ? activityLabels[item.title] || item.title : item.title;
    return `<div class="activity-row"><span class="activity-mark ${item.kind === "carbon" ? "activity-carbon" : "activity-waste"}">${item.kind === "carbon" ? "↗" : "♧"}</span><div class="activity-copy"><strong>${escapeHtml(title)}</strong><span>${formatDate(item.created_at)}</span></div><span class="activity-value">${formatNumber(item.quantity)} ${item.kind === "carbon" ? "kg CO₂e" : "kg"}</span></div>`;
  }).join("") : emptyState("✳", "Your story starts here", "Log a little activity to see your progress take shape.", '<button class="button button-primary" type="button" data-action="waste">Log first activity</button>');
  const categoryBars = categories.filter((item) => Number(item.weight_kg) > 0).slice(0, 4);
  const categoryPanel = categoryBars.length ? categoryBars.map((item) => `
    <div class="breakdown-item"><div class="breakdown-label"><span class="category-cell"><span class="category-dot" style="background:${escapeHtml(item.color)}"></span>${escapeHtml(item.name)}</span><strong>${formatNumber(item.weight_kg)} kg</strong></div><div class="progress-track"><div class="progress-fill" style="width:${Math.min(100, item.weight_kg / Math.max(...categoryBars.map((entry) => entry.weight_kg)) * 100)}%;background:${escapeHtml(item.color)}"></div></div></div>`).join("")
    : '<div class="subtle-empty">Your material breakdown will appear after your first waste entry.</div>';
  const collectionList = state.dashboard.upcoming_collections.length ? state.dashboard.upcoming_collections.map((item) => `
    <div class="collection-item"><div class="calendar-icon">${escapeHtml(formatDate(item.scheduled_date, { day: "2-digit", month: "short" }))}</div><div class="collection-info"><strong>${escapeHtml(item.area)}</strong><span>${escapeHtml(item.assigned_to)}</span></div><span class="status-badge status-${escapeHtml(item.status)}">${statusLabel(item.status)}</span></div>`).join("")
    : '<div class="subtle-empty">No community pickups scheduled.</div>';
  pageContent.innerHTML = `${heading("YOUR PERSONAL IMPACT", `Good to see you, ${escapeHtml(state.user.display_name.split(" ")[0])}.`, "Small choices add up. Here’s how your eco journey is going.", `<div class="date-pill"><span>●</span> ${formatDate(new Date().toISOString())}</div>`)}
    <section class="metrics" aria-label="Your environmental impact">${cards}</section>
    <div class="dashboard-grid impact-dashboard-grid">
      <div class="dashboard-main-column">
        <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Your impact over time</h2><div class="panel-subtitle">Monthly carbon emissions and waste, last 6 months</div></div><button class="text-button" type="button" data-page-link="analytics">Full analytics →</button></div>${renderTrendChart(monthly)}</section>
        <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Recent activity</h2><div class="panel-subtitle">Your latest recorded actions</div></div><button class="text-button" type="button" data-page-link="waste">View waste log →</button></div><div class="activity-list">${recent}</div></section>
      </div>
      <div class="right-stack impact-right-column">
        <section class="panel"><div class="panel-header"><div><h2 class="panel-title">A few ideas for you</h2><div class="panel-subtitle">Practical next steps, based on your logs</div></div><span class="idea-spark">✳</span></div><div class="recommendation-list">${recommendationsHtml}</div></section>
        <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Your waste mix</h2><div class="panel-subtitle">By recorded weight</div></div><button class="text-button" type="button" data-page-link="recycling">Recycling tips →</button></div><div class="breakdown">${categoryPanel}</div></section>
        <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Community pickups</h2><div class="panel-subtitle">Upcoming local collections</div></div><button class="text-button" type="button" data-page-link="collections">View all →</button></div><div class="collection-list">${collectionList}</div></section>
      </div>
    </div>
    <p class="estimate-note">Carbon figures are estimates using average activity factors. Your sustainability score is a personal progress indicator, not an official rating.</p>`;
}

function updateNotifications() {
  const count = state.dashboard.summary.open_reports + state.dashboard.summary.active_collections;
  const badge = document.getElementById("notification-count");
  badge.hidden = count === 0;
  badge.textContent = count > 9 ? "9+" : String(count);
  const items = state.dashboard.recent_activities.slice(0, 3).map((activity) => {
    const label = activity.kind === "carbon"
      ? activityLabels[activity.title] || activity.title
      : activity.title;
    return `<div class="notification-item"><span class="notification-item-icon ${activity.kind === "carbon" ? "activity-carbon" : "activity-waste"}">${activity.kind === "carbon" ? "↗" : "♧"}</span><span><strong>${escapeHtml(label)}</strong><small>${formatDate(activity.created_at)} · ${formatNumber(activity.quantity)} ${activity.kind === "carbon" ? "kg CO₂e" : "kg"}</small></span></div>`;
  }).join("");
  const community = count
    ? `<div class="notification-community"><strong>${count} community ${count === 1 ? "item needs" : "items need"} attention</strong><small>${state.dashboard.summary.open_reports} open reports · ${state.dashboard.summary.active_collections} active pickups</small><button type="button" data-page="reports">View community updates →</button></div>`
    : "";
  document.getElementById("notification-popover").innerHTML = `<div class="popover-heading"><strong>Notifications</strong><span>${items ? "Recent activity" : "You're all caught up"}</span></div>${community}${items || '<div class="popover-empty">Your latest recorded activity will appear here.</div>'}`;
}

function renderRecommendations() {
  const ideas = state.dashboard.recommendations;
  const cards = ideas.map((idea, index) => `
    <article class="idea-card"><span class="idea-number">0${index + 1}</span><div class="idea-card-content"><span class="eyebrow">PERSONALIZED NEXT STEP</span><h2>${escapeHtml(idea.title)}</h2><p>${escapeHtml(idea.detail)}</p><button class="button button-secondary" type="button" data-recommendation="${escapeHtml(idea.action)}">${escapeHtml(idea.action)} <span aria-hidden="true">→</span></button></div></article>`).join("");
  const typeCards = [
    ["Everyday habits", "Start with small changes to shopping, packaging, and food planning.", "Cut waste before it starts", "♧"],
    ["Smarter recycling", `${formatNumber(state.dashboard.summary.diversion_rate, 0)}% of your logged waste is currently marked recycled. Check local collection rules.`, "Explore recycling", "⟳"],
    ["Lower-carbon travel", "Try logging a commute or choosing a lower-impact option for one short journey.", "Log an activity", "↗"],
  ].map(([label, detail, action, icon]) => `<article class="recommendation-category"><span class="recommendation-category-icon">${icon}</span><div><h3>${label}</h3><p>${detail}</p><button class="text-button" type="button" data-recommendation="${action}">${action} →</button></div></article>`).join("");
  pageContent.innerHTML = `${heading("SMALL STEPS, REAL MOMENTUM", "Ideas for a lighter footprint", "Practical suggestions based on the waste and activities you’ve logged.", "")}
    <div class="recommendations-intro"><span class="idea-spark">✳</span><span><strong>Made for your eco journey</strong><small>These suggestions use your own recorded activity. They’re prompts, not promises of impact.</small></span></div>
    <section class="recommendation-feature-grid">${cards}</section>
    <section class="panel recommendation-categories-panel"><div class="panel-header"><div><h2 class="panel-title">Choose a place to start</h2><div class="panel-subtitle">A few low-pressure ways to make progress</div></div></div><div class="recommendation-category-grid">${typeCards}</div></section>
    <p class="estimate-note">Environmental outcomes depend on local infrastructure, personal circumstances, and the materials involved. Start with what’s practical for you.</p>`;
}

function renderTrendChart(monthly) {
  const width = 620;
  const height = 190;
  const chartTop = 13;
  const chartBottom = 148;
  const maximum = Math.max(1, ...monthly.flatMap((month) => [month.carbon_kg, month.waste_kg]));
  const groupWidth = width / monthly.length;
  const barWidth = Math.min(20, groupWidth * 0.23);
  const bars = monthly.map((month, index) => {
    const center = groupWidth * index + groupWidth / 2;
    const carbonHeight = (month.carbon_kg / maximum) * (chartBottom - chartTop);
    const wasteHeight = (month.waste_kg / maximum) * (chartBottom - chartTop);
    return `<rect x="${center - barWidth - 2}" y="${chartBottom - carbonHeight}" width="${barWidth}" height="${Math.max(carbonHeight, 1)}" rx="4" fill="#d49b56"><title>${escapeHtml(month.label)} carbon: ${formatNumber(month.carbon_kg)} kg CO₂e</title></rect>
      <rect x="${center + 2}" y="${chartBottom - wasteHeight}" width="${barWidth}" height="${Math.max(wasteHeight, 1)}" rx="4" fill="#64a67b"><title>${escapeHtml(month.label)} waste: ${formatNumber(month.waste_kg)} kg</title></rect>
      <text x="${center}" y="171" text-anchor="middle" class="chart-label">${escapeHtml(month.label)}</text>`;
  }).join("");
  const grid = [0, 1, 2, 3].map((line) => {
    const y = chartTop + (chartBottom - chartTop) * line / 3;
    return `<line x1="0" x2="${width}" y1="${y}" y2="${y}" class="chart-gridline"/>`;
  }).join("");
  return `<div class="chart-wrap"><div class="chart-legend"><span><i class="legend-dot legend-carbon"></i>Carbon (kg CO₂e)</span><span><i class="legend-dot legend-waste"></i>Waste (kg)</span></div><svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Bar chart comparing monthly carbon emissions and waste for the last six months">${grid}${bars}</svg></div>`;
}

function renderWaste() {
  const rows = state.waste.map((item) => `
    <tr><td><span class="category-cell"><span class="category-dot" style="background:${escapeHtml(item.category_color)}"></span>${escapeHtml(item.category)}</span></td>
      <td class="table-number">${formatNumber(item.weight_kg)} kg</td><td class="table-number">${formatNumber(item.recycled_kg)} kg</td><td>${escapeHtml(item.note || "—")}</td><td>${formatDate(item.created_at)}</td>
      <td><span class="row-actions"><button class="row-edit" type="button" data-edit-waste="${item.id}" aria-label="Edit ${escapeHtml(item.category)} entry">Edit</button><button class="row-delete" type="button" data-delete-type="waste" data-delete-id="${item.id}" aria-label="Delete ${escapeHtml(item.category)} entry">×</button></span></td></tr>`).join("");
  const body = rows ? `<div class="toolbar"><span class="record-count">${state.waste.length} ${state.waste.length === 1 ? "entry" : "entries"}</span><span class="toolbar-spacer"></span><span class="form-hint">Only you can see your personal records.</span></div><div class="table-wrap"><table><thead><tr><th>CATEGORY</th><th>WASTE</th><th>RECYCLED</th><th>NOTE</th><th>DATE</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` :
    emptyState("♧", "Your waste log is ready", "Record waste by material and note how much you recycled. Your entries stay private to your account.", '<button class="button button-primary" type="button" data-action="waste">＋ Log household waste</button>');
  pageContent.innerHTML = `${heading("WASTE MANAGEMENT", "Your waste log", "Keep track of waste generated and the materials you keep in circulation.", `<button class="button button-primary" type="button" data-action="waste">＋ Log waste</button>`)}
    <section class="metrics compact-metrics">
      ${metricCard("Waste recorded", `${formatNumber(state.dashboard.summary.waste_kg)}<span class="metric-suffix"> kg</span>`, "Across all logged entries", "♧", "blue")}
      ${metricCard("Recycled", `${formatNumber(state.dashboard.summary.recycled_kg)}<span class="metric-suffix"> kg</span>`, "Kept out of general waste", "⟳", "green")}
      ${metricCard("Diversion rate", `${formatNumber(state.dashboard.summary.diversion_rate, 0)}<span class="metric-suffix">%</span>`, "Share of logged waste recycled", "✳", "amber")}
      ${metricCard("Waste entries", state.dashboard.summary.waste_entries, "Personal records", "▤", "pink")}</section>
    <section class="panel page-panel">${body}</section><p class="estimate-note">Waste amounts are based on the weights you enter. This log is for personal tracking and does not replace local waste reporting.</p>`;
}

function renderCarbon() {
  const rows = state.carbon.map((item) => `
    <tr><td><span class="activity-type-cell"><span class="activity-mark activity-carbon">↗</span>${escapeHtml(item.label || activityLabels[item.activity_type])}</span></td>
      <td class="table-number">${formatNumber(item.quantity)} ${escapeHtml(item.unit)}</td><td class="table-number carbon-number">${formatNumber(item.emissions_kg)} kg CO₂e</td>
      <td>${escapeHtml(item.note || "—")}</td><td>${formatDate(item.created_at)}</td>
      <td><button class="row-delete" type="button" data-delete-type="carbon" data-delete-id="${item.id}" aria-label="Delete ${escapeHtml(item.label || activityLabels[item.activity_type])} entry">×</button></td></tr>`).join("");
  const body = rows ? `<div class="toolbar"><span class="record-count">${state.carbon.length} ${state.carbon.length === 1 ? "activity" : "activities"}</span><span class="toolbar-spacer"></span><span class="form-hint">Estimated using average factors. Actual emissions vary.</span></div><div class="table-wrap"><table><thead><tr><th>ACTIVITY</th><th>AMOUNT</th><th>EST. EMISSIONS</th><th>NOTE</th><th>DATE</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>` :
    emptyState("↗", "Start your carbon footprint log", "Add everyday activities like travel or home electricity to see estimated CO₂e over time.", '<button class="button button-primary" type="button" data-action="carbon">＋ Log an activity</button>');
  pageContent.innerHTML = `${heading("CARBON FOOTPRINT", "Understand your emissions", "Track common activities and spot where small changes could make a difference.", `<button class="button button-primary" type="button" data-action="carbon">＋ Log activity</button>`)}
    <section class="metrics compact-metrics">
      ${metricCard("Estimated total", `${formatNumber(state.dashboard.summary.carbon_kg)}<span class="metric-suffix"> kg</span>`, "kg CO₂e across your log", "↗", "amber")}
      ${metricCard("This month", `${formatNumber(state.dashboard.summary.month_carbon_kg)}<span class="metric-suffix"> kg</span>`, "Estimated kg CO₂e", "◷", "green")}
      ${metricCard("Activities", state.dashboard.summary.carbon_entries, "Logged for your account", "▤", "blue")}
      ${metricCard("Recent log", rows ? formatDate(state.carbon[0].created_at, { month: "short", day: "numeric" }) : "—", "Most recent activity", "✳", "pink")}</section>
    <section class="panel page-panel">${body}</section>
    <section class="panel factor-panel"><div class="panel-header"><div><h2 class="panel-title">How estimates are calculated</h2><div class="panel-subtitle">Illustrative average factors used by this local tracker</div></div></div><div class="factor-grid">
      ${Object.entries({ car: "0.192 kg CO₂e / km", bus: "0.105 kg CO₂e / km", electricity: "0.400 kg CO₂e / kWh", flight: "0.150 kg CO₂e / passenger-km" }).map(([type, factor]) => `<div><span>${escapeHtml(activityLabels[type])}</span><strong>${factor}</strong></div>`).join("")}</div><p class="estimate-note">Factors are approximate examples, not location-specific or official emissions data. The factor used is saved with each calculation.</p></section>`;
}

function renderRecycling() {
  const guidance = state.recycling.guidance.map((item) => `
    <article class="guidance-card"><span class="guidance-category">${escapeHtml(item.category)}</span><p>${escapeHtml(item.detail)}</p></article>`).join("");
  const recent = state.recycling.recent.length ? state.recycling.recent.map((item) => `
    <div class="recycling-history-row"><span class="category-dot" style="background:${escapeHtml(item.category_color)}"></span><strong>${escapeHtml(item.category)}</strong><span>${formatNumber(item.recycled_kg)} kg recycled</span><time>${formatDate(item.created_at)}</time></div>`).join("")
    : emptyState("⟳", "No recycling entries yet", "Record recycled amounts in your waste log to track your diversion progress.", '<button class="button button-primary" type="button" data-action="waste">＋ Log waste & recycling</button>');
  pageContent.innerHTML = `${heading("RECYCLING MANAGEMENT", "Make more materials count", "Get practical sorting reminders and see what you've kept out of general waste.", `<button class="button button-primary" type="button" data-action="waste">＋ Log recycling</button>`)}
    <section class="recycling-summary">
      <article class="recycling-hero"><span class="eyebrow">YOUR DIVERSION PROGRESS</span><strong>${formatNumber(state.recycling.diversion_rate, 0)}<small>%</small></strong><p>${formatNumber(state.recycling.recycled_kg)} kg recycled out of ${formatNumber(state.recycling.waste_kg)} kg logged waste</p><div class="progress-track"><div class="progress-fill" style="width:${Math.min(100, state.recycling.diversion_rate)}%"></div></div></article>
      <article class="panel recycling-stat"><span class="metric-label">Materials recycled</span><strong>${formatNumber(state.recycling.recycled_kg)} <small>kg</small></strong><span class="form-hint">Across all your waste entries</span></article>
      <article class="panel recycling-stat"><span class="metric-label">Still in the mix</span><strong>${formatNumber(Math.max(0, state.recycling.waste_kg - state.recycling.recycled_kg))} <small>kg</small></strong><span class="form-hint">Logged but not marked recycled</span></article>
    </section>
    <section class="panel guidance-panel"><div class="panel-header"><div><h2 class="panel-title">A quick sorting guide</h2><div class="panel-subtitle">A starting point — accepted materials vary by local service.</div></div><span class="idea-spark">♧</span></div><div class="guidance-grid">${guidance}</div></section>
    <section class="panel recycling-history"><div class="panel-header"><div><h2 class="panel-title">Your recycling activity</h2><div class="panel-subtitle">Recycled amounts you've recorded</div></div><button class="text-button" type="button" data-page-link="waste">View waste log →</button></div>${recent}</section>
    <p class="estimate-note">Always check your local recycling provider’s rules. EcoTrack’s guide is general information, not a local collection schedule.</p>`;
}

function renderAnalytics() {
  const monthly = state.analytics.monthly;
  const categoryRows = state.analytics.waste_categories.filter((item) => Number(item.weight_kg) > 0);
  const maxWeight = Math.max(1, ...categoryRows.map((item) => item.weight_kg));
  const categoryContent = categoryRows.length ? categoryRows.map((item) => `
    <div class="analytics-category"><div class="breakdown-label"><span class="category-cell"><span class="category-dot" style="background:${escapeHtml(item.color)}"></span>${escapeHtml(item.name)}</span><strong>${formatNumber(item.weight_kg)} kg</strong></div><div class="progress-track"><div class="progress-fill" style="width:${item.weight_kg / maxWeight * 100}%;background:${escapeHtml(item.color)}"></div></div><span class="category-footnote">${formatNumber(item.recycled_kg)} kg recycled</span></div>`).join("")
    : '<div class="subtle-empty">Log waste to build your material breakdown.</div>';
  const emissionRows = state.analytics.carbon_activities.length ? state.analytics.carbon_activities.map((item) => `
    <tr><td>${escapeHtml(item.label)}</td><td>${item.entry_count}</td><td class="table-number">${formatNumber(item.emissions_kg)} kg CO₂e</td></tr>`).join("")
    : '<tr><td colspan="3" class="empty-cell">Log a carbon activity to see a breakdown.</td></tr>';
  pageContent.innerHTML = `${heading("PERSONAL REPORTING", "Your impact, in perspective", "Explore your six-month trends and export your personal activity data.", '<a class="button button-secondary download-button" href="/api/analytics.csv">↓ Export CSV</a>')}
    <section class="metrics compact-metrics">
      ${metricCard("Carbon footprint", `${formatNumber(state.dashboard.summary.carbon_kg)}<span class="metric-suffix"> kg</span>`, "Estimated total kg CO₂e", "↗", "amber")}
      ${metricCard("Waste generated", `${formatNumber(state.dashboard.summary.waste_kg)}<span class="metric-suffix"> kg</span>`, "Total recorded weight", "♧", "blue")}
      ${metricCard("Waste recycled", `${formatNumber(state.dashboard.summary.recycled_kg)}<span class="metric-suffix"> kg</span>`, `${formatNumber(state.dashboard.summary.diversion_rate, 0)}% diversion rate`, "⟳", "green")}
      ${metricCard("Entries logged", state.dashboard.summary.carbon_entries + state.dashboard.summary.waste_entries, "Across waste & carbon logs", "▤", "pink")}</section>
    <section class="panel analytics-chart-panel"><div class="panel-header"><div><h2 class="panel-title">Six-month activity</h2><div class="panel-subtitle">Monthly waste generated and estimated carbon emissions</div></div></div>${renderTrendChart(monthly)}</section>
    <div class="analytics-grid"><section class="panel"><div class="panel-header"><div><h2 class="panel-title">Waste by material</h2><div class="panel-subtitle">Total recorded weight and recycled share</div></div></div><div class="analytics-categories">${categoryContent}</div></section>
    <section class="panel"><div class="panel-header"><div><h2 class="panel-title">Estimated emissions by activity</h2><div class="panel-subtitle">Based on your saved activity records</div></div></div><div class="table-wrap"><table><thead><tr><th>ACTIVITY</th><th>ENTRIES</th><th>EST. EMISSIONS</th></tr></thead><tbody>${emissionRows}</tbody></table></div></section></div>
    <p class="estimate-note">Charts summarize activities you have logged in EcoTrack. Missing or estimated data is not a full lifecycle assessment or official sustainability report.</p>`;
}

function renderReports() {
  const rows = state.reports.map((report) => `
    <tr data-report-row data-search="${escapeHtml(`${report.title} ${report.category} ${report.location}`.toLowerCase())}" data-status="${escapeHtml(report.status)}">
      <td><div class="report-name">${escapeHtml(report.title)}</div><div class="panel-subtitle">${escapeHtml(report.location)}</div></td>
      <td><span class="category-cell"><span class="category-dot" style="background:${escapeHtml(report.category_color)}"></span>${escapeHtml(report.category)}</span></td>
      <td><span class="urgency-${escapeHtml(report.urgency)}">${escapeHtml(report.urgency[0].toUpperCase() + report.urgency.slice(1))}</span></td>
      <td><span class="status-badge status-${escapeHtml(report.status)}">${statusLabel(report.status)}</span></td><td>${formatDate(report.created_at)}</td>
      <td>${report.status !== "resolved" ? `<select class="status-select" aria-label="Update status for ${escapeHtml(report.title)}" data-report-status="${report.id}"><option value="">Update status</option>${["open", "scheduled", "resolved"].filter((status) => status !== report.status).map((status) => `<option value="${status}">${statusLabel(status)}</option>`).join("")}</select>` : "—"}</td></tr>`).join("");
  const table = rows ? `<div class="toolbar"><div class="search-field"><input id="report-search" type="search" placeholder="Search reports…" aria-label="Search reports"></div><select id="report-filter" aria-label="Filter reports by status"><option value="">All statuses</option><option value="open">Open</option><option value="scheduled">Scheduled</option><option value="resolved">Resolved</option></select><span class="toolbar-spacer"></span><span class="record-count">${state.reports.length} ${state.reports.length === 1 ? "report" : "reports"}</span></div><div class="table-wrap"><table><thead><tr><th>REPORT / LOCATION</th><th>CATEGORY</th><th>URGENCY</th><th>STATUS</th><th>REPORTED</th><th>ACTION</th></tr></thead><tbody>${rows}</tbody></table></div>` :
    emptyState("♧", "No community reports yet", "Keep your neighborhood informed by reporting waste that needs attention.", '<button class="button button-primary" type="button" data-action="report">＋ Create first report</button>');
  pageContent.innerHTML = `${heading("COMMUNITY FEEDBACK", "Neighborhood waste reports", "Track local waste issues and coordinate pickup follow-through.", `<button class="button button-primary" type="button" data-action="report">＋ New report</button>`)}<section class="panel page-panel">${table}</section>`;
}

function renderCollections() {
  const cards = state.collections.map((item) => `
    <article class="collection-card"><div class="collection-card-head"><div><h3>${escapeHtml(item.area)}</h3><p>${item.report_id ? `Linked to report #${item.report_id}` : "Neighborhood pickup"}</p></div><span class="status-badge status-${escapeHtml(item.status)}">${statusLabel(item.status)}</span></div>
      <div class="collection-meta"><div><span>PICKUP DATE</span><strong>${formatDate(item.scheduled_date)}</strong></div><div><span>ASSIGNED TEAM</span><strong>${escapeHtml(item.assigned_to)}</strong></div></div>
      ${item.status !== "completed" ? `<div class="card-actions"><select aria-label="Update pickup status for ${escapeHtml(item.area)}" data-collection-status="${item.id}"><option value="">Update status</option>${(item.status === "scheduled" ? ["in_progress", "completed"] : ["completed", "scheduled"]).map((status) => `<option value="${status}">${statusLabel(status)}</option>`).join("")}</select></div>` : ""}</article>`).join("");
  const body = cards ? `<div class="toolbar"><span class="record-count">${state.collections.length} ${state.collections.length === 1 ? "collection" : "collections"}</span><span class="toolbar-spacer"></span><span class="form-hint">Update a pickup’s status from its card.</span></div><div class="collection-cards">${cards}</div>` :
    emptyState("↗", "No collections scheduled", "Schedule a neighborhood pickup and assign a team to get things moving.", '<button class="button button-primary" type="button" data-action="collection">＋ Schedule collection</button>');
  pageContent.innerHTML = `${heading("COMMUNITY FEEDBACK", "Collection schedule", "Plan neighborhood pickups and track their progress.", `<button class="button button-primary" type="button" data-action="collection">＋ Schedule pickup</button>`)}<section class="panel page-panel">${body}</section>`;
}

function renderProfile() {
  pageContent.innerHTML = `${heading("YOUR ACCOUNT", "Profile settings", "Manage your EcoTrack account and password.", "")}
    <section class="panel profile-settings"><div class="panel-header"><div><h2 class="panel-title">Personal details</h2><div class="panel-subtitle">Your account is private to this local EcoTrack workspace.</div></div></div>
    <form id="profile-form" class="profile-form"><div class="form-grid">
      <label class="form-field"><span>Your name</span><input name="display_name" maxlength="80" value="${escapeHtml(state.user.display_name)}" required></label>
      <label class="form-field"><span>Email address</span><input name="email" type="email" maxlength="254" value="${escapeHtml(state.user.email)}" required></label>
      <div class="profile-divider"></div><div class="profile-password-title"><strong>Change password</strong><span>Leave these fields blank to keep your current password.</span></div>
      <label class="form-field"><span>Current password</span><input name="current_password" type="password" autocomplete="current-password"></label>
      <label class="form-field"><span>New password</span><input name="new_password" type="password" minlength="10" maxlength="128" autocomplete="new-password" placeholder="At least 10 characters"></label>
    </div><p class="form-error" id="profile-error" hidden></p><div class="form-actions"><button class="button button-primary" type="submit">Save changes</button></div></form></section>
    <section class="privacy-card"><span class="privacy-lock">⌑</span><div><strong>Your privacy matters</strong><p>EcoTrack stores your account and impact logs in a local SQLite database. Passwords are stored as salted, slow hashes. Keep your device secure and back up your data directory if needed.</p></div></section>`;
}

function openModal(type, entryId = null) {
  const titles = {
    waste: "Log household waste", carbon: "Log a carbon activity",
    report: "Report neighborhood waste", collection: "Schedule a collection",
    "edit-waste": "Edit waste entry",
  };
  modalTitle.textContent = titles[type] || titles.waste;
  const entry = type === "edit-waste" ? state.waste.find((item) => item.id === Number(entryId)) : null;
  if (type === "edit-waste" && !entry) {
    toast("This waste entry is no longer available.", true);
    return;
  }
  const categoryOptions = state.categories.map((item) => `<option value="${item.id}">${escapeHtml(item.name)}</option>`).join("");
  const reportOptions = state.reports.filter((item) => item.status !== "resolved")
    .map((item) => `<option value="${item.id}">${escapeHtml(item.title)}</option>`).join("");
  let form;
  if (type === "waste" || type === "edit-waste") {
    form = `<form id="action-form" data-form-type="${type}" data-entry-id="${entry?.id || ""}"><div class="form-grid">
      <label class="form-field"><span>Waste category</span><select name="category_id" required><option value="">Choose category</option>${categoryOptions}</select></label>
      <label class="form-field"><span>Total amount (kg)</span><input name="weight_kg" type="number" min="0.01" max="100000" step="0.01" placeholder="e.g. 2.5" value="${entry ? entry.weight_kg : ""}" required></label>
      <label class="form-field"><span>Amount recycled (kg)</span><input name="recycled_kg" type="number" min="0" max="100000" step="0.01" value="${entry ? entry.recycled_kg : "0"}" required><small>Cannot be greater than total waste.</small></label>
      <label class="form-field"><span>Date</span><input type="text" value="${formatDate(new Date().toISOString())}" disabled></label>
      <label class="form-field form-field-full"><span>Note <small>(optional)</small></span><input name="note" maxlength="300" placeholder="A short note to help you remember" value="${escapeHtml(entry?.note || "")}"></label>
    </div><p class="form-error" hidden></p><div class="form-actions"><button class="button button-secondary" type="button" data-close-modal>Cancel</button><button class="button button-primary" type="submit">${entry ? "Save changes" : "Save waste entry"}</button></div></form>`;
  } else if (type === "carbon") {
    form = `<form id="action-form" data-form-type="carbon"><div class="form-grid">
      <label class="form-field form-field-full"><span>Activity</span><select name="activity_type" id="carbon-activity-type" required>
        <option value="car">Car travel (km)</option><option value="bus">Bus travel (km)</option><option value="electricity">Home electricity (kWh)</option><option value="flight">Air travel (passenger-km)</option></select></label>
      <label class="form-field"><span>Amount</span><input name="quantity" type="number" min="0.01" max="1000000" step="0.01" placeholder="e.g. 12" required></label>
      <div class="factor-callout form-field"><span>Estimated factor</span><strong id="carbon-factor">0.192 kg CO₂e / km</strong></div>
      <label class="form-field form-field-full"><span>Note <small>(optional)</small></span><input name="note" maxlength="300" placeholder="An optional detail about this activity"></label>
    </div><p class="form-hint">Estimates use average factors and may differ from your actual footprint.</p><p class="form-error" hidden></p><div class="form-actions"><button class="button button-secondary" type="button" data-close-modal>Cancel</button><button class="button button-primary" type="submit">Calculate & save</button></div></form>`;
  } else if (type === "report") {
    form = `<form id="action-form" data-form-type="report"><div class="form-grid">
      <label class="form-field form-field-full"><span>What needs attention?</span><input name="title" maxlength="120" placeholder="e.g. Overflowing bins by the park" required></label>
      <label class="form-field"><span>Waste category</span><select name="category" required><option value="">Choose category</option>${categoryOptions}</select></label>
      <label class="form-field"><span>Urgency</span><select name="urgency"><option value="low">Low</option><option value="medium" selected>Medium</option><option value="high">High</option></select></label>
      <label class="form-field form-field-full"><span>Location</span><input name="location" maxlength="180" placeholder="Street, landmark, or neighborhood" required></label>
      <label class="form-field form-field-full"><span>A few more details</span><textarea name="description" maxlength="1000" placeholder="Share what you noticed." required></textarea></label>
    </div><p class="form-error" hidden></p><div class="form-actions"><button class="button button-secondary" type="button" data-close-modal>Cancel</button><button class="button button-primary" type="submit">Submit report</button></div></form>`;
  } else {
    form = `<form id="action-form" data-form-type="collection"><div class="form-grid">
      <label class="form-field form-field-full"><span>Pickup area</span><input name="area" maxlength="180" placeholder="Street or neighborhood" required></label>
      <label class="form-field"><span>Pickup date</span><input name="scheduled_date" type="date" min="${new Date().toISOString().slice(0, 10)}" required></label>
      <label class="form-field"><span>Assigned team</span><input name="assigned_to" maxlength="120" placeholder="e.g. Green Crew" required></label>
      <label class="form-field form-field-full"><span>Link to one of your reports <small>(optional)</small></span><select name="report_id"><option value="">No linked report</option>${reportOptions}</select></label>
    </div><p class="form-error" hidden></p><div class="form-actions"><button class="button button-secondary" type="button" data-close-modal>Cancel</button><button class="button button-primary" type="submit">Schedule pickup</button></div></form>`;
  }
  modalContent.innerHTML = form;
  if (entry && type === "edit-waste") {
    modalContent.querySelector('[name="category_id"]').value = String(entry.category_id);
  }
  modalBackdrop.hidden = false;
  document.body.style.overflow = "hidden";
  modalContent.querySelector("input,select")?.focus();
}

function closeModal() {
  modalBackdrop.hidden = true;
  document.body.style.overflow = "";
}

function toast(message, error = false) {
  const element = document.createElement("div");
  element.className = `toast${error ? " error" : ""}`;
  element.textContent = message;
  document.getElementById("toast-region").append(element);
  window.setTimeout(() => element.remove(), 3800);
}

async function submitActivityForm(form) {
  const type = form.dataset.formType;
  const data = Object.fromEntries(new FormData(form));
  const endpoints = { waste: "/api/waste", "edit-waste": `/api/waste/${form.dataset.entryId}`, carbon: "/api/carbon", report: "/api/reports", collection: "/api/collections" };
  if (type === "waste" || type === "edit-waste") data.category_id = Number(data.category_id);
  if (type === "carbon") data.quantity = Number(data.quantity);
  if (type === "report") data.category = Number(data.category);
  if (type === "collection" && data.report_id) data.report_id = Number(data.report_id);
  const submitButton = form.querySelector('[type="submit"]');
  const previousLabel = submitButton.textContent;
  submitButton.disabled = true;
  submitButton.textContent = "Saving…";
  const errorElement = form.querySelector(".form-error");
  errorElement.hidden = true;
  try {
    await api(endpoints[type], {
      method: type === "edit-waste" ? "PATCH" : "POST",
      body: JSON.stringify(data),
    });
    closeModal();
    await refresh();
    toast({
      waste: "Waste entry saved.", "edit-waste": "Waste entry updated.", carbon: "Activity saved and emissions estimated.",
      report: "Community report submitted.", collection: "Pickup scheduled.",
    }[type]);
  } catch (error) {
    errorElement.textContent = error.message;
    errorElement.hidden = false;
    submitButton.disabled = false;
    submitButton.textContent = previousLabel;
  }
}

async function updateStatus(resource, id, status, control) {
  if (!status) return;
  control.disabled = true;
  try {
    await api(`/api/${resource}/${id}`, { method: "PATCH", body: JSON.stringify({ status }) });
    await refresh();
    toast(`${resource === "reports" ? "Report" : "Pickup"} marked ${statusLabel(status).toLowerCase()}.`);
  } catch (error) {
    control.disabled = false;
    control.value = "";
    toast(error.message, true);
  }
}

function togglePopover(popoverId, buttonId) {
  const popover = document.getElementById(popoverId);
  const button = document.getElementById(buttonId);
  const opening = popover.hidden;
  document.querySelectorAll(".topbar-popover").forEach((item) => { item.hidden = true; });
  document.querySelectorAll("#notification-button, #profile-menu-button").forEach((item) => {
    item.setAttribute("aria-expanded", "false");
  });
  popover.hidden = !opening;
  button.setAttribute("aria-expanded", String(opening));
}

async function deleteEntry(type, id) {
  const label = type === "waste" ? "waste" : "carbon";
  if (!window.confirm(`Delete this ${label} entry? This cannot be undone.`)) return;
  try {
    await api(`/api/${type}/${id}`, { method: "DELETE" });
    await refresh();
    toast("Entry deleted.");
  } catch (error) {
    toast(error.message, true);
  }
}

async function submitAuthForm(form) {
  const mode = form.dataset.authForm;
  const data = Object.fromEntries(new FormData(form));
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  button.textContent = mode === "register" ? "Creating account…" : "Signing in…";
  try {
    const result = await api(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify(data) });
    state.user = result.user;
    await enterWorkspace();
  } catch (error) {
    showAuth(mode, error.message);
  }
}

async function submitProfileForm(form) {
  const data = Object.fromEntries(new FormData(form));
  const errorElement = document.getElementById("profile-error");
  errorElement.hidden = true;
  const button = form.querySelector('[type="submit"]');
  button.disabled = true;
  try {
    const result = await api("/api/profile", { method: "PATCH", body: JSON.stringify(data) });
    state.user = result.user;
    await enterWorkspace();
    state.page = "profile";
    render();
    toast("Profile saved.");
  } catch (error) {
    errorElement.textContent = error.message;
    errorElement.hidden = false;
    button.disabled = false;
  }
}

async function signOut() {
  try {
    await api("/api/auth/logout", { method: "POST", body: "{}" });
  } catch (error) {
    toast(error.message, true);
  }
  state.user = null;
  state.dashboard = null;
  showAuth("login");
}

function filterReports() {
  const query = document.getElementById("report-search")?.value.trim().toLowerCase() || "";
  const status = document.getElementById("report-filter")?.value || "";
  document.querySelectorAll("[data-report-row]").forEach((row) => {
    row.hidden = !(row.dataset.search.includes(query) && (!status || row.dataset.status === status));
  });
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (target.closest("#notification-button")) {
    togglePopover("notification-popover", "notification-button");
    return;
  }
  if (target.closest("#profile-menu-button")) {
    togglePopover("profile-popover", "profile-menu-button");
    return;
  }
  const authMode = target.closest("[data-auth-mode]");
  if (authMode) {
    showAuth(authMode.dataset.authMode);
    return;
  }
  const pageButton = target.closest("[data-page], [data-page-link]");
  if (pageButton) {
    state.page = pageButton.dataset.page || pageButton.dataset.pageLink;
    document.getElementById("sidebar").classList.remove("open");
    document.querySelectorAll(".topbar-popover").forEach((item) => { item.hidden = true; });
    document.querySelectorAll("#notification-button, #profile-menu-button").forEach((item) => {
      item.setAttribute("aria-expanded", "false");
    });
    render();
  }
  const actionButton = target.closest("[data-action]");
  if (actionButton) openModal(actionButton.dataset.action);
  if (target.closest("[data-close-modal]") || target === modalBackdrop || target.closest("#modal-close")) closeModal();
  const recommendation = target.closest("[data-recommendation]");
  if (recommendation) {
    const action = recommendation.dataset.recommendation;
    if (action === "Explore recycling") {
      state.page = "recycling";
      render();
    } else {
      openModal(action.toLowerCase().includes("carbon") ? "carbon" : "waste");
    }
  }
  const deleteButton = target.closest("[data-delete-type]");
  if (deleteButton) deleteEntry(deleteButton.dataset.deleteType, deleteButton.dataset.deleteId);
  const editButton = target.closest("[data-edit-waste]");
  if (editButton) openModal("edit-waste", editButton.dataset.editWaste);
  if (!target.closest(".topbar-menu-wrap")) {
    document.querySelectorAll(".topbar-popover").forEach((item) => { item.hidden = true; });
    document.querySelectorAll("#notification-button, #profile-menu-button").forEach((item) => {
      item.setAttribute("aria-expanded", "false");
    });
  }
});

document.addEventListener("submit", (event) => {
  if (event.target.id === "auth-form") {
    event.preventDefault();
    submitAuthForm(event.target);
  } else if (event.target.id === "action-form") {
    event.preventDefault();
    submitActivityForm(event.target);
  } else if (event.target.id === "profile-form") {
    event.preventDefault();
    submitProfileForm(event.target);
  }
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (target.matches("[data-report-status]")) {
    updateStatus("reports", target.dataset.reportStatus, target.value, target);
  } else if (target.matches("[data-collection-status]")) {
    updateStatus("collections", target.dataset.collectionStatus, target.value, target);
  } else if (target.id === "report-filter") {
    filterReports();
  } else if (target.id === "carbon-activity-type") {
    const factors = {
      car: "0.192 kg CO₂e / km", bus: "0.105 kg CO₂e / km",
      electricity: "0.400 kg CO₂e / kWh", flight: "0.150 kg CO₂e / passenger-km",
    };
    document.getElementById("carbon-factor").textContent = factors[target.value];
  }
});

document.addEventListener("input", (event) => {
  if (event.target.id === "report-search") filterReports();
});

document.getElementById("menu-button").addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("open");
});
document.getElementById("signout-button").addEventListener("click", signOut);
document.getElementById("topbar-signout").addEventListener("click", signOut);
document.getElementById("modal-close").addEventListener("click", closeModal);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeModal();
});
document.getElementById("current-year").textContent = String(new Date().getFullYear());

bootstrap();
