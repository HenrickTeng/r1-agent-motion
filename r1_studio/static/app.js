const state = {
  tab: "teleop",
  armed: null,
  cameraSource: "",
  switching: false,
  keys: new Set(),
  catalog: { actions: [], compositions: {}, speech: {} },
  stack: [],
  teleopBusy: false,
  teleopAgain: false,
  holdGapMs: 450,
  lastHoldSend: 0,
};

const FEATURE_NAMES = {
  teleop: "键盘遥控",
  gesture: "手势操作",
  vision: "校园识别",
  blocks: "图形化编程",
};

const CAM_NAMES = {
  laptop: "笔记本摄像头",
  r1: "R1 机载摄像头",
};

const SAFETY =
  "已经发给机器人的指令无法从网页撤回。软急停只停后续下发；正在走的步态请立刻按遥控器急停。";

const $ = (id) => document.getElementById(id);

async function api(path, body) {
  const res = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return res.json();
}

function paintState(data, light = false) {
  if (!data) return;
  $("reply").textContent = data.reply || "";
  $("error").textContent = data.error || "";
  $("mode-chip").textContent = state.armed ? FEATURE_NAMES[state.armed] : "未开启";
  $("hw-chip").textContent = data.hardware
    ? (data.robot_ready === false ? "连接中" : "真机")
    : "仿真";
  $("busy-chip").textContent = data.busy ? "忙碌" : "空闲";
  $("camera-label").textContent = data.camera || "";
  if ($("cam-laptop") && $("cam-r1")) {
    $("cam-laptop").classList.toggle("active", data.camera_source === "laptop");
    $("cam-r1").classList.toggle("active", data.camera_source === "r1");
  }
  paintGestureSheet(data);
  $("gesture-label").textContent = data.gesture || "";
  const detail = data.gesture_detail;
  if (detail) {
    $("recog-label").textContent = detail.label || data.gesture || "—";
    $("recog-poses").textContent =
      (detail.strategy === "pose" ? "姿势：" : "手：") + ((detail.poses || []).join(" / ") || "无");
    $("recog-twist").innerHTML =
      `<code>vx ${(detail.vx || 0).toFixed(2)}　vy ${(detail.vy || 0).toFixed(2)}　ω ${(detail.omega || 0).toFixed(2)}</code>`;
    if ($("cam-twist") && state.armed !== "teleop") {
      $("cam-twist").textContent =
        `vx ${(detail.vx || 0).toFixed(2)}　vy ${(detail.vy || 0).toFixed(2)}　ω ${(detail.omega || 0).toFixed(2)}`;
    }
    const skip = detail.skip || "";
    const issued = detail.issued === true;
    const holding = skip.indexOf("节流") >= 0;
    if (data.mode === "gesture" && detail.kind === "drive" && (issued || holding)) {
      $("recog-kind").textContent = issued ? "已下发速度" : "速度保持中";
    } else if (detail.kind === "cheer") {
      $("recog-kind").textContent = "欢呼";
    } else if (detail.kind === "stop") {
      $("recog-kind").textContent = "停";
    } else {
      $("recog-kind").textContent = skip || "未下发（悬停/未开手势不会走）";
    }
    if ($("recog-operator")) {
      const st = detail.operator || "off";
      const text = st === "locked"
        ? (detail.strategy === "pose" ? "操控者：已锁定（全身 Pose）" : "操控者：已锁定")
        : st === "hunting"
          ? (detail.operator_label || "操控者：侧平举锁定")
          : "操控者：笔记本用手部关键点";
      $("recog-operator").textContent = text;
    }
  }
  if (!light) {
    state.cameraSource = data.camera_source || state.cameraSource;
  }
  paintTeleopHud();
  if ($("arm-banner")) {
    $("arm-banner").textContent = state.armed
      ? `使用中：${FEATURE_NAMES[state.armed]}。换选项卡或摄像头会先停止新指令。`
      : "当前没有开启课堂功能。点「开始」才会向 R1 发指令。";
  }
  if (light) return;
  if (data.presets) renderPresets(data.presets);
  if (data.groups) renderGroups(data.groups);
  if (data.vision && data.vision.items) {
    $("vision-items").innerHTML = data.vision.items
      .map((item) => `<li>${item.title}（${item.category}）${Math.round(item.score * 100)}%</li>`)
      .join("");
  }
  const campus = data.campus;
  if (campus && !light) {
    if ($("llm-url") && !$("llm-url").value && campus.url) $("llm-url").value = campus.url;
    if ($("llm-model") && !$("llm-model").value && campus.model) $("llm-model").value = campus.model;
    if ($("library-on")) $("library-on").checked = !!campus.library_on;
    if ($("vision-chat")) {
      $("vision-chat").innerHTML = (campus.turns || [])
        .map((turn) => `<p class="${turn.role}"><strong>${turn.role === "user" ? "问" : "R1"}</strong> ${turn.content}</p>`)
        .join("");
    }
  }
}

