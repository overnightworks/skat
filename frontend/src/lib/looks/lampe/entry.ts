import type { SurfaceLook } from "../look.ts";
import "./room.css";
import "./chairs.css";
import Table from "./Table.svelte";

const lampe: SurfaceLook = { name: "look.lampeName", renderer: Table };

export default lampe;
