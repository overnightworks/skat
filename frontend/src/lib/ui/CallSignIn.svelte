<script lang="ts">
    import { SignInPage, type SignInState } from "overnightworks-design";
    import { onMount } from "svelte";
    import {
        createCallSignIn,
        signInAddress,
        tableIdFromSearch,
        tablePath,
        type CallSignIn,
        type CallSignInView,
    } from "#lib/callSignIn.ts";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { AUTH_START_PATH } from "#lib/wire.ts";

    let view = $state<CallSignInView>("signed-out");
    let tableId = $state<string | null>(null);
    let signIn: CallSignIn | null = null;

    const signInState = $derived.by((): SignInState => {
        if (view === "no-access") {
            return { page: "no-access" };
        }
        if (view === "signing-in" && tableId !== null) {
            return { page: "signing-in", tabHref: tablePath(tableId) };
        }
        if (tableId === null) {
            return { page: "signed-out", signInHref: AUTH_START_PATH };
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

    onMount(() => {
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
        if (event.target instanceof Element && event.target.closest("a[target=_blank]") !== null) {
            signIn?.recheck();
        }
    }
</script>

<!-- The wrapper only hears the plain link's tap on its way down; the link keeps design's behaviour. -->
<div class="sign-in" onclickcapture={tabOpened}>
    <SignInPage appName="Skat" state={signInState} legalLinks={LEGAL_LINKS} />
</div>