function renderPresets(presets) {
  const box = $("presets");
  box.innerHTML = "";
  for (const item of presets) {
    const btn = document.createElement("button");
    btn.textContent = `${item.title}\n${item.hint}`;
    btn.style.whiteSpace = "pre-line";
    btn.onclick = async () => {
      if (state.armed !== "teleop") {
        await confirmChoice({ title: "请先开始键盘遥控", body: "点「开始键盘遥控」后再用预设。", yes: "知道了" });
        return;
      }
      paintState(await api("/api/run", { preset: item.id }));
    };
    box.appendChild(btn);
  }
}

function toolboxItems(catalog, groups) {
  const move = catalog.actions.filter((a) => a.kind === "move");
  const turn = catalog.actions.filter((a) => a.kind === "turn");
  const arm = catalog.actions.filter((a) => a.kind === "arm");
  const items = [
    { type: "say", title: "说话", color: "say", extra: { text: "你好，同学们" } },
    { type: "wait", title: "等待 1 秒", color: "wait", extra: { seconds: 1 } },
    ...move.map((a) => ({ type: "move", title: a.title, color: "move", extra: { name: a.name, repeat: 1 } })),
    ...turn.map((a) => ({ type: "turn", title: a.title, color: "turn", extra: { name: a.name } })),
    ...arm.map((a) => ({ type: "action", title: a.title, color: "arm", extra: { name: a.name } })),
    ...Object.keys(catalog.compositions || {}).map((name) => ({
      type: "group",
      title: "组合：" + name,
      color: "group",
      extra: { name },
    })),
  ];
  for (const name of Object.keys(groups || {})) {
    items.push({ type: "custom", title: "我的：" + name, color: "custom", extra: { name } });
  }
  return items;
}

function renderToolbox(catalog, groups) {
  const box = $("toolbox");
  box.innerHTML = "<strong>方块箱</strong><p class=\"hint\">点彩色方块加入程序；点「看」只预览命令，不会动机器人。</p>";
  for (const item of toolboxItems(catalog, groups)) {
    const row = document.createElement("div");
    row.className = "tool-row";
    const btn = document.createElement("button");
    btn.className = "tool " + item.color;
    btn.textContent = item.title;
    btn.onclick = () => {
      state.stack.push({ type: item.type, title: item.title, ...item.extra });
      renderStack();
    };
    const peek = document.createElement("button");
    peek.className = "peek " + item.color;
    peek.textContent = "看";
    peek.title = "看这个方块会发给 R1 什么命令";
    peek.onclick = async (event) => {
      event.stopPropagation();
      showInspect(await api("/api/program/inspect", {
        name: item.title,
        blocks: [{ type: item.type, ...item.extra }],
      }));
    };
    row.appendChild(btn);
    row.appendChild(peek);
    box.appendChild(row);
  }
}

function renderStack() {
  const stack = $("stack");
  stack.innerHTML = "";
  state.stack.forEach((block, index) => {
    const li = document.createElement("li");
    li.className = "tool " + (block.type === "action" ? "arm" : block.type);
    const label = document.createElement("span");
    label.textContent = `${index + 1}. ${block.title || block.name}`;
    const actions = document.createElement("span");
    const peek = document.createElement("button");
    peek.className = "peek";
    peek.textContent = "看命令";
    peek.onclick = () => inspectBlocks(index);
    const del = document.createElement("button");
    del.textContent = "×";
    del.onclick = () => {
      state.stack.splice(index, 1);
      renderStack();
    };
    actions.appendChild(peek);
    actions.appendChild(del);
    li.appendChild(label);
    li.appendChild(actions);
    stack.appendChild(li);
  });
}

