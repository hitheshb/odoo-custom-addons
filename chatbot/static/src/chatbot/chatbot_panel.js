import { Component, onMounted, onPatched, onWillStart, onWillUnmount, proxy, signal } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
import { router } from "@web/core/browser/router";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";

const STORAGE_KEY = "chatbot.tab.v1";
const HISTORY_LIMIT = 60;
const RECORD_LINKS = 4;
// Once the backup has answered, stay with it for a while rather than making
// every question wait for a provider we already know is down.
const STICKY_MS = 5 * 60 * 1000;
// The filter box only earns its place once the list gets long.
const FILTER_FROM = 12;

export class ChatbotPanel extends Component {
    static template = "chatbot.Panel";

    setup() {
        this.action = useService("action");
        // This OWL build has no useState: state is a proxy.
        this.state = proxy({
            open: false,
            turns: [],
            draft: "",
            busy: false,
            error: "",
            configured: false,
            model: "",
            // Which model this tab asks for. `pick` is what the user chose in
            // the list; `sticky` is the backup we fell back to, with an expiry.
            pick: null,
            sticky: null,
            picker: false,
            pickerData: null,
            pickerLoading: false,
            pickerError: "",
            filter: "",
            pending: null,
        });
        // The provider conversation, kept apart from what we draw: the model
        // needs the tool calls and their results verbatim, the user does not.
        this.history = [];
        this.bottomRef = signal.ref();
        this.restore();
        onWillStart(() => this.loadState());
        onMounted(() => this.scrollDown());
        onPatched(() => this.scrollDown());
        onWillUnmount(() => this.save());
    }

    // -- being on screen --------------------------------------------------

    get visible() {
        return user.isSystem;
    }

    get canChat() {
        return this.state.configured;
    }

    async loadState() {
        try {
            const info = await rpc("/chatbot/state", {});
            this.state.configured = info.configured;
            this.state.model = info.model;
        } catch {
            this.state.configured = false;
        }
    }

    currentScreen() {
        const current = router.current || {};
        return {
            model: current.model || "",
            resId: current.resId || 0,
            action: current.action || 0,
        };
    }

    // -- the tab's own memory ---------------------------------------------

    restore() {
        try {
            const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
            if (saved) {
                this.state.turns = saved.turns || [];
                this.history = saved.history || [];
                this.state.pick = saved.pick || null;
                this.state.sticky = saved.sticky || null;
            }
        } catch {
            sessionStorage.removeItem(STORAGE_KEY);
        }
    }

