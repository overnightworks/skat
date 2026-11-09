<script lang="ts">
    import { AccountMenu, LegalLinks } from "overnightworks-design";
    import { onMount } from "svelte";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import NewTableButton from "./NewTableButton.svelte";
    import { accountMenuWords } from "#lib/kitWords.ts";
    import { menuName, readAccount } from "#lib/ui/account.svelte.ts";
    import { words } from "#lib/words.ts";
    import { ACCOUNT_CONSOLE_PATH, LOGOUT_PATH } from "#lib/wire.ts";

    let accountMenu: HTMLElement;

    onMount(() => {
        void readAccount();
    });
</script>

<svelte:head>
    <!-- eslint-disable-next-line @typescript-eslint/no-unnecessary-template-expression -- a bare {words.x} compiles to a `?? ""` branch no word can take -->
    <title>{`${words.appName}`}</title>
</svelte:head>

<div class="start" data-theme="dark">
    <header class="start-bar">
        <span class="wordmark">{words.appName}</span>
        <button type="button" class="account-button" aria-label={words.account} popovertarget="accountMenu">
            <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                aria-hidden="true"
            >
                <circle cx="9" cy="8" r="3.5" />
                <path d="M2.5 19.5c.7-3.4 3.3-5.2 6.5-5.2s5.8 1.8 6.5 5.2" />
            </svg>
        </button>
    </header>
    <div id="accountMenu" class="account-menu" popover bind:this={accountMenu}>
        <AccountMenu
            name={menuName()}
            accountHref={ACCOUNT_CONSOLE_PATH}
            onAccountOpen={() => {
                accountMenu.hidePopover();
            }}
            appRows={[]}
            legalLinks={LEGAL_LINKS}
            logOutAction={LOGOUT_PATH}
            words={accountMenuWords}
        />
    </div>
    <main class="start-main">
        <NewTableButton />
    </main>
    <footer class="start-legal">
        <LegalLinks links={LEGAL_LINKS} />
    </footer>
</div>
