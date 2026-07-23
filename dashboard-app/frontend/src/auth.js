const STORAGE_KEY = "dashboard_auth_header";

export function getStoredAuthHeader() {
  return sessionStorage.getItem(STORAGE_KEY);
}

export function setStoredAuthHeader(value) {
  sessionStorage.setItem(STORAGE_KEY, value);
}

export function clearStoredAuthHeader() {
  sessionStorage.removeItem(STORAGE_KEY);
}

export function buildAuthHeader(username, password) {
  return "Basic " + btoa(`${username}:${password}`);
}