    save() {
        try {
            if (!this.state.turns.length) {
                sessionStorage.removeItem(STORAGE_KEY);
                return;
            }
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
                turns: this.state.turns.slice(-HISTORY_LIMIT),
                history: this.history.slice(-HISTORY_LIMIT),
                pick: this.state.pick,
                sticky: this.state.sticky,
            }));
        } catch {
            /* a full or blocked sessionStorage is not worth an error */
        }
    }

    clear() {
        this.state.turns = [];
        this.state.pending = null;
        this.state.error = "";
        this.history = [];
        this.save();
    }

    // -- drawing ----------------------------------------------------------

    scrollDown() {
        const node = this.bottomRef();
        if (node && this.state.open) {
            node.scrollIntoView({ block: "end" });
        }
    }

    addTurn(turn) {
        this.state.turns.push(turn);
        return this.state.turns[this.state.turns.length - 1];
    }

    toggle() {
        this.state.open = !this.state.open;
        if (this.state.open && !this.state.turns.length) {
            this.addTurn({
                kind: "bot",
                text: this.canChat
                    ? "Ask me anything about this database. I can read and change records."
                    : "I am not set up yet. Add an API key in Settings, Chatbot.",
            });
        }
    }

    openRecord(model, resId) {
        if (!model || !resId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: resId,
            views: [[false, "form"]],
        });
    }

    // -- picking a model --------------------------------------------------

    get shownModel() {
        const choice = this.effectiveChoice();
        return (choice && choice.model) || this.state.model;
    }

    get lotsOfModels() {
        return (this.state.pickerData || []).some(
            (provider) => (provider.models || []).length > FILTER_FROM);
    }

    get menuGroups() {
        const needle = this.state.filter.trim().toLowerCase();
        const groups = [];
        for (const provider of this.state.pickerData || []) {
            const models = (provider.models || []).filter(
                (name) => !needle || name.toLowerCase().includes(needle));
            if (!models.length && !provider.error) {
                continue;
            }
            groups.push({
                key: provider.key,
                label: provider.label,
                model: provider.model,
                error: provider.error,
                models,
            });
        }
        return groups;
    }

    effectiveChoice() {
        const sticky = this.state.sticky;
        if (sticky && sticky.until > Date.now()) {
            return { provider: sticky.provider, model: sticky.model };
        }
        return this.state.pick || null;
    }

    isCurrent(providerKey, model) {
        const choice = this.effectiveChoice();
        if (choice) {
            return choice.provider === providerKey && choice.model === model;
        }
        // Nothing picked in this tab: the model from Settings is the one in use.
        const provider = (this.state.pickerData || []).find((item) => item.key === providerKey);
        return Boolean(provider) && provider.model === model;
    }

    togglePicker() {
        this.state.picker = !this.state.picker;
        this.state.filter = "";
        if (this.state.picker && !this.state.pickerData) {
            this.loadModels();
        }
    }

    closePicker() {
        this.state.picker = false;
    }

    swallow() {
        /* a click inside the menu must not close it */
    }

    async loadModels() {
        this.state.pickerLoading = true;
        this.state.pickerError = "";
        try {
            const data = await rpc("/chatbot/models", {});
            this.state.pickerData = data.providers || [];
        } catch (error) {
            this.state.pickerError = this.errorText(error);
        } finally {
            this.state.pickerLoading = false;
        }
    }

    pickModel(providerKey, model) {
        this.state.pick = { provider: providerKey, model };
        this.state.sticky = null;
        this.state.picker = false;
        this.save();
    }

    // -- talking ----------------------------------------------------------

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    async send(ev) {
        if (ev) {
            ev.preventDefault();
        }
        const question = this.state.draft.trim();
        if (!question || this.state.busy) {
            return;
        }
        this.state.draft = "";
        this.addTurn({ kind: "user", text: question });
        this.history.push({ role: "user", content: question });
        await this.stream([]);
    }

    async approve() {
        const pending = this.state.pending;
        if (!pending || this.state.busy) {
            return;
        }
        this.state.pending = null;
        this.resolveConfirm(pending.id, "allowed");
        this.save();
        await this.stream([pending.id]);
    }

    async refuse() {
        const pending = this.state.pending;
        if (!pending || this.state.busy) {
            return;
        }
        this.state.pending = null;
        this.resolveConfirm(pending.id, "refused");
        // Answer the tool call ourselves, so the conversation stays valid and
        // the model learns the user said no.
        this.history.push({
            role: "tool",
            tool_call_id: pending.id,
            name: pending.name,
            content: JSON.stringify({ error: "The user refused this action. Do not repeat it." }),
        });
        this.save();
        await this.stream([]);
    }

    resolveConfirm(callId, verdict) {
        const turn = this.state.turns.find(
            (item) => item.kind === "confirm" && item.callId === callId);
        if (turn) {
            turn.verdict = verdict;
        }
    }

    async stream(approvals) {
        this.state.busy = true;
        this.state.error = "";
        let bubble = this.openBubble();
        const newBubble = () => {
            bubble = this.openBubble();
        };
        let pending = null;
        try {
            const response = await fetch("/chatbot/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    csrf_token: odoo.csrf_token,
                    messages: this.history,
                    approvals,
                    screen: this.currentScreen(),
                    choice: this.effectiveChoice(),
                }),
            });
            if (!response.ok || !response.body) {
                throw new Error(await this.errorFrom(response));
            }
            for await (const event of this.readEvents(response)) {
                if (event.e === "text") {
                    bubble.text += event.d;
                    bubble.streaming = false;
                } else if (event.e === "assistant") {
                    this.history.push(event.message);
                } else if (event.e === "tool") {
                    this.history.push(event.message);
                    this.dropEmptyBubble();
                    this.addTurn({
                        kind: "tool",
                        label: event.label,
                        name: event.name,
                        summary: event.summary,
                        state: event.state,
                        error: event.error,
                        model: event.model,
                        records: (event.records || []).slice(0, RECORD_LINKS),
                        count: event.count,
                    });
                    // Whatever it says next is a new thought, not a continuation.
                    newBubble();
                } else if (event.e === "provider") {
                    // The first provider would not answer. Note it, and stay on
                    // the backup for a few minutes.
                    this.state.sticky = {
                        provider: event.key,
                        model: event.model,
                        label: event.label,
                        until: Date.now() + STICKY_MS,
                    };
                    this.dropEmptyBubble();
                    this.addTurn({
                        kind: "note",
                        text: `${event.from} did not answer, so I am using ${event.label} for now.`,
                        detail: event.reason || "",
                    });
                    newBubble();
                } else if (event.e === "confirm") {
                    pending = event;
                    this.dropEmptyBubble();
                    this.addTurn({
                        kind: "confirm",
                        callId: event.id,
                        name: event.name,
                        summary: event.summary,
                        records: event.records || [],
                        verdict: "",
                    });
                    newBubble();
                } else if (event.e === "error") {
                    this.state.error = event.message;
                }
            }
            this.settleBubbles();
            if (!pending && !this.state.error && !this.hasAnswer()) {
                this.addTurn({ kind: "bot", text: "(no answer)" });
            }
            this.state.pending = pending;
        } catch (error) {
            this.settleBubbles();
            this.state.error = this.errorText(error);
        } finally {
            this.state.busy = false;
            this.save();
        }
    }

    openBubble() {
        return this.addTurn({ kind: "bot", text: "", streaming: true });
    }

    settleBubbles() {
        for (const turn of this.state.turns) {
            if (turn.kind === "bot") {
                turn.streaming = false;
            }
        }
        // Drop a bubble the model opened and never filled, e.g. it only ran tools.
        this.dropEmptyBubble();
    }

    dropEmptyBubble() {
        const turns = this.state.turns;
        while (turns.length) {
            const last = turns[turns.length - 1];
            if (last.kind === "bot" && !last.text) {
                turns.pop();
            } else {
                break;
            }
        }
    }

    hasAnswer() {
        return this.state.turns.some((turn) => turn.kind === "bot" && turn.text);
    }

    async *readEvents(response) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            let cut = buffer.indexOf("\n\n");
            while (cut !== -1) {
                const frame = buffer.slice(0, cut);
                buffer = buffer.slice(cut + 2);
                const line = frame.split("\n").find((item) => item.startsWith("data:"));
                if (line) {
                    try {
                        yield JSON.parse(line.slice(5).trim());
                    } catch {
                        /* a half-written frame: ignore it */
                    }
                }
                cut = buffer.indexOf("\n\n");
            }
        }
    }

    async errorFrom(response) {
        const body = await response.text();
        const text = body.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        return text.slice(0, 300) || `HTTP ${response.status}`;
    }

    errorText(error) {
        const message = error && error.message ? error.message : String(error);
        if (message.includes("Session expired") || message.includes("token")) {
            return "Your session token went stale. Reload the page and try again.";
        }
        return message;
    }
}

registry.category("main_components").add("chatbot", { Component: ChatbotPanel });
