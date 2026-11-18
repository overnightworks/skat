<script lang="ts">
    import { onMount } from "svelte";
    import type { PageProps } from "./$types";
    import Lobby from "./Lobby.svelte";
    import NewTableButton from "./NewTableButton.svelte";
    import AccountMark from "#lib/ui/AccountMark.svelte";
    import { readAccount } from "#lib/ui/account.svelte.ts";
    import SkatAccountMenu from "#lib/ui/SkatAccountMenu.svelte";
    import { words } from "#lib/words.ts";

    const { data }: PageProps = $props();

    let accountMenu: HTMLElement;
    let lobbyShown = $state(false);

    onMount(() => {
        void readAccount();
    });
</script>

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    <title>{`${words["app.name"]}`}</title>
</svelte:head>

<div class="start" class:with-lobby={lobbyShown} data-theme="dark">
    <header class="start-bar">
        <span class="wordmark">{words["app.name"]}</span>
        <button type="button" class="account-button" aria-label={words["account.title"]} popovertarget="accountMenu">
            <AccountMark />
        </button>
    </header>
    <div id="accountMenu" class="account-menu" popover bind:this={accountMenu}>
        <SkatAccountMenu
            kitWords={data.kitWords}
            onAccountOpen={() => {
                accountMenu.hidePopover();
            }}
        />
    </div>
    <div class="start-body">
        <Lobby bind:shown={lobbyShown} />
        <main class="start-main">
            <NewTableButton />
        </main>
    </div>
</div>
