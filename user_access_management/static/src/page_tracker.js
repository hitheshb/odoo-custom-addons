import { router } from "@web/core/browser/router";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";

const MIN_GAP_MS = 10 * 1000;

registry.category("services").add("uam_page_tracker", {
    dependencies: ["orm"],
    start(env, { orm }) {
        if (!user.isInternalUser) {
            return;
        }
        let lastKey = "";
        let lastAt = 0;
        env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", () => {
            const { model, action, resId } = router.current;
            const page = document.title.replace(/ - Odoo$/, "");
            const key = `${model}|${action}|${resId}|${page}`;
            if (key === lastKey && Date.now() - lastAt < MIN_GAP_MS) {
                return;
            }
            lastKey = key;
            lastAt = Date.now();
            orm.silent.call("res.users", "uam_track", [model || false, action || false, page]);
        });
    },
});
