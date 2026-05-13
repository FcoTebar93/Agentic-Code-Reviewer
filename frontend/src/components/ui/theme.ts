export function cx(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(" ");
}

export const APP_BUTTON_PRIMARY = "app-button app-button-primary";
export const APP_BUTTON_SECONDARY = "app-button app-button-secondary";
export const APP_BUTTON_DANGER = "app-button app-button-danger";
export const APP_BUTTON_SUBTLE = "app-button app-button-subtle";
export const APP_BUTTON_TAB = "app-button app-button-tab";

export const APP_INPUT = "app-input text-sm font-mono";
export const APP_SELECT = "app-select text-xs font-mono";
export const APP_TEXTAREA = "app-textarea text-sm font-mono";

export const APP_LABEL = "app-label";
export const APP_META_TEXT = "app-meta-text text-xs";
export const APP_MUTED_TEXT = "app-muted-text";
export const APP_EMPTY_STATE = "app-empty-state";