function programPayload() {
  return {
    schema: "r1-student-program/v1",
    name: $("prog-name").value,
    author: $("prog-author").value,
    blocks: state.stack.map(({ title, ...rest }) => rest),
  };
}

function renderGroups(groups) {
  const box = $("my-groups");
  box.innerHTML = "";
  for (const [name, steps] of Object.entries(groups || {})) {
    const row = document.createElement("p");
    row.textContent = name + " → " + steps.join("，");
    const del = document.createElement("button");
    del.className = "ghost";
    del.textContent = "删除";
    del.onclick = async () => {
      const data = await api("/api/groups/delete", { name });
      await refresh();
      paintState(data);
    };
    row.appendChild(del);
    box.appendChild(row);
  }
}

async function refresh() {
  const data = await api("/api/state");
  paintState(data);
  const catalog = await api("/api/catalog");
  state.catalog = catalog;
  renderToolbox(catalog, data.groups || {});
  return data;
}

function currentKeys() {
  return [...state.keys];
}

function paintTeleopHud() {
  document.querySelectorAll("#teleop-keys kbd").forEach((el) => {
    el.classList.toggle("down", state.keys.has(el.dataset.key));
  });
  if (!$("teleop-status")) return;
  if (state.armed !== "teleop") {
    $("teleop-status").textContent = "未开始：键盘和下面的 QWEASD 都不会发给机器人。先点「开始键盘遥控」。";
    return;
  }
  const held = currentKeys().filter((key) => key !== "shift");
  $("teleop-status").textContent = held.length
    ? "正在发给机器人：" + held.join(" ").toUpperCase() + "。松开或点空格会停。"
    : "已开始：请先点一下 QWEASD 格子（格子会亮），再按键盘。切走浏览器再切回来也是为了重新点进这一页。";
}

async function sendTeleop() {
  if (state.armed !== "teleop") return;
  if (state.teleopBusy) {
    if (!currentKeys().length) state.teleopAgain = true;
    return;
  }
  state.teleopBusy = true;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 4000);
  try {
    const res = await fetch("/api/teleop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keys: currentKeys(), slow: state.keys.has("shift") }),
      signal: ctrl.signal,
    });
    const data = await res.json();
    if (data.vx !== undefined) {
      $("twist").textContent = `${data.vx.toFixed(2)}, ${data.vy.toFixed(2)}, ${data.omega.toFixed(2)}`;
      if ($("cam-twist")) {
        $("cam-twist").textContent =
          `vx ${data.vx.toFixed(2)}　vy ${data.vy.toFixed(2)}　ω ${data.omega.toFixed(2)}`;
      }
    }
    if (data.duration) state.holdGapMs = Math.max(400, Math.round(Number(data.duration) * 900));
    if (data.error) $("error").textContent = data.error;
    else if (data.ok) $("error").textContent = "";
  } catch (_err) {
    $("error").textContent = "这次按键没发出去。请点一下 QWEASD 格子再按，或看终端是否卡在 StopMove。";
  } finally {
    clearTimeout(timer);
    state.teleopBusy = false;
    if (state.teleopAgain) {
      state.teleopAgain = false;
      sendTeleop();
    }
  }
}

async function haltTeleop() {
  state.keys.clear();
  state.teleopAgain = false;
  state.teleopBusy = false;
  paintTeleopHud();
  try {
    const data = await api("/api/teleop", { keys: [] });
    if (data.vx !== undefined) {
      $("twist").textContent = `${data.vx.toFixed(2)}, ${data.vy.toFixed(2)}, ${data.omega.toFixed(2)}`;
      if ($("cam-twist")) {
        $("cam-twist").textContent =
          `vx ${data.vx.toFixed(2)}　vy ${data.vy.toFixed(2)}　ω ${data.omega.toFixed(2)}`;
      }
    }
  } catch (_err) {
    /* 服务端 0.8s 无新指令会停 */
  }
}

