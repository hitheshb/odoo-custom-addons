import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";

export class ProfileUsersField extends X2ManyField {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
    }

    async openRecord(record) {
        const action = await this.orm.call("res.users", "action_open_profile_tab", [[record.resId]]);
        return this.actionService.doAction(action);
    }
}

registry.category("fields").add("test_profile_users", {
    ...x2ManyField,
    component: ProfileUsersField,
});
