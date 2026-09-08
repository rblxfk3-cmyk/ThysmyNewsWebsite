const form = document.getElementById("registerForm");
const msg = document.getElementById("msg");
const btn = document.getElementById("registerBtn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  msg.textContent = "Creating account…";
  btn.disabled = true;
  btn.textContent = "Creating…";

  try {
    const r = await fetch("/api/auth/register", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        email: document.getElementById("email").value.trim(),
        password: document.getElementById("password").value
      })
    });

    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || "Registration failed");

    document.getElementById("registerContent").classList.add("hidden");
    document.getElementById("registerSuccess").classList.remove("hidden");
  } catch (err) {
    msg.textContent = err.message;
    btn.disabled = false;
    btn.textContent = "Register";
  }
});
