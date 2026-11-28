import eslint from "@eslint/js";
import prettier from "eslint-config-prettier";
import svelte from "eslint-plugin-svelte";
import globals from "globals";
import ts from "typescript-eslint";

// In flat config a later block that sets a rule replaces the options of every earlier block that set it, so each
// option entry is built once here and spread into every block that sets its rule.
const styleElement = {
    selector: "SvelteStyleElement",
    message: "Components carry classes only; styles live in start.css.",
};
const styleComparison = {
    selector: "BinaryExpression[operator=/^[!=]==?$/] > CallExpression[callee.name='tableStyle']",
    message:
        "What differs between styles lives in the style's look entry under lib/looks/, never in a branch on tableStyle().",
};
const signInWords = {
    group: ["**/words.ts", "**/words.js"],
    message: "Sign-in pages read their words from the layout data, never from lib/words.ts.",
    allowTypeImports: true,
};
// The look layer is reached only through its registry and the types of its entry, so a look changes nowhere else.
const lookInternals = ["**/looks/**", "!**/looks/registry.ts", "!**/looks/look.ts"];
const lookMessage =
    "Only lib/looks/registry.ts and the types of lib/looks/look.ts are reached from outside the look layer.";
const lookTypes = { group: ["**/looks/look.ts"], message: lookMessage, allowTypeImports: true };
const outsideLooks = [{ group: lookInternals, message: lookMessage }, lookTypes];
// The layout loads the looks' sheets until each entry carries its own.
const layoutOutsideLooks = [
    { group: [...lookInternals, "!**/looks/klassik.css", "!**/looks/strandbar.css"], message: lookMessage },
    lookTypes,
];
// A look reads the table only through lib/table/, so it never depends on the routes, a store or the wire.
const insideLooksMessage =
    "A look reads the table through lib/table/: no routes module, no store outside lib/looks/, no wire.ts.";
const insideLooks = [
    { group: ["**/routes/**", "**/wire.ts", "**/wire.js"], message: insideLooksMessage },
    { group: ["**/*.svelte.ts", "!./**", "!#lib/looks/**"], message: insideLooksMessage },
];

export default ts.config(
    { linterOptions: { reportUnusedDisableDirectives: "error" } },
    eslint.configs.recommended,
    ...ts.configs.strictTypeChecked,
    ...svelte.configs.recommended,
    prettier,
    ...svelte.configs.prettier,
    {
        languageOptions: {
            globals: { ...globals.browser, ...globals.node },
            parserOptions: {
                projectService: { allowDefaultProject: ["*.js"] },
                extraFileExtensions: [".svelte"],
            },
        },
    },
    {
        files: ["**/*.svelte", "**/*.svelte.ts"],
        languageOptions: { parserOptions: { parser: ts.parser } },
    },
    {
        files: ["**/*.js"],
        extends: [ts.configs.disableTypeChecked],
    },
    {
        files: ["**/*.svelte"],
        rules: {
            "svelte/no-inline-styles": ["error", { allowTransitions: false }],
            "svelte/no-at-html-tags": "error",
            "no-restricted-syntax": ["error", styleElement, styleComparison],
        },
    },
    {
        files: ["src/**/*.ts"],
        ignores: ["src/lib/looks/**"],
        rules: { "no-restricted-syntax": ["error", styleComparison] },
    },
    {
        // A look branches on its own style; the card back, the scene and the ambience still branch until their parts
        // come from the look entry.
        files: [
            "src/lib/looks/**/*.svelte",
            "src/lib/ui/CardBack.svelte",
            "src/lib/ui/StyleScene.svelte",
            "src/lib/ui/Ambience.svelte",
        ],
        rules: { "no-restricted-syntax": ["error", styleElement] },
    },
    {
        files: ["src/**/*.{ts,js,svelte}"],
        ignores: ["src/lib/looks/**"],
        rules: { "no-restricted-imports": ["error", { patterns: outsideLooks }] },
    },
    {
        files: ["src/routes/+layout.svelte"],
        rules: { "no-restricted-imports": ["error", { patterns: layoutOutsideLooks }] },
    },
    {
        // A sign-in page is prerendered once per language, so it takes its words from the layout's data; the module's
        // words are those of the language the build runs in.
        files: [
            "src/lib/ui/SignIn.svelte",
            "src/lib/ui/CallSignIn.svelte",
            "src/lib/legal.ts",
            "src/routes/(sign-in)/**",
        ],
        rules: { "no-restricted-imports": ["error", { patterns: [signInWords, ...outsideLooks] }] },
    },
    {
        files: ["src/lib/looks/**"],
        rules: { "no-restricted-imports": ["error", { patterns: insideLooks }] },
    },
    {
        rules: { "@typescript-eslint/no-explicit-any": "error" },
    },
    { ignores: ["build/", ".svelte-kit/", "coverage/", "../src/skat/web/build/"] },
);
