import Table from "../flat/Table.svelte";
import type { LookEntry } from "../look.ts";
import Cocktail from "./Cocktail.svelte";
import Shell from "./Shell.svelte";

const strandbar: LookEntry = {
    name: "table.styleStrandbar",
    renderer: Table,
    furniture: [
        { object: "cocktail", Piece: Cocktail },
        { object: "shell", Piece: Shell },
    ],
};

export default strandbar;
