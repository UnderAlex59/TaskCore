export const NOTIFICATIONS_CHANGED_EVENT = "notifications:changed";

export function notifyNotificationsChanged() {
  window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED_EVENT));
}
