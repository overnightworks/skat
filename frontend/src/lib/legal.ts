import { words } from "#lib/words.ts";

// Every legal row links these, in this order.
const CENTRAL_LEGAL_ORIGIN = "https://hallucinai.de";
const APP_LEGAL_ANCHOR = "#skat";

function centralLegalAddress(path: string): string {
    return `${CENTRAL_LEGAL_ORIGIN}/${path}${APP_LEGAL_ANCHOR}`;
}

export const LEGAL_LINKS = [
    { label: words.legalImprint, href: centralLegalAddress("impressum") },
    { label: words.legalPrivacy, href: centralLegalAddress("datenschutz") },
    { label: words.legalTerms, href: centralLegalAddress("nutzungsbedingungen") },
];