function paintGestureSheet(data) {
  const sheet = $("gesture-sheet");
  if (!sheet) return;
  const r1 = (data.camera_source || state.cameraSource) === "r1";
  if ($("gesture-list-laptop")) $("gesture-list-laptop").classList.toggle("hidden", r1);
  if ($("gesture-list-r1")) $("gesture-list-r1").classList.toggle("hidden", !r1);
  if ($("gesture-sheet-title")) {
    $("gesture-sheet-title").textContent = r1 ? "R1 机载摄像头手势" : "笔记本摄像头手势";
  }
  const poses = ((data.gesture_detail || {}).poses || []).slice();
  const kindPose = (data.gesture_detail || {}).kind === "cheer" ? "peace" : "";
  const active = new Set(poses);
  if (poses.filter((p) => p === "palm").length >= 2) active.add("palms");
  if (kindPose) active.add(kindPose);
  const shape = poses[0] || "";
  document.querySelectorAll(".gesture-list li").forEach((item) => {
    const key = item.dataset.pose;
    item.classList.toggle("active", active.has(key) || key === shape);
  });
}

function showInspect(data) {
  if (!data || !data.ok) {
    $("error").textContent = (data && data.error) || "看不出命令";
    return;
  }
  $("inspect-title").textContent = data.scope === "program" ? "整段程序发给 R1 的命令" : "这一块发给 R1 的命令";
  $("inspect-heading").textContent = data.heading || "";
  $("inspect-steps").innerHTML = (data.steps || [])
    .map((step) => `<li><strong>${step.summary}</strong><br /><code>${step.command}</code><br /><small>${step.channel}</small></li>`)
    .join("");
  $("inspect-text").textContent = data.text || "";
  $("inspect-mask").classList.remove("hidden");
}

async function inspectBlocks(index) {
  const payload = programPayload();
  if (index !== undefined) payload.index = index;
  showInspect(await api("/api/program/inspect", payload));
}

function showTab(name) {
  state.tab = name;
  document.querySelectorAll("nav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  ["teleop", "gesture", "vision", "blocks"].forEach((id) => {
    $("panel-" + id).classList.toggle("hidden", id !== name);
  });
  if ($("recog")) $("recog").classList.toggle("hidden", name !== "gesture");
  if ($("speed-line")) $("speed-line").classList.toggle("hidden", name === "gesture");
  if ($("campus-api")) $("campus-api").classList.toggle("hidden", name !== "vision");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function confirmChoice({ title, body, yes, no }) {
  return new Promise((resolve) => {
    $("confirm-title").textContent = title;
    $("confirm-body").textContent = body;
    $("confirm-yes").textContent = yes || "确定";
    $("confirm-no").textContent = no || "取消";
    $("confirm-no").classList.toggle("hidden", !no);
    $("confirm-mask").classList.remove("hidden");
    const finish = (value) => {
      $("confirm-mask").classList.add("hidden");
      $("confirm-yes").onclick = null;
      $("confirm-no").onclick = null;
      resolve(value);
    };
    $("confirm-yes").onclick = () => finish(true);
    $("confirm-no").onclick = () => finish(false);
  });
}

async function stopSending() {
  state.keys.clear();
  state.teleopAgain = false;
  state.teleopBusy = false;
  const previous = state.armed;
  state.armed = null;
  await api("/api/mode", { mode: "idle" });
  await sleep(280);
  return previous;
}

async function noticeStopped(name) {
  await confirmChoice({
    title: "已停止向 R1 发送新指令",
    body: (name ? `「${name}」已结束。` : "") + SAFETY,
    yes: "知道了",
  });
}

