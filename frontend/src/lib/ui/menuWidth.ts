// The widths of the blessed pictures: a phone's menu and a desktop's, from the width the stylesheet widens the bar at.
const PHONE_PANEL_WIDTH = 300;
const DESKTOP_PANEL_WIDTH = 320;
const DESKTOP_FROM = 900;

/** The width the table menu and a panel opened in its place want at this viewport width. */
export function menuPanelWidth(viewportWidth: number): number {
    return viewportWidth >= DESKTOP_FROM ? DESKTOP_PANEL_WIDTH : PHONE_PANEL_WIDTH;
}
