<script lang="ts">
    import { AccountMenu, type KitWords } from "overnightworks-design";
    import { legalLinks } from "#lib/legal.ts";
    import { menuName } from "#lib/ui/account.svelte.ts";
    import { words } from "#lib/words.ts";
    import { ACCOUNT_CONSOLE_PATH, LOGOUT_PATH } from "#lib/wire.ts";

    // The kit's account menu of the signed-in person, which holds every signed-in page's legal links; the page decides
    // where it hangs and closes it when the name opens the account.
    let { kitWords, onAccountOpen }: { kitWords: KitWords; onAccountOpen: () => void } = $props();
</script>

<AccountMenu
    name={menuName()}
    accountHref={ACCOUNT_CONSOLE_PATH}
    {onAccountOpen}
    appRows={[]}
    legalLinks={legalLinks(words)}
    logOutAction={LOGOUT_PATH}
    words={kitWords}
/>
