<script lang="ts">
    import { SignInPage, type KitWords, type SignInState } from "overnightworks-design";
    import { onMount } from "svelte";
    import {
        createCallSignIn,
        signInAddress,
        tableIdFromSearch,
        tablePath,
        type CallSignIn,
        type CallSignInView,
    } from "#lib/callSignIn.ts";
    import { legalLinks } from "#lib/legal.ts";
    import type { Words } from "#lib/words/de.ts";
    import { AUTH_START_PATH } from "#lib/wire.ts";

    const { kitWords, words }: { kitWords: KitWords; words: Words } = $props();

    let view = $state<CallSignInView>("signed-out");
    let tableId = $state<string | null>(null);
    let mounted = $state(false);
    let signIn: CallSignIn | null = null;
    let face: HTMLDivElement | undefined;

    const signInState = $derived.by((): SignInState => {
        if (view === "no-access") {
            return { page: "no-access" };
        }
        if ((view === "signing-in" || view === "window-blocked") && tableId !== null) {
            return { page: view, tabHref: tablePath(tableId) };
        }
        if (tableId === null) {
            // Before the script runs, a tap reloads the framed page, since the issuer refuses to be framed.
            return { page: "signed-out", signInHref: mounted ? AUTH_START_PATH : "" };
        }
        return {
            page: "signed-out",
            signInHref: signInAddress(tableId),
            onSignIn: () => {
                signIn?.logIn();
            },
            ...(view === "unfinished" ? { unfinished: true as const } : {}),
        };
    });

    // The blocked face announces nothing itself, so a screen reader hears the switch through the focused heading.
    $effect(() => {
        if (signInState.page !== "window-blocked") {
            return;
        }
        const heading = face?.querySelector("h1");
        heading?.setAttribute("tabindex", "-1");
        heading?.focus();
    });

    onMount(() => {
        mounted = true;
        const id = tableIdFromSearch(window.location.search);
        if (id === null) {
            return undefined;
        }
        const created = createCallSignIn(
            id,
            {
                open: (address, name, features) => window.open(address, name, features),
                replace: (address) => {
                    window.location.replace(address);
                },
                fetchStatus: async (path) => (await fetch(path)).status,
                every: (callback, milliseconds) => {
                    const timer = setInterval(() => void callback(), milliseconds);
                    return () => {
                        clearInterval(timer);
                    };
                },
            },
            (next) => {
                view = next;
            },
        );
        signIn = created;
        tableId = id;
        return created.stop;
    });

    function tabOpened(event: MouseEvent): void {
        if (tableId === null || !(event.target instanceof Element)) {
            return;
        }
        if (event.target.closest("a[target=_blank]")?.getAttribute("href") === tablePath(tableId)) {
            signIn?.recheck();
        }
    }
</script>

<!-- The wrapper recognises the tab link by its address and hears its tap on the way down; the link keeps design's behaviour. -->
<div class="sign-in" bind:this={face} onclickcapture={tabOpened}>
    <SignInPage
        appName={words["app.name"]}
        state={signInState}
        legalLinks={legalLinks(words)}
        legalLinksNewTab
        words={kitWords}
    />
</div>
