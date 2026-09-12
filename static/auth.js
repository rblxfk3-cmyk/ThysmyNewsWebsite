const form = document.getElementById("form");
const msg = document.getElementById("msg");
const btn = document.getElementById("loginBtn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "Sedang log masuk…";
  btn.disabled = true;
  btn.textContent = "Sedang log masuk…";

  try {
    const r = await fetch("/api/auth/login", {
      method: "POST",
      signal: AbortSignal.timeout(25000),
      headers: {"Content-Type": "application/json", "X-THYSMY-Request":"1"},
      body: JSON.stringify({
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value
      })
    });

    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Login tidak berjaya");
    window.location.href = d.redirect || "/dashboard";
  } catch (err) {
    const text = String(err.message || "");
    if (text.toLowerCase().includes("email") &&
        (text.toLowerCase().includes("confirm") || text.toLowerCase().includes("verified"))) {
      msg.textContent = "Sahkan email dahulu. Semak Inbox, Spam atau Junk.";
    } else {
      msg.textContent = text;
    }
    btn.disabled = false;
    btn.textContent = "Log masuk";
  }
});
