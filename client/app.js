const $ = (id) => document.getElementById(id);
const base = $("base");
const token = $("token");
const health = $("health");
const message = $("message");
let taskTimer = null;

base.value = sessionStorage.getItem("agentBase") || location.origin;
token.value = sessionStorage.getItem("agentToken") || "";

function apiUrl(path) {
  const root = base.value.trim().replace(/\/$/, "");
  if (!/^https?:\/\//i.test(root)) throw new Error("API base must start with http:// or https://");
  return root + path;
}

function headers() {
  const value = token.value.trim();
  if (!value) throw new Error("Enter the Bearer token.");
  return { Authorization: "Bearer " + value };
}

function setMessage(text, error = false) {
  message.textContent = text;
  message.className = error ? "message error" : "message";
}

async function checkHealth() {
  try {
    const response = await fetch(apiUrl("/health"), { cache: "no-store" });
    const data = await response.json();
    health.textContent = response.ok ? "online" : "error";
    health.dataset.state = response.ok ? "ok" : "error";
    return response.ok && data.status === "ok";
  } catch (error) {
    health.textContent = "offline";
    health.dataset.state = "error";
    return false;
  }
}

$("save").onclick = () => {
  try {
    sessionStorage.setItem("agentBase", base.value.trim());
    sessionStorage.setItem("agentToken", token.value.trim());
    setMessage("Saved for this browser session.");
    checkHealth();
  } catch (error) { setMessage(error.message, true); }
};

$("clear").onclick = () => {
  sessionStorage.removeItem("agentBase");
  sessionStorage.removeItem("agentToken");
  token.value = "";
  setMessage("Session credentials cleared.");
};

async function startTask() {
  try {
    const goal = $("goal").value.trim();
    const max_steps = Number($("steps").value);
    if (!goal) throw new Error("Enter a goal.");
    const response = await fetch(apiUrl("/tasks"), {
      method: "POST", headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify({ goal, max_steps })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Task submission failed.");
    $("taskCard").classList.remove("hidden");
    $("taskId").textContent = data.task_id;
    setMessage("Task started.");
    pollTask(data.task_id);
  } catch (error) { setMessage(error.message, true); }
}

async function pollTask(taskId) {
  clearTimeout(taskTimer);
  try {
    const response = await fetch(apiUrl("/tasks/" + encodeURIComponent(taskId)), { headers: headers(), cache: "no-store" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Task lookup failed.");
    $("status").textContent = data.status;
    $("step").textContent = String(data.current_step ?? "-") + " / " + String(data.max_steps ?? "-");
    $("verified").textContent = data.verified ? "yes" : "no";
    $("history").textContent = JSON.stringify(data.history || [], null, 2);
    if (data.status === "running" || data.status === "pending") taskTimer = setTimeout(() => pollTask(taskId), 1200);
    else setMessage("Task " + data.status + ".");
  } catch (error) {
    setMessage(error.message, true);
    taskTimer = setTimeout(() => pollTask(taskId), 2500);
  }
}

$("run").onclick = startTask;
checkHealth();
