const form = document.getElementById("form");
const msg = document.getElementById("msg");
const btn = document.getElementById("loginBtn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "Signing in…";
  btn.disabled = true;
  btn.textContent = "Signing in…";

  try {
    const r = await fetch("/api/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value
      })
    });

    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Login failed");
    window.location.href = d.redirect || "/dashboard";
  } catch (err) {
    const text = String(err.message || "");
    if (text.toLowerCase().includes("email") &&
        (text.toLowerCase().includes("confirm") || text.toLowerCase().includes("verified"))) {
      msg.textContent = "Please verify your email first. Check your Inbox, Spam or Junk folder.";
    } else {
      msg.textContent = text;
    }
    btn.disabled = false;
    btn.textContent = "Login";
  }
});