async function startFeature(name) {
  if (state.switching) return;
  if (state.armed === name) {
    showTab(name);
    return;
  }
  state.switching = true;
  try {
    if (state.armed) {
      const from = FEATURE_NAMES[state.armed];
      await stopSending();
      await noticeStopped(from);
    }
    showTab(name);
    state.armed = name;
    if (name === "teleop") {
      state.teleopBusy = false;
      state.keys.clear();
      const pad = $("teleop-keys");
      if (pad) pad.focus();
      const focus = document.activeElement;
      if (focus && (focus.tagName === "INPUT" || focus.tagName === "TEXTAREA")) {
        focus.blur();
        if (pad) pad.focus();
      }
      paintTeleopHud();
    }
    const data = await api("/api/mode", { mode: name });
    if (state.armed === name) paintState(data);
  } finally {
    state.switching = false;
  }
}

async function stopFeature() {
  if (state.switching) return;
  if (!state.armed) {
    await confirmChoice({
      title: "当前没有开启的功能",
      body: "没有正在向 R1 发送的新指令。",
      yes: "知道了",
    });
    return;
  }
  state.switching = true;
  try {
    const from = FEATURE_NAMES[state.armed];
    await stopSending();
    await noticeStopped(from);
  } finally {
    state.switching = false;
  }
}

async function requestTab(name) {
  if (state.switching) return;
  if (state.armed && state.armed !== name) {
    state.switching = true;
    try {
      const from = FEATURE_NAMES[state.armed];
      await stopSending();
      const go = await confirmChoice({
        title: "已停止向 R1 发送新指令",
        body: `刚才开着「${from}」。${SAFETY}切换到「${FEATURE_NAMES[name]}」后也要再点「开始」才会发指令。`,
        yes: "关闭并切换过去",
        no: "留在当前页（需重新点开始）",
      });
      if (go) showTab(name);
    } finally {
      state.switching = false;
    }
    return;
  }
  showTab(name);
}

async function requestCamera(source) {
  if (state.switching) return;
  if ((state.cameraSource || "") === source) return;
  state.switching = true;
  try {
    if (state.armed) {
      const from = FEATURE_NAMES[state.armed];
      await stopSending();
      const go = await confirmChoice({
        title: "已停止向 R1 发送新指令",
        body: `换摄像头前已停掉「${from}」。${SAFETY}换过去后要重新点「开始」。`,
        yes: "关闭功能并切换摄像头",
        no: "不换摄像头（需重新点开始）",
      });
      if (!go) return;
    }
    const payload = source === "r1" ? { source: "r1" } : { source: "laptop", camera: 0 };
    paintState(await api("/api/camera", payload));
    state.cameraSource = source;
  } finally {
    state.switching = false;
  }
}

document.querySelectorAll("nav button").forEach((btn) => {
  btn.onclick = () => requestTab(btn.dataset.tab);
});

