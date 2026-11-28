import Table from "../flat/Table.svelte";
import type { LookEntry } from "../look.ts";
import Lamp from "./Lamp.svelte";

const klassik: LookEntry = {
    name: "table.styleKlassik",
    renderer: Table,
    furniture: [{ object: "lamp", Piece: Lamp }],
};

export default klassik;
