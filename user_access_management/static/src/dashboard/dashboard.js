import { Component, onWillStart, onWillUnmount, proxy, useProps } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardActionServiceProps } from "@web/webclient/actions/action_plugin";

const REFRESH_MS = 30 * 1000;

export class UamDashboard extends Component {
    static template = "user_access_management.Dashboard";
    props = useProps(standardActionServiceProps);

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = proxy({ data: null, date: "" });
        onWillStart(() => this.load());
        const timer = setInterval(() => this.load(), REFRESH_MS);
        onWillUnmount(() => clearInterval(timer));
    }

    async load() {
        this.state.data = await this.orm.call("uam.dashboard", "get_data", [this.state.date || false]);
        this.state.date = this.state.data.date;
    }

    onDate(ev) {
        this.state.date = ev.target.value;
        this.load();
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
