<script lang="ts">
    import { untrack } from "svelte";
    import { AgentControl, type AgentControlRefusal, type KitWords } from "overnightworks-design";
    import { followAgents, type AgentsControl, type AgentsFollower } from "../../routes/(start)/agents.ts";

    // The kit's list of the agents the viewer may call or send away, in the panel the table menu's „Agenten“ row opens.
    // `open` is the menu or the panel while either shows; `shown` tells the menu whether the server shows the control
    // to the viewer at all, and so whether the row stands.
    // `streamedVersion` is the version of the latest table the page's stream brought, null before the first: the first
    // one means the viewer has a stream on the table, which the control needs, and each later one is read only while
    // the menu is open or when the agents seated changed, which can show the list to an owner or take it away.
    // `watchers` is how many people watch without a chair: an owner who comes to the table lists his agent without any
    // change of the table, so an open menu follows that count too.
    let {
        tableId,
        streamedVersion,
        seatedAgents,
        watchers,
        kitWords,
        open,
        shown = $bindable(),
    }: {
        tableId: string;
        streamedVersion: number | null;
        seatedAgents: string;
        watchers: number;
        kitWords: KitWords;
        open: boolean;
        shown: boolean;
    } = $props();

    let control = $state<AgentsControl>({ shown: false, rows: [] });
    let refusal = $state<AgentControlRefusal | undefined>();
    // A read that no longer shows the control came while a refusal stands: the list stays until the person has read the
    // refusal.
    let hiddenUnderRefusal = false;
    let follower: AgentsFollower | undefined;
    let seatedAgentsAtLastTable: string | undefined;

    $effect(() => {
        shown = control.shown;
    });

    $effect(() => {
        const following = followAgents(
            tableId,
            (answer) => {
                hiddenUnderRefusal = !answer.shown && refusal !== undefined;
                if (hiddenUnderRefusal) return;
                control = answer;
            },
            (reason) => (refusal = reason ?? undefined),
        );
        follower = following;
        return () => {
            following.stop();
        };
    });

    // What the latest streamed table brought that can change the list, null before the first table.
    const streamedFacts = $derived(streamedVersion === null ? null : [streamedVersion, watchers]);

    $effect(() => {
        if (streamedFacts === null) return;
        const firstTable = seatedAgentsAtLastTable === undefined;
        const agentsChanged = seatedAgents !== seatedAgentsAtLastTable;
        seatedAgentsAtLastTable = seatedAgents;
        if (firstTable || agentsChanged || untrack(() => open)) void follower?.read();
    });

    // The menu or the panel opens on a list read anew; it closes on a refusal read, and a control the server stopped
    // showing while the refusal stood goes with it.
    $effect(() => {
        if (open) {
            void follower?.read();
            return;
        }
        refusal = undefined;
        if (!hiddenUnderRefusal) return;
        hiddenUnderRefusal = false;
        control = { shown: false, rows: [] };
    });
</script>

{#if control.shown}
    <div class="agents-list">
        <AgentControl
            rows={control.rows}
            onCall={(key) => void follower?.call(key)}
            onSendAway={(key) => void follower?.sendAway(key)}
            {refusal}
            words={kitWords}
        />
    </div>
{/if}
