<script lang="ts">
    import { SignInPage, type KitWords, type SignInState } from "overnightworks-design";
    import { legalLinks } from "#lib/legal.ts";
    import type { Words } from "#lib/words/de.ts";
    import { AUTH_START_PATH, LOGOUT_PATH } from "#lib/wire.ts";

    // The words arrive as props: a sign-in page is prerendered once per language, so it reads no module-level words.
    const {
        page,
        kitWords,
        words,
    }: { page: "signed-out" | "login-failed" | "no-access"; kitWords: KitWords; words: Words } = $props();
    const signInState = $derived.by((): SignInState => {
        if (page === "no-access") {
            return { page, logOutAction: LOGOUT_PATH };
        }
        return { page, signInHref: AUTH_START_PATH };
    });
</script>

<div class="sign-in">
    <SignInPage appName={words["app.name"]} state={signInState} legalLinks={legalLinks(words)} words={kitWords} />
</div>