$("estop").onclick = async () => {
  state.armed = null;
  state.keys.clear();
  paintState(await api("/api/estop", {}));
};
$("clear-estop").onclick = async () => paintState(await api("/api/estop/clear", {}));
$("send-text").onclick = async () => {
  paintState(await api("/api/text", { text: $("utterance").value }));
};
$("listen").onclick = async () => paintState(await api("/api/listen", {}));
$("start-teleop").onclick = () => startFeature("teleop");
$("stop-teleop").onclick = () => stopFeature();
$("start-gesture").onclick = () => startFeature("gesture");
$("stop-gesture").onclick = () => stopFeature();
$("start-vision").onclick = () => startFeature("vision");
$("stop-vision").onclick = () => stopFeature();
$("start-blocks").onclick = () => startFeature("blocks");
$("stop-blocks").onclick = () => stopFeature();
$("cam-laptop").onclick = () => requestCamera("laptop");
$("cam-r1").onclick = () => requestCamera("r1");
$("capture-vision").onclick = async () => {
  if (state.armed !== "vision") {
    await confirmChoice({ title: "请先开始校园识别", body: "点「开始校园识别」后再提问。", yes: "知道了" });
    return;
  }
  const question = ($("vision-question") && $("vision-question").value) || "";
  const data = await api("/api/vision", { speak: true, question });
  paintState(await api("/api/state"));
};
if ($("save-campus")) {
  $("save-campus").onclick = async () => {
    paintState(await api("/api/campus", {
      api_key: $("llm-key").value,
      api_url: $("llm-url").value,
      model: $("llm-model").value,
      extra: $("campus-extra").value,
      library_on: $("library-on").checked,
    }));
  };
}
$("run-prog").onclick = async () => {
  if (state.armed !== "blocks") {
    await confirmChoice({ title: "请先开始图形化", body: "点「开始图形化」后再运行程序。", yes: "知道了" });
    return;
  }
  paintState(await api("/api/program/run", programPayload()));
};
$("check-prog").onclick = async () => {
  const data = await api("/api/program/validate", programPayload());
  $("error").textContent = data.ok ? "检查通过：" + (data.titles || []).join(" → ") : data.error;
};
$("inspect-prog").onclick = () => inspectBlocks();
if ($("inspect-close")) {
  $("inspect-close").onclick = () => $("inspect-mask").classList.add("hidden");
}
$("save-prog").onclick = () => {
  const blob = new Blob([JSON.stringify(programPayload(), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = ($("prog-name").value || "program") + ".r1prog.json";
  a.click();
};
$("load-prog").onchange = async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const payload = JSON.parse(await file.text());
  $("prog-name").value = payload.name || "未命名";
  $("prog-author").value = payload.author || "同学";
  state.stack = (payload.blocks || []).map((block) => ({ ...block, title: block.name || block.type }));
  renderStack();
};
$("save-group").onclick = async () => {
  const steps = state.stack
    .filter((block) => block.name && ["action", "move", "turn"].includes(block.type))
    .map((block) => block.name);
  const data = await api("/api/groups", { name: $("group-name").value, steps });
  if (!data.ok) $("error").textContent = data.error || "";
  await refresh();
};

const KEY_MAP = {
  KeyW: "w",
  KeyA: "a",
  KeyS: "s",
  KeyD: "d",
  KeyQ: "q",
  KeyE: "e",
  ArrowUp: "arrowup",
  ArrowDown: "arrowdown",
  ArrowLeft: "arrowleft",
  ArrowRight: "arrowright",
  ShiftLeft: "shift",
  ShiftRight: "shift",
};

document.addEventListener("keydown", (event) => {
  const tag = (event.target && event.target.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if ($("confirm-mask") && !$("confirm-mask").classList.contains("hidden")) return;
  if (state.armed !== "teleop") return;
  if (event.code === "Space") {
    event.preventDefault();
    haltTeleop();
    return;
  }
  const name = KEY_MAP[event.code];
  if (!name) return;
  event.preventDefault();
  if (event.repeat) return;
  state.keys.add(name);
  state.lastHoldSend = Date.now();
  paintTeleopHud();
  sendTeleop();
}, true);
document.addEventListener("keyup", (event) => {
  const name = KEY_MAP[event.code];
  if (!name) return;
  state.keys.delete(name);
  paintTeleopHud();
  if (state.armed === "teleop") sendTeleop();
}, true);
if ($("teleop-keys")) {
  $("teleop-keys").addEventListener("pointerdown", (event) => {
    const key = event.target && event.target.dataset && event.target.dataset.key;
    if (!key) return;
    event.preventDefault();
    if (state.armed !== "teleop") return;
    $("teleop-keys").focus();
    event.target.setPointerCapture(event.pointerId);
    state.keys.add(key);
    state.lastHoldSend = Date.now();
    paintTeleopHud();
    sendTeleop();
  });
  const padUp = (event) => {
    const key = event.target && event.target.dataset && event.target.dataset.key;
    if (!key) return;
    state.keys.delete(key);
    paintTeleopHud();
    if (state.armed === "teleop") sendTeleop();
  };
  $("teleop-keys").addEventListener("pointerup", padUp);
  $("teleop-keys").addEventListener("pointercancel", padUp);
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden && state.armed === "teleop") haltTeleop();
});
setInterval(() => {
  if (!state.keys.size) return;
  const now = Date.now();
  if (now - state.lastHoldSend < (state.holdGapMs || 450)) return;
  state.lastHoldSend = now;
  sendTeleop();
}, 80);
setInterval(refresh, 2000);
setInterval(async () => {
  paintState(await api("/api/state"), true);
}, 250);
refresh();
showTab(state.tab);
