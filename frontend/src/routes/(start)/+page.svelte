<script lang="ts">
    import { onMount } from "svelte";
    import type { PageProps } from "./$types";
    import Lobby from "./Lobby.svelte";
    import NewTableButton from "./NewTableButton.svelte";
    import AccountMark from "#lib/ui/AccountMark.svelte";
    import { knownName, readAccount } from "#lib/ui/account.svelte.ts";
    import CardSprite from "#lib/ui/CardSprite.svelte";
    import StartMark from "#lib/ui/StartMark.svelte";
    import SkatAccountMenu from "#lib/ui/SkatAccountMenu.svelte";
    import { words } from "#lib/words.ts";

    const { data }: PageProps = $props();

    let accountMenu: HTMLElement;

    onMount(() => {
        void readAccount();
    });
</script>

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words[key]} compiles to a `?? ""` branch no word can take -->
    <title>{`${words["app.name"]}`}</title>
</svelte:head>

<div class="start with-lobby" data-theme="dark">
    <CardSprite />
    <header class="start-bar start-head">
        <StartMark />
        <button type="button" class="account-button" aria-label={words["account.title"]} popovertarget="accountMenu">
            <span class="account-avatar">
                {#if knownName() === null}
                    <AccountMark />
                {:else}
                    {knownName()?.charAt(0).toUpperCase()}
                {/if}
            </span>
            {#if knownName() !== null}<span class="account-name">{knownName()}</span>{/if}
            <svg
                class="account-chevron"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.2"
                stroke-linecap="round"
                aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg
            >
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
        <Lobby />
        <main class="start-main">
            <NewTableButton />
        </main>
    </div>
</div>
