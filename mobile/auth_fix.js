/* Auth fixes for Render + Google GIS */
(function () {
  function detailMsg(d, fallback) {
    if (!d) return fallback;
    if (typeof d.detail === "string") return d.detail;
    if (Array.isArray(d.detail)) return d.detail.map(function (x) { return x.msg || x; }).join(" ");
    return fallback;
  }
  window.initGoogle = async function () {
    if (window.googleReady) return;
    try {
      var cfg = await fetch(API + "/api/v1/auth/google/config").then(function (r) { return r.json(); });
      if (!cfg.enabled || !cfg.client_id) {
        var n = document.getElementById("googleNote");
        if (n) n.textContent = "Google sign-in can be enabled for this deployment.";
        return;
      }
      if (!window.google) {
        await new Promise(function (resolve, reject) {
          var sc = document.createElement("script");
          sc.src = "https://accounts.google.com/gsi/client";
          sc.async = true;
          sc.defer = true;
          sc.onload = resolve;
          sc.onerror = reject;
          document.head.appendChild(sc);
        });
      }
      window.handleGoogleCredential = async function (response) {
        setMsg("authmsg", "");
        try {
          var r = await fetch(API + "/api/v1/auth/google", {
            method: "POST",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ credential: response.credential })
          });
          var d = await r.json().catch(function () { return {}; });
          if (!r.ok) {
            setMsg("authmsg", detailMsg(d, "Could not authenticate with Google."));
            return;
          }
          await finishAuth();
        } catch (e) {
          setMsg("authmsg", "Google sign-in could not be completed right now.");
        }
      };
      google.accounts.id.initialize({
        client_id: cfg.client_id,
        callback: window.handleGoogleCredential,
        use_fedcm_for_prompt: false,
        auto_select: false
      });
      google.accounts.id.renderButton(document.getElementById("googleButton"), {
        type: "standard",
        theme: "outline",
        size: "large",
        text: "continue_with",
        shape: "rectangular",
        logo_alignment: "left",
        width: 330
      });
      window.googleReady = true;
    } catch (e) {
      var note = document.getElementById("googleNote");
      if (note) note.textContent = "Google sign-in is unavailable in this environment.";
    }
  };
  window.finishAuth = async function () {
    await fetch(API + "/api/v1/auth/csrf", { credentials: "include" });
    csrf = (document.cookie.split("; ").find(function (x) { return x.startsWith("nexgene_csrf="); }) || "").split("=")[1] || "";
    document.getElementById("auth").classList.add("hide");
    document.getElementById("account").textContent = "SIGN OUT";
    await loadProfile();
    await load();
  };
})();
