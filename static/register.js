const form = document.getElementById("registerForm");
const msg = document.getElementById("msg");
const btn = document.getElementById("registerBtn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "Mencipta akaun…";
  btn.disabled = true;
  btn.textContent = "Mencipta…";

  try {
    const r = await fetch("/api/auth/register", {
      method: "POST",
      signal: AbortSignal.timeout(25000),
      headers: {"Content-Type": "application/json", "X-THYSMY-Request":"1"},
      body: JSON.stringify({
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value
      })
    });

    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Pendaftaran tidak berjaya");

    document.getElementById("registerContent").classList.add("hidden");
    document.getElementById("registerSuccess").classList.remove("hidden");
  } catch (err) {
    msg.textContent = err.message;
    btn.disabled = false;
    btn.textContent = "Daftar";
  }
});
