import type { Place } from "./timeline.ts";
import { includesCard, type Card } from "../../routes/(start)/tables.ts";

// The own hand lets a card go before the table answers, and the card has left the hand when it lands on the felt.
let letGo: { readonly card: Card; readonly place: Place } | undefined;

/** Keeps where the own hand let `card` go until that card lands. */
export function cardLetGo(card: Card, place: Place): void {
    letGo = { card, place };
}

/** Where the own hand let `card` go, told once; nothing for a card no hand of this page let go. */
export function letGoPlaceOf(card: Card): Place | undefined {
    if (letGo === undefined || !includesCard([letGo.card], card)) return undefined;
    const { place } = letGo;
    letGo = undefined;
    return place;
}
