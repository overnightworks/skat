<script lang="ts">
    import CallSignIn from "#lib/ui/CallSignIn.svelte";
    import type { PageProps } from "./$types";

    const { data }: PageProps = $props();
</script>

<CallSignIn kitWords={data.kitWords} />
