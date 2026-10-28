/* ArbiScan Phase 20.2 — same-origin read-only browser client.
 * All untrusted API strings are assigned through textContent (never innerHTML).
 * Market decisions, financial calculations and stake allocation remain Python-owned.
 */
"use strict";

const API = "/api/v1";
const byId = (id) => document.getElementById(id);
const state = {
  mode: null,
  version: null,
  events: [],
  providers: [],
  quotes: [],
  opportunities: [],
  readiness: null,
  metrics: {},
  selected: null,
  loading: false,
  truncated: false,
};
const formatTime = new Intl.DateTimeFormat("nl-BE", { hour: "2-digit", minute: "2-digit" });
const formatStamp = new Intl.DateTimeFormat("nl-BE", {
  day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
});
const formatCount = new Intl.NumberFormat("nl-BE", { maximumFractionDigits: 0 });

function node(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined && value !== null) element.textContent = String(value);
  return element;
}
function append(parent, ...children) {
  parent.append(...children);
  return parent;
}
function safeNumber(value) {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  const result = Number(value);
  return Number.isFinite(result) ? result : null;
}
function pctText(decimalRate) {
  const value = safeNumber(decimalRate);
  return value === null ? "—" : new Intl.NumberFormat("nl-BE", {
    style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(value);
}
function stampText(raw) {
  if (!raw) return "Onbekend";
  const value = new Date(raw);
  return Number.isNaN(value.getTime()) ? "Onbekend" : formatStamp.format(value);
}
function shorten(value, max = 46) {
  const text = String(value ?? "—");
  return text.length > max ? text.slice(0, max - 1) + "…" : text;
}
function setText(id, value) { byId(id).textContent = String(value); }
function showNotice(type, title, text, tag) {
  const item = byId("data-notice");
  item.className = "notice " + type;
  setText("notice-title", title);
  setText("notice-text", text);
  setText("notice-tag", tag);
}
function alertError(message) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.hidden = false;
}
function clearError() { byId("toast").hidden = true; }

async function requestJson(path) {
  // This application never makes requests to vendor hosts or a second backend.
  if (!path.startsWith(API + "/") || path.startsWith("//")) {
    throw new Error("Niet-toegestane API-route");
  }
  const response = await fetch(path, {
    method: "GET", credentials: "omit", cache: "no-store",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("Lokale API-fout: HTTP " + response.status);
  const modeHeader = response.headers.get("X-Arbiscan-Data-Mode");
  if (!["synthetic", "empty"].includes(modeHeader)) {
    throw new Error("Onbekende gegevensmodus; weergave geblokkeerd");
  }
  const body = await response.json();
  if (state.mode !== null && modeHeader !== state.mode) {
    throw new Error("De gegevensmodus is gewijzigd; herlaad de pagina");
  }
  return body;
}
async function collection(path) {
  let offset = 0;
  const results = [];
  // Bound local requests. Browser refresh cannot trigger provider polling.
  for (let batch = 0; batch < 10; batch += 1) {
    const separator = path.includes("?") ? "&" : "?";
    const page = await requestJson(path + separator + "limit=200&offset=" + offset);
    if (!Array.isArray(page.items) || typeof page.has_more !== "boolean") {
      throw new Error("Ongeldig API-pagineringcontract");
    }
    results.push(...page.items);
    if (!page.has_more) return results;
    if (page.items.length === 0) throw new Error("Ongeldige API-paginering");
    offset += page.items.length;
  }
  state.truncated = true;
  return results;
}
function matchTitle(event) {
  if (!event) return "Onbekende wedstrijd";
  const names = Array.isArray(event.participant_names) ? event.participant_names : [];
  return names.join(" – ") || "Onbekende wedstrijd";
}
function liveBlocked(runtime, readiness) {
  return runtime.live_quote_authorized !== false ||
    runtime.live_provider_ingestion !== false ||
    runtime.scanner_only !== true ||
    readiness.ready !== false;
}
function buildIndex() {
  const events = new Map(state.events.map((event) => [event.event_id, event]));
  const quoteMap = new Map(state.quotes.map((quote) => [quote.quote_id, quote]));
  return { events, quoteMap };
}
function quoteMatches(opportunity, quote) {
  return quote && quote.event_id === opportunity.event_id &&
    quote.market_id === opportunity.market_id;
}
function quotesFor(opportunity) {
  return state.quotes.filter((q) => quoteMatches(opportunity, q));
}
function updateChoices(selectId, items) {
  const target = byId(selectId);
  const previous = target.value;
  target.replaceChildren(target.options[0].cloneNode(true));
  for (const item of [...new Set(items)].sort()) {
    if (!item) continue;
    const option = node("option", "", item);
    option.value = item;
    target.append(option);
  }
  target.value = [...target.options].some((item) => item.value === previous) ? previous : "";
}
function renderStats() {
  const actionable = safeNumber(state.metrics.actionable_opportunities);
  const synthetic = safeNumber(state.metrics.synthetic_opportunities);
  setText("metric-actionable", formatCount.format(actionable ?? 0));
  setText("metric-demo", formatCount.format(synthetic ?? 0));
  setText("metric-events", formatCount.format(state.events.length));
  setText("metric-providers", formatCount.format(state.providers.length));
  setText("metric-actionable-note", "Niet vrijgegeven in Phase 20");
  setText("metric-demo-note", state.mode === "synthetic" ? "Alleen fictieve signalen" : "Geen demogegevens geladen");
  setText("metric-provider-note", "0 live-verbindingen");
  setText("last-update", "Lokaal vernieuwd om " + formatTime.format(new Date()));
  setText("app-version", "v" + (state.version ?? "—"));
  setText("top-mode", state.mode === "synthetic" ? "● DEMO / SYNTHETISCH" : "● LEEG / GEEN LIVE");
  byId("top-mode").classList.toggle("synthetic", state.mode === "synthetic");
}
function renderNotice() {
  if (state.mode === "synthetic") {
    showNotice("synthetic", "Demonstratiemodus — geen echte arbitrage",
      "Wedstrijden, quotes en ROI hieronder zijn synthetische voorbeelden. Providerverbindingen en live betting zijn uitgeschakeld.",
      "DEMO DATA");
  } else {
    showNotice("empty", "Geen live-gegevens beschikbaar",
      "De lokale server is verbonden, maar de scanner is niet gekoppeld aan gevalideerde live feeds. Start met --demo voor fictieve voorbeelden.",
      "EMPTY MODE");
  }
}
function renderEvents() {
  setText("events-count", String(state.events.length));
  const container = byId("event-list");
  container.replaceChildren();
  if (!state.events.length) {
    container.append(node("p", "muted-line", "Geen wedstrijden beschikbaar in deze modus."));
    return;
  }
  for (const event of state.events.slice(0, 12)) {
    const details = node("div");
    append(details, node("strong", "", matchTitle(event)),
      node("small", "", event.competition + " · " + stampText(event.scheduled_start)));
    const status = node("span", "entity-count", state.mode === "synthetic" ? "DEMO" : event.status);
    append(container, append(node("div", "entity-row"), details, status));
  }
}
function renderProviders() {
  setText("providers-count", String(state.providers.length));
  const container = byId("provider-list");
  container.replaceChildren();
  if (!state.providers.length) {
    container.append(node("p", "muted-line", "Geen providers gekoppeld. Er worden geen live-requests uitgevoerd."));
  }
  for (const provider of state.providers) {
    const details = append(node("div"), node("strong", "", provider.provider_id),
      node("small", "", "Geen actieve live verbinding"));
    append(container, append(node("div", "entity-row"), details,
      node("span", "entity-count", provider.available ? "BESCHIKBAAR" : "INACTIEF")));
  }
  const checks = state.readiness?.checks ?? {};
  setText("readiness-text", "Live gereedheid: niet vrijgegeven · " +
    Object.values(checks).filter((item) => item === true).length + "/" +
    Object.keys(checks).length + " controles");
  byId("readiness-dot").className = "status-indicator bad";
}
function filteredOpportunities() {
  const query = byId("search").value.trim().toLocaleLowerCase("nl");
  const sport = byId("sport-filter").value;
  const provider = byId("provider-filter").value;
  const roi = byId("min-roi").value.trim();
  const threshold = roi ? safeNumber(roi) : null;
  const index = buildIndex();
  let rows = state.opportunities.filter((opp) => {
    const event = index.events.get(opp.event_id);
    if (sport && event?.sport !== sport) return false;
    if (provider && !quotesFor(opp).some((q) => q.provider_id === provider)) return false;
    if (threshold !== null && (safeNumber(opp.guaranteed_profit_rate) ?? -Infinity) * 100 < threshold) return false;
    if (!query) return true;
    const haystack = [opp.market_id, opp.opportunity_id, event?.competition,
      event?.sport, ...(event?.participant_names ?? [])].join(" ").toLocaleLowerCase("nl");
    return haystack.includes(query);
  });
  const sort = byId("sort").value;
  rows = [...rows].sort((a, b) => {
    if (sort === "match") return matchTitle(index.events.get(a.event_id))
      .localeCompare(matchTitle(index.events.get(b.event_id)), "nl");
    if (sort === "date") return String(b.detected_at).localeCompare(String(a.detected_at));
    return (safeNumber(b.guaranteed_profit_rate) ?? -Infinity) -
      (safeNumber(a.guaranteed_profit_rate) ?? -Infinity);
  });
  return rows;
}
function renderOpportunities() {
  const tbody = byId("opportunity-rows");
  tbody.replaceChildren();
  const rows = filteredOpportunities();
  setText("opp-count", rows.length + " resultaten");
  const empty = byId("opportunity-empty");
  empty.hidden = rows.length > 0;
  const index = buildIndex();
  for (const opp of rows) {
    const event = index.events.get(opp.event_id);
    const tr = node("tr");
    const title = append(node("td"),
      node("strong", "cell-primary", matchTitle(event)),
      node("span", "cell-secondary", event?.competition ?? "Competitie onbekend"));
    const market = append(node("td"), node("strong", "cell-primary", opp.market_id),
      node("span", "cell-secondary", "Backend-marktidentificatie"));
    const roi = append(node("td"), node("span", "roi-value", pctText(opp.guaranteed_profit_rate)),
      node("span", "cell-secondary", "Theoretisch / demo"));
    const status = append(node("td"), node("span", "pill", "Niet uitvoerbaar"));
    const action = node("td", "align-right");
    const button = node("button", "details-button", "Bekijk →");
    button.type = "button";
    button.setAttribute("aria-label", "Bekijk details: " + matchTitle(event));
    button.addEventListener("click", () => openDetails(opp.opportunity_id));
    append(action, button);
    tbody.append(append(tr, title, market, roi, status, action));
  }
  setText("table-description", state.truncated ?
    "Niet alle records zijn opgehaald; maximaal 2.000 per collectie" :
    "Niet-uitvoerbare projecties · Geen bookmakertransacties");
}
function detailRow(label, value) {
  return append(node("div"), node("dt", "", label), node("dd", "", value));
}
function detailCard(title, rows) {
  const card = node("section", "drawer-card");
  const dl = node("dl");
  for (const [label, value] of rows) dl.append(detailRow(label, value));
  return append(card, node("h3", "", title), dl);
}
async function openDetails(id) {
  const opp = state.opportunities.find((item) => item.opportunity_id === id);
  if (!opp || state.mode !== "synthetic") return;
  state.selected = id;
  const panel = byId("detail-drawer");
  const content = byId("drawer-content");
  const event = state.events.find((item) => item.event_id === opp.event_id);
  content.replaceChildren(
    node("h2", "", matchTitle(event)),
    node("p", "drawer-subtitle", (event?.competition ?? "Onbekende competitie") +
      " · " + stampText(event?.scheduled_start) + " · SYNTHETISCHE DEMO"),
  );
  const warning = node("div", "drawer-note");
  append(warning, node("strong", "", "Geen gevalideerde inzetmogelijkheid"),
    node("span", "", "Deze odds en ROI zijn fictief. De backend heeft geen uitvoerbaar inzetplan aangeleverd; inzet, uitbetaling en gegarandeerde winst worden daarom niet verzonnen."));
  content.append(warning);
  content.append(detailCard("Markt & analyse", [
    ["Markt-ID", opp.market_id],
    ["Theoretische ROI", pctText(opp.guaranteed_profit_rate)],
    ["Impliciete som", opp.implied_probability_sum],
    ["Gedetecteerd", stampText(opp.detected_at)],
    ["Inzetplan", "Niet beschikbaar"],
    ["Status", "NIET UITVOERBAAR / DEMO"],
  ]));
  const card = append(node("section", "drawer-card"), node("h3", "", "Quotes en herkomst"));
  const quotes = quotesFor(opp);
  if (quotes.length === 0) card.append(node("p", "muted-line", "Geen quotes voor deze markt."));
  for (const quote of quotes) {
    const left = append(node("div"), node("strong", "", quote.selection_id),
      node("span", "", quote.provider_id),
      node("small", "", "Waargenomen: " + stampText(quote.observed_at)));
    card.append(append(node("div", "drawer-leg"), left, node("b", "", quote.decimal_price)));
  }
  content.append(card);
  panel.hidden = false;
  byId("drawer-backdrop").hidden = false;
  byId("close-detail").focus();
  try {
    const detail = await requestJson(API + "/opportunities/" + encodeURIComponent(id));
    if (state.selected !== id) return;
    const evidence = Boolean(detail.evidence_available);
    content.append(detailCard("Verificatie", [
      ["Bewijsmateriaal", evidence ? "Beschikbaar" : "Niet beschikbaar"],
      ["Quote-ID's", Array.isArray(detail.quote_ids) ? detail.quote_ids.join(", ") : "—"],
      ["Databron", "Synthetisch / lokale API"],
    ]));
  } catch {
    if (state.selected === id) alertError("De details konden niet worden geladen.");
  }
}
function closeDetails() {
  state.selected = null;
  byId("detail-drawer").hidden = true;
  byId("drawer-backdrop").hidden = true;
  const button = byId("opportunity-rows").querySelector("button");
  if (button) button.focus();
}
function renderAll() {
  renderStats();
  renderNotice();
  renderEvents();
  renderProviders();
  updateChoices("sport-filter", state.events.map((item) => item.sport));
  updateChoices("provider-filter", state.quotes.map((item) => item.provider_id));
  renderOpportunities();
}
async function refresh() {
  if (state.loading) return;
  state.loading = true;
  byId("refresh").disabled = true;
  clearError();
  try {
    const runtime = await requestJson(API + "/runtime");
    if (!["synthetic", "empty"].includes(runtime.data_mode) || runtime.data_mode !== state.mode && state.mode !== null) {
      throw new Error("Onverwachte datamodus; herlaad de pagina.");
    }
    // Require explicit *blocked* status; the demo interface does not support live.
    if (runtime.live_quote_authorized !== false || runtime.live_provider_ingestion !== false) {
      throw new Error("Live modus is niet beschikbaar in Phase 20.2");
    }
    state.mode = runtime.data_mode;
    const [health, readiness, metrics, events, providers, quotes, opportunities] = await Promise.all([
      requestJson(API + "/health"), requestJson(API + "/readiness"),
      requestJson(API + "/metrics"), collection(API + "/events"),
      collection(API + "/providers/status"), collection(API + "/odds"),
      collection(API + "/opportunities"),
    ]);
    if (liveBlocked(runtime, readiness)) {
      throw new Error("Onverwachte live gereedheid; weergave geblokkeerd");
    }
    if (state.mode === "empty" && (events.length || quotes.length || opportunities.length)) {
      throw new Error("Lege modus bevat onverwachte marktgegevens");
    }
    state.version = health.version;
    state.readiness = readiness;
    state.metrics = metrics.values;
    state.events = events;
    state.providers = providers;
    state.quotes = quotes;
    state.opportunities = opportunities;
    renderAll();
    if (!byId("detail-drawer").hidden) closeDetails();
  } catch (error) {
    // On any error, clear cached data: never display potentially outdated
    // opportunities as though they had just been refreshed.
    state.events = [];
    state.providers = [];
    state.quotes = [];
    state.opportunities = [];
    state.metrics = {};
    state.readiness = { ready: false, checks: {} };
    setText("top-mode", "● VERBINDINGSPROBLEEM");
    showNotice("error", "Lokale API niet beschikbaar",
      "Gegevens zijn verborgen wegens een verbindings- of beveiligingsfout. Controleer of de Python-server draait.",
      "OFFLINE");
    renderStats();
    renderEvents();
    renderProviders();
    renderOpportunities();
    closeDetails();
    alertError(error instanceof Error ? error.message : "Onbekende fout");
  } finally {
    state.loading = false;
    byId("refresh").disabled = false;
  }
}
function init() {
  for (const id of ["search", "sport-filter", "provider-filter", "min-roi", "sort"]) {
    byId(id).addEventListener(id === "search" || id === "min-roi" ? "input" : "change",
      renderOpportunities);
  }
  byId("refresh").addEventListener("click", refresh);
  byId("close-detail").addEventListener("click", closeDetails);
  byId("drawer-backdrop").addEventListener("click", closeDetails);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !byId("detail-drawer").hidden) closeDetails();
    if (event.key === "Tab" && !byId("detail-drawer").hidden) {
      // Keep keyboard focus in the modal until it closes.
      event.preventDefault();
      byId("close-detail").focus();
    }
  });
  for (const link of document.querySelectorAll(".nav-link")) {
    link.addEventListener("click", () => {
      for (const item of document.querySelectorAll(".nav-link")) item.classList.remove("active");
      link.classList.add("active");
    });
  }
  setText("local-time", formatTime.format(new Date()));
  refresh();
}
document.addEventListener("DOMContentLoaded", init);
