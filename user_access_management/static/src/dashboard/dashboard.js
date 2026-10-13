import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const REFRESH_MS = 30 * 1000;
const ALERT_KEYS = ["stale", "locks", "temp_expiring"];

function shiftDay(isoDate, days) {
    const d = new Date(`${isoDate}T00:00:00Z`);
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
}

export class UamDashboard extends Component {
    static template = "user_access_management.Dashboard";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, date: "", showOthers: false });
        onWillStart(() => this.load());
        const timer = setInterval(() => this.load(), REFRESH_MS);
        onWillUnmount(() => clearInterval(timer));
    }

    async load() {
        this.state.data = await this.orm.call("uam.dashboard", "get_data", [this.state.date || false]);
        this.state.date = this.state.data.date;
    }

    get here() {
        return this.state.data.users.filter((u) => u.status === "online" || u.status === "away");
    }

    get others() {
        return this.state.data.users.filter((u) => u.status !== "online" && u.status !== "away");
    }

    get staleCount() {
        return this.others.filter((u) => u.stale).length;
    }

    /** Usage rows grouped per user, each bar sized against the busiest model of the day. */
    get activity() {
        const rows = this.state.data.usage;
        const max = Math.max(1, ...rows.map((r) => r.views));
        const groups = new Map();
        for (const r of rows) {
            if (!groups.has(r.user_id)) {
                groups.set(r.user_id, { userId: r.user_id, user: r.user, total: 0, rows: [] });
            }
            const g = groups.get(r.user_id);
            g.total += r.views;
            g.rows.push({ ...r, width: Math.max(4, Math.round((r.views / max) * 100)) });
        }
        return [...groups.values()].sort((a, b) => b.total - a.total);
    }

    get dateLabel() {
        return new Date(`${this.state.date}T00:00:00Z`).toLocaleDateString(undefined, {
            day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
        });
    }

    get isToday() {
        const now = new Date();
        const local = new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
        return this.state.date >= local;
    }

    tileClass(tile) {
        if (ALERT_KEYS.includes(tile.key)) {
            return tile.count ? "o_uam_chip o_uam_chip--alert" : "o_uam_chip o_uam_chip--calm";
        }
        return `o_uam_chip o_uam_chip--${tile.key}`;
    }

    ago(utc) {
        if (!utc) {
            return "";
        }
        const mins = Math.round((Date.now() - new Date(`${utc.replace(" ", "T")}Z`).getTime()) / 60000);
        if (mins < 1) {
            return "just now";
        }
        if (mins < 60) {
            return `${mins} min ago`;
        }
        const hours = Math.round(mins / 60);
        return hours < 24 ? `${hours} h ago` : `${Math.round(hours / 24)} d ago`;
    }

    avatar(userId) {
        return `/web/image/res.users/${userId}/avatar_128`;
    }

    onDate(ev) {
        if (ev.target.value) {
            this.state.date = ev.target.value;
            this.load();
        }
    }

    step(days) {
        this.state.date = shiftDay(this.state.date, days);
        this.load();
    }

    toggleOthers() {
        this.state.showOthers = !this.state.showOthers;
    }

    async openTile(key) {
        this.action.doAction(await this.orm.call("uam.dashboard", "open_tile", [key]));
    }

    async openUsage(userId) {
        this.action.doAction(await this.orm.call("uam.dashboard", "open_user_usage", [userId, this.state.date]));
    }

    openUser(userId) {
        this.action.doAction({ type: "ir.actions.act_window", res_model: "res.users", res_id: userId,
                               views: [[false, "form"]] });
    }
}

registry.category("actions").add("uam_dashboard", UamDashboard);
