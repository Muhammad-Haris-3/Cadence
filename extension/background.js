// Reports the active tab to the Cadence daemon.
//
// MV3 service workers are killed after ~30s idle, so this cannot rely on a
// timer of its own. Two things keep the daemon current: browser events wake the
// worker on every tab or focus change, and a 30s alarm acts as a heartbeat for
// the case where you sit on one tab and nothing fires. The daemon treats any
// report older than its freshness window as unknown rather than as still-true.

const ENDPOINT = "http://127.0.0.1:8765/tab";
const HEARTBEAT_MINUTES = 0.5;

function setBadge(text, color) {
  chrome.action.setBadgeText({ text });
  if (color) chrome.action.setBadgeBackgroundColor({ color });
}

async function post(payload) {
  const { token } = await chrome.storage.local.get("token");
  if (!token) {
    setBadge("!", "#b91c1c"); // not configured -- open the options page
    return;
  }

  try {
    const res = await fetch(ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Cadence-Token": token },
      body: JSON.stringify(payload),
    });
    setBadge(res.ok ? "" : "!", res.ok ? "#000000" : "#b91c1c");
  } catch {
    // Daemon isn't running. Not an error worth shouting about.
    setBadge("·", "#6b7280");
  }
}

async function reportActiveTab() {
  let win;
  try {
    win = await chrome.windows.getLastFocused();
  } catch {
    return post({ focused: false });
  }

  if (!win || !win.focused) return post({ focused: false });

  const [tab] = await chrome.tabs.query({ active: true, windowId: win.id });
  if (!tab) return post({ focused: false });

  // audible: a video or song is playing, so no mouse input still means watching, not idle.
  post({ url: tab.url || "", title: tab.title || "", focused: true, audible: !!tab.audible });
}

chrome.tabs.onActivated.addListener(() => reportActiveTab());

chrome.tabs.onUpdated.addListener((_id, info, tab) => {
  if (tab.active && (info.url || info.title || info.status === "complete" || info.audible !== undefined)) reportActiveTab();
});

chrome.windows.onFocusChanged.addListener((windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) post({ focused: false });
  else reportActiveTab();
});

chrome.alarms.create("cadence-heartbeat", { periodInMinutes: HEARTBEAT_MINUTES });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "cadence-heartbeat") reportActiveTab();
});

chrome.runtime.onStartup.addListener(reportActiveTab);
chrome.runtime.onInstalled.addListener(reportActiveTab);
