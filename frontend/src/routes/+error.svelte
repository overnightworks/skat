<script lang="ts">
    import { goto } from "$app/navigation";
    import { page } from "$app/state";
    import { onMount } from "svelte";
    import { startOutage, type OutageState } from "#lib/outage.ts";
    import { words } from "#lib/words.ts";

    const FIRST_SERVER_ERROR_STATUS = 500;

    let outage = $state<OutageState>("reconnecting");
    const waiting = $derived(page.status >= FIRST_SERVER_ERROR_STATUS && outage !== "failed");

    // A failed route load answers 500 or more when the connection to Skat broke it, and so does a code error: the
    // controller tells them apart by whether the edge answers and the route still fails.
    onMount(() => {
        if (page.status < FIRST_SERVER_ERROR_STATUS) return;
        return startOutage({
            // eslint-disable-next-line svelte/no-navigation-without-resolve -- the address that failed is already one of this app
            retry: () => goto(page.url.href, { replaceState: true }),
            onState: (next) => {
                outage = next;
            },
        });
    });
</script>

<div class="start" data-theme="dark" lang="de">
    <header class="start-bar outage-bar">
        <span class="wordmark">{words["app.name"]}</span>
    </header>
    {#if waiting}
        <div class="reconnect" role="status"><span class="spin"></span>{words["app.reconnecting"]}</div>
        {#if outage === "unreachable"}
            <p class="outage-line" role="status">{words["app.unreachable"]}</p>
        {/if}
    {:else}
        <main class="start-main">
            <div class="failure">
                <h1>{page.status}</h1>
                <p>{page.error?.message}</p>
            </div>
        </main>
    {/if}
</div>
