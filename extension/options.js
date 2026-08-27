const tokenInput = document.getElementById("token");
const statusEl = document.getElementById("status");

chrome.storage.local.get("token").then(({ token }) => {
  if (token) tokenInput.value = token;
});

function show(message, ok) {
  statusEl.textContent = message;
  statusEl.className = ok ? "ok" : "err";
}

document.getElementById("save").addEventListener("click", async () => {
  const token = tokenInput.value.trim();
  if (!token) return show("Paste the token first.", false);

  await chrome.storage.local.set({ token });

  try {
    const res = await fetch("http://127.0.0.1:8765/tab", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-Cadence-Token": token },
      body: JSON.stringify({ url: "", title: "", focused: false }),
    });
    if (res.ok) show("Connected. Saved.", true);
    else if (res.status === 401) show("Saved, but the daemon rejected that token.", false);
    else show(`Saved, but the daemon answered ${res.status}.`, false);
  } catch {
    show("Saved, but the daemon isn't running. Start it and click again.", false);
  }
});
