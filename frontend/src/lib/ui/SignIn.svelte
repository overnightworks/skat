<script lang="ts">
    import { SignInPage, type KitWords, type SignInState } from "overnightworks-design";
    import { LEGAL_LINKS } from "#lib/legal.ts";
    import { words } from "#lib/words.ts";
    import { AUTH_START_PATH, LOGOUT_PATH } from "#lib/wire.ts";

    const { page, kitWords }: { page: "signed-out" | "login-failed" | "no-access"; kitWords: KitWords } = $props();
    const signInState = $derived.by((): SignInState => {
        if (page === "no-access") {
            return { page, logOutAction: LOGOUT_PATH };
        }
        return { page, signInHref: AUTH_START_PATH };
    });
</script>

<div class="sign-in">
    <SignInPage appName={words["app.name"]} state={signInState} legalLinks={LEGAL_LINKS} words={kitWords} />
</div>
