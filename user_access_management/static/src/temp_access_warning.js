import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const CHECK_EVERY_MS = 15 * 60 * 1000;

registry.category("services").add("uam_temp_access_warning", {
    dependencies: ["orm", "notification"],
    start(env, { orm, notification }) {
        if (!user.isInternalUser) {
            return;
        }
        // access id -> stages already shown ("normal", "last_hour"): each shown once per session
        const shown = new Map();
        const check = async () => {
            const rows = await orm.silent.call("user.temp.access", "uam_my_expiring", []);
            for (const r of rows) {
                const stage = r.hours_left < 1 ? "last_hour" : "normal";
                const stages = shown.get(r.id) || new Set();
                if (stages.has(stage)) {
                    continue;
                }
                stages.add(stage);
                shown.set(r.id, stages);
                notification.add(`Your extra access (${r.groups}) ends ${r.until}.`, {
                    title: "Temporary access",
                    type: r.hours_left < 24 ? "warning" : "info",
                    sticky: true,
                });
            }
        };
        check();
        setInterval(check, CHECK_EVERY_MS);
    },
});
