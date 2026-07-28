/**
 * Paddleforge Inovelli ZHA Controller — sidebar panel + Lovelace card (no build step).
 *
 * Reads the group snapshot from `sensor.paddleforge_inovelli_zha_controller_groups` (attribute
 * `groups`, kept live by the integration) and drives the create/add/remove/recolor/
 * delete services. Physical scene-button changes flow back through the same sensor,
 * so the UI and the switches stay in sync.
 */

const DOMAIN = "paddleforge_inovelli_zha_controller";
const SENSOR_ID = "sensor.paddleforge_inovelli_zha_controller_groups";

const hueToHex = (hue) => {
  const h = ((Number(hue) % 256) / 255) * 6;
  const c = 1;
  const x = 1 - Math.abs((h % 2) - 1);
  let r = 0;
  let g = 0;
  let b = 0;
  if (h < 1) [r, g, b] = [c, x, 0];
  else if (h < 2) [r, g, b] = [x, c, 0];
  else if (h < 3) [r, g, b] = [0, c, x];
  else if (h < 4) [r, g, b] = [0, x, c];
  else if (h < 5) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const to = (v) => Math.round(v * 255).toString(16).padStart(2, "0");
  return `#${to(r)}${to(g)}${to(b)}`;
};

const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[ch]);

const STYLE = `
  :host { display: block; }
  .topbar { display: flex; align-items: center; gap: 8px; height: 56px; padding: 0 8px;
            background: var(--app-header-background-color, var(--primary-color));
            color: var(--app-header-text-color, var(--text-primary-color, #fff));
            position: sticky; top: 0; z-index: 3; box-sizing: border-box; }
  .topbar-title { font-size: 1.15rem; font-weight: 500; }
  .menu { background: transparent; border: none; color: inherit; font-size: 1.5rem; line-height: 1;
          cursor: pointer; padding: 6px 10px; border-radius: 50%; display: inline-flex; }
  .menu:hover { background: rgba(127,127,127,.18); }
  .wrap { max-width: 960px; margin: 0 auto; padding: 16px; }
  h1 { font-size: 1.4rem; margin: 8px 0 16px; }
  .muted { color: var(--secondary-text-color); }
  .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); }
  .card { background: var(--card-background-color, #fff); border-radius: 12px;
          box-shadow: var(--ha-card-box-shadow, 0 2px 6px rgba(0,0,0,.15)); overflow: hidden; }
  .swatch { height: 8px; }
  .body { padding: 14px 16px 16px; }
  .title { display: flex; align-items: center; gap: 10px; font-weight: 600; margin-bottom: 10px; }
  .dot { width: 16px; height: 16px; border-radius: 50%; border: 1px solid rgba(0,0,0,.2); }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0 12px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; background: var(--secondary-background-color);
          border-radius: 14px; padding: 3px 8px 3px 10px; font-size: .85rem; }
  .chip button { border: none; background: transparent; cursor: pointer; font-size: 1rem; line-height: 1;
                 color: var(--secondary-text-color); }
  .row { display: flex; gap: 8px; align-items: center; margin-top: 8px; flex-wrap: wrap; }
  select, input[type=text] { flex: 1; min-width: 120px; padding: 6px 8px; border-radius: 8px;
          border: 1px solid var(--divider-color, #ccc); background: var(--card-background-color); color: inherit; }
  input[type=range] { flex: 1; }
  button.act { border: none; border-radius: 8px; padding: 7px 12px; cursor: pointer; font-weight: 500;
          background: var(--primary-color); color: var(--text-primary-color, #fff); }
  button.ghost { background: transparent; color: var(--primary-color); border: 1px solid var(--primary-color); }
  button.danger { background: var(--error-color, #db4437); }
  .new { margin-top: 20px; }
  label { font-size: .8rem; color: var(--secondary-text-color); display: block; margin-bottom: 2px; }
  .badge { font-size: .68rem; text-transform: uppercase; letter-spacing: .03em; padding: 1px 6px;
           border-radius: 8px; background: var(--secondary-background-color); color: var(--secondary-text-color); flex: none; }
  .dev-list { max-height: 210px; overflow-y: auto; border: 1px solid var(--divider-color, #ccc);
              border-radius: 8px; padding: 4px; margin-top: 2px; }
  .dev-row { display: flex; align-items: center; gap: 8px; padding: 5px 6px; border-radius: 6px; font-size: .9rem; }
  .dev-row + .dev-row { border-top: 1px solid var(--divider-color, #eee); }
  .dev-row.taken { opacity: .7; }
  .dev-row label { display: flex; align-items: center; gap: 8px; margin: 0; cursor: pointer; flex: 1;
                   color: inherit; font-size: .9rem; }
  .dev-row.taken label { cursor: default; }
  .gdot { width: 12px; height: 12px; border-radius: 50%; border: 1px solid rgba(0,0,0,.25); flex: none; }
  .grp-tag { font-size: .72rem; color: var(--secondary-text-color); display: inline-flex; align-items: center; gap: 5px; }
  .spacer { flex: 1; }
`;

class InovelliPairingBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._groups = [];
    this._groupsKey = "";
    this._draft = { name: "", hue: 85, switches: [] };
    this._isPanel = false;
  }

  set hass(hass) {
    this._hass = hass;
    const ent =
      hass.states[SENSOR_ID] ||
      Object.values(hass.states).find(
        (s) => s.entity_id.startsWith("sensor.") && Array.isArray(s.attributes.groups)
      );
    const groups = ent ? ent.attributes.groups || [] : [];
    const key = JSON.stringify(groups);
    if (key !== this._groupsKey || !this.shadowRoot.firstChild) {
      this._groups = groups;
      this._groupsKey = key;
      this._render();
    }
  }

  get hass() {
    return this._hass;
  }

  _ieeeOfDevice(d) {
    const c = (d.connections || []).find((x) => x[0] === "zigbee");
    return c ? String(c[1]).toLowerCase() : null;
  }

  /** Enriched Inovelli device list: { id, name, type, ieee, group|null }. */
  _devices() {
    const hass = this._hass;
    if (!hass || !hass.devices) return [];
    const byIeee = {};
    for (const g of this._groups) for (const m of g.members) byIeee[m.ieee] = g;
    return Object.values(hass.devices)
      .filter(
        (d) =>
          (d.identifiers || []).some((id) => id[0] === "zha") &&
          (d.manufacturer || "").toLowerCase() === "inovelli"
      )
      .map((d) => {
        const ieee = this._ieeeOfDevice(d);
        return {
          id: d.id,
          name: d.name_by_user || d.name || d.id,
          type: /vzm35/i.test(d.model || "") ? "fan" : "light",
          ieee,
          group: ieee ? byIeee[ieee] || null : null,
        };
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  async _call(service, data) {
    try {
      await this._hass.callService(DOMAIN, service, data);
    } catch (err) {
      alert(`Paddleforge Inovelli ZHA Controller: ${err.message || err}`);
    }
  }

  _render() {
    const devices = this._devices();
    const typeByIeee = {};
    devices.forEach((d) => (typeByIeee[d.ieee] = d.type));
    // Drop draft picks that have since joined a group.
    const freeIds = new Set(devices.filter((d) => !d.group).map((d) => d.id));
    this._draft.switches = this._draft.switches.filter((id) => freeIds.has(id));

    // Per-group "Add" dropdown: any device not already in *this* group.
    const addOptions = (gid) =>
      devices
        .filter((d) => !d.group || d.group.group_id !== gid)
        .map(
          (d) =>
            `<option value="${d.id}">${esc(d.name)} · ${d.type}${d.group ? ` — in ${esc(d.group.name)}` : ""}</option>`
        )
        .join("");

    const groupsHtml = this._groups.length
      ? this._groups
          .map((g) => {
            const hex = g.color_hex || hueToHex(g.color_hue);
            const chips = g.members
              .map(
                (m) =>
                  `<span class="chip"><span class="badge">${typeByIeee[m.ieee] || "?"}</span>${esc(m.name)}<button data-act="remove" data-gid="${g.group_id}" data-ieee="${m.ieee}" title="Remove">×</button></span>`
              )
              .join("");
            return `
              <div class="card">
                <div class="swatch" style="background:${hex}"></div>
                <div class="body">
                  <div class="title"><span class="dot" style="background:${hex}"></span>${esc(g.name)}
                    <span class="muted" style="font-weight:400">#${g.group_id}</span></div>
                  <div class="chips">${chips || '<span class="muted">no members</span>'}</div>
                  <div class="row">
                    <select data-role="add" data-gid="${g.group_id}">${addOptions(g.group_id)}</select>
                    <button class="act ghost" data-act="add" data-gid="${g.group_id}">Add</button>
                  </div>
                  <div class="row">
                    <input type="range" min="0" max="255" value="${g.color_hue}" data-role="hue" data-gid="${g.group_id}">
                    <button class="act ghost" data-act="color" data-gid="${g.group_id}">Recolor</button>
                    <button class="act danger" data-act="delete" data-gid="${g.group_id}">Delete</button>
                  </div>
                </div>
              </div>`;
          })
          .join("")
      : '<p class="muted">No pairing groups yet. Create one below, or hold a switch config button.</p>';

    // Create-form device list: free switches are selectable; grouped ones are shown
    // (disabled) with a colored dot + label for the group they already belong to.
    const devList = devices.length
      ? devices
          .map((d) => {
            if (d.group) {
              const ghex = d.group.color_hex || hueToHex(d.group.color_hue);
              return `<div class="dev-row taken"><span class="badge">${d.type}</span><label>${esc(d.name)}</label>
                        <span class="grp-tag"><span class="gdot" style="background:${ghex}"></span>${esc(d.group.name)}</span></div>`;
            }
            const checked = this._draft.switches.includes(d.id) ? " checked" : "";
            return `<div class="dev-row"><label><input type="checkbox" data-role="pick" value="${d.id}"${checked}>
                      <span class="badge">${d.type}</span>${esc(d.name)}</label></div>`;
          })
          .join("")
      : '<p class="muted">No Inovelli switches found.</p>';

    const topbar = this._isPanel
      ? `<div class="topbar"><button class="menu" data-act="menu" title="Open menu" aria-label="Open menu">☰</button><div class="topbar-title">Paddleforge Inovelli ZHA Controller</div></div>`
      : "";
    const heading = this._isPanel ? "" : "<h1>Paddleforge Inovelli ZHA Controller</h1>";

    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      ${topbar}
      <div class="wrap">
        ${heading}
        <div class="grid">${groupsHtml}</div>
        <div class="card new">
          <div class="swatch" style="background:${hueToHex(this._draft.hue)}"></div>
          <div class="body">
            <div class="title">Create a group</div>
            <label>Switches (pick two or more free switches)</label>
            <div class="dev-list">${devList}</div>
            <div class="row">
              <input type="text" placeholder="Name (optional)" data-role="new-name" value="${esc(this._draft.name)}">
            </div>
            <div class="row">
              <label style="margin:0">Color</label>
              <input type="range" min="0" max="255" value="${this._draft.hue}" data-role="new-hue">
              <button class="act" data-act="create">Create group</button>
            </div>
          </div>
        </div>
      </div>`;

    this._wire();
  }

  _wire() {
    const root = this.shadowRoot;
    root.querySelectorAll("[data-act]").forEach((el) => {
      el.addEventListener("click", () => this._onAction(el));
    });
    // Live color preview while dragging a group's hue slider.
    root.querySelectorAll('input[data-role="hue"]').forEach((sl) => {
      sl.addEventListener("input", () => {
        const hex = hueToHex(Number(sl.value));
        const card = sl.closest(".card");
        if (!card) return;
        const swatch = card.querySelector(".swatch");
        const dot = card.querySelector(".dot");
        if (swatch) swatch.style.background = hex;
        if (dot) dot.style.background = hex;
      });
    });
    root.querySelectorAll('input[data-role="pick"]').forEach((cb) => {
      cb.addEventListener("change", () => {
        const set = new Set(this._draft.switches);
        if (cb.checked) set.add(cb.value);
        else set.delete(cb.value);
        this._draft.switches = [...set];
      });
    });
    const nm = root.querySelector('[data-role="new-name"]');
    if (nm) nm.addEventListener("input", (e) => (this._draft.name = e.target.value));
    const nh = root.querySelector('[data-role="new-hue"]');
    if (nh)
      nh.addEventListener("input", (e) => {
        this._draft.hue = Number(e.target.value);
        const sw = nh.closest(".card").querySelector(".swatch");
        if (sw) sw.style.background = hueToHex(this._draft.hue);
      });
  }

  _onAction(el) {
    const act = el.dataset.act;
    const gid = el.dataset.gid ? Number(el.dataset.gid) : undefined;
    const root = this.shadowRoot;
    if (act === "menu") {
      // Toggle the Home Assistant sidebar drawer (no header on a custom panel).
      this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
    } else if (act === "remove") {
      const dev = this._deviceForIeee(el.dataset.ieee);
      if (dev) this._call("remove_member", { group_id: gid, switch: dev });
      else alert("Could not resolve the switch device for this member.");
    } else if (act === "add") {
      const sel = root.querySelector(`select[data-role="add"][data-gid="${gid}"]`);
      if (sel && sel.value) this._call("add_member", { group_id: gid, switch: sel.value });
    } else if (act === "color") {
      const sl = root.querySelector(`input[data-role="hue"][data-gid="${gid}"]`);
      if (sl) this._call("set_color", { group_id: gid, color_hue: Number(sl.value) });
    } else if (act === "delete") {
      if (confirm("Delete this pairing group?")) this._call("delete_group", { group_id: gid });
    } else if (act === "create") {
      if (this._draft.switches.length < 2) {
        alert("Pick at least two free switches.");
        return;
      }
      const data = { switches: this._draft.switches, color_hue: this._draft.hue };
      if (this._draft.name.trim()) data.name = this._draft.name.trim();
      this._draft = { name: "", hue: 85, switches: [] };
      this._call("create_group", data);
    }
  }

  _deviceForIeee(ieee) {
    const hass = this._hass;
    if (!hass || !hass.devices) return undefined;
    const dev = Object.values(hass.devices).find((d) =>
      (d.connections || []).some((c) => c[0] === "zigbee" && String(c[1]).toLowerCase() === ieee)
    );
    return dev ? dev.id : undefined;
  }
}

class InovelliScenePairingPanel extends InovelliPairingBase {
  constructor() {
    super();
    this._isPanel = true;
  }
}

class InovelliScenePairingCard extends InovelliPairingBase {
  setConfig(_config) {}
  getCardSize() {
    return 8;
  }
}

if (!customElements.get("paddleforge-inovelli-zha-controller-panel")) {
  customElements.define("paddleforge-inovelli-zha-controller-panel", InovelliScenePairingPanel);
}
if (!customElements.get("paddleforge-inovelli-zha-controller-card")) {
  customElements.define("paddleforge-inovelli-zha-controller-card", InovelliScenePairingCard);
}

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "paddleforge-inovelli-zha-controller-card")) {
  window.customCards.push({
    type: "paddleforge-inovelli-zha-controller-card",
    name: "Paddleforge Inovelli ZHA Controller",
    description: "Manage Inovelli Blue pairing groups (create, add, recolor, remove).",
  });
}
