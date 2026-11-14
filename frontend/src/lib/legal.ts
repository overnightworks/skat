import type { Words } from "#lib/words/de.ts";

// Every legal row links these, in this order.
const CENTRAL_LEGAL_ORIGIN = "https://hallucinai.de";
const APP_LEGAL_ANCHOR = "#skat";

function centralLegalAddress(path: string): string {
    return `${CENTRAL_LEGAL_ORIGIN}/${path}${APP_LEGAL_ANCHOR}`;
}

// The labels read in the page's language; the addresses stay the German binding pages in every language.
export function legalLinks(words: Pick<Words, "legal.imprint" | "legal.privacy" | "legal.terms">) {
    return [
        { label: words["legal.imprint"], href: centralLegalAddress("impressum") },
        { label: words["legal.privacy"], href: centralLegalAddress("datenschutz") },
        { label: words["legal.terms"], href: centralLegalAddress("nutzungsbedingungen") },
    ];
}
