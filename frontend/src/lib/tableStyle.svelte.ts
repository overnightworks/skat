import type { TableStyle } from "../routes/(start)/tables.ts";

// The style of the table the page shows: the streamed table sets it and every part that draws the look reads it.
let current = $state<TableStyle>("klassik");

export function tableStyle(): TableStyle {
    return current;
}

/** A table that has ended carries no style; the page falls back to the classic look. */
export function showTableStyle(style: TableStyle | null): void {
    current = style ?? "klassik";
}
