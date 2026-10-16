import { Component, signal, t, useProps } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const CHECK_EVERY_MS = 5 * 60 * 1000;
const DOT_COLORS = { online: "success", away: "warning", offline: "secondary" };

export class UamStatusDot extends Component {
    static template = "user_access_management.StatusDot";
    props = useProps({ ...standardFieldProps });

    get color() {
        return DOT_COLORS[this.props.record.data[this.props.name]] || "secondary";
    }
}
registry.category("fields").add("uam_status_dot", {
    component: UamStatusDot,
    supportedTypes: ["selection"],
});

export class WorkPromptDialog extends Component {
    static template = "user_access_management.WorkPromptDialog";
    static components = { Dialog };
    props = useProps({ close: t.function(), submit: t.function() });

    setup() {
        this.inputRef = signal.ref();
        this.env.dialogData.dismiss = () => this.send("");
    }

    async send(text) {
        await this.props.submit(text);
        this.props.close();
    }
}

registry.category("services").add("uam_work_prompt", {
    dependencies: ["orm", "dialog", "multi_tab"],
    start(env, { orm, dialog, multi_tab }) {
        if (!user.isInternalUser) {
            return;
        }
        let open = false;
        const check = async () => {
            if (open || !(await multi_tab.isOnMainTab())) {
                return;
            }
            if (await orm.call("user.work.update", "uam_is_due", [])) {
                open = true;
                dialog.add(
                    WorkPromptDialog,
                    { submit: (text) => orm.call("user.work.update", "uam_submit", [text]) },
                    { onClose: () => (open = false) }
                );
            }
        };
        check();
        setInterval(check, CHECK_EVERY_MS);
    },
});
