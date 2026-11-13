<script lang="ts">
    import SignIn from "#lib/ui/SignIn.svelte";
    import type { PageProps } from "./$types";

    const { data }: PageProps = $props();
</script>

<SignIn page="no-access" kitWords={data.kitWords} words={data.words} />
