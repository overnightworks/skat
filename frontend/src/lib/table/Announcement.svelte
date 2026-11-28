<script lang="ts">
    import "./announcement.css";

    // The one live region of a table that a look draws: a sentence that appears here is said once, and a look draws
    // the same sentence for the eye without saying it again.
    const { text }: { text: string | null } = $props();
</script>

<p class="table-announcement" role="status">{text ?? ""}</p>
