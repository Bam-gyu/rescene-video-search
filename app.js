const REPO = "Bam-gyu/rescene-video-search";
const RULES = {
  long: "최근 7일 업로드 · 조회수 5만 이상 · 리센느 전용 팬 채널 제외",
  shorts: "최근 7일 업로드 · 조회수 20만 이상",
};

const $ = (id) => document.getElementById(id);
const store = {
  get(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch {}
  },
};

let data = { long: [], shorts: [] };
let tab = store.get("tab", "long");
let hidden = store.get("hiddenChannels", {}); // { channelId: channelTitle }
// "NEW" 표시 기준: 이전 방문 때 본 데이터의 갱신 시각
const lastSeen = store.get("lastSeenUpdate", null);

const fmtViews = (n) =>
  n >= 1e8 ? `${+(n / 1e8).toFixed(1)}억회` : n >= 1e4 ? `${+(n / 1e4).toFixed(1)}만회` : `${n.toLocaleString()}회`;
const fmtDate = (iso) => {
  const d = new Date(iso);
  return `${d.getFullYear()}.${d.getMonth() + 1}.${d.getDate()}`;
};
const dayKey = (iso) => {
  const d = new Date(iso);
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 864e5);
  if (days === 0) return "오늘";
  if (days === 1) return "어제";
  return `${d.getMonth() + 1}월 ${d.getDate()}일 (${"일월화수목금토"[d.getDay()]})`;
};
const esc = (s) => s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
// API 제목은 HTML 엔티티가 섞여 올 수 있어 한 번 풀어준다
const decode = (s) => {
  const t = document.createElement("textarea");
  t.innerHTML = s;
  return t.value;
};

function card(v, isShort) {
  const url = isShort ? `https://www.youtube.com/shorts/${v.id}` : `https://www.youtube.com/watch?v=${v.id}`;
  const img = isShort ? `https://i.ytimg.com/vi/${v.id}/oardefault.jpg` : v.thumbnail;
  const fallback = `https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`;
  const isNew = lastSeen && v.listedAt && v.listedAt > lastSeen;
  const title = esc(decode(v.title));
  const channel = esc(decode(v.channelTitle));
  return `
    <article class="card">
      <a class="thumb" href="${url}" target="_blank" rel="noopener">
        <img src="${img}" alt="" loading="lazy" onerror="this.onerror=null;this.src='${fallback}'">
        ${isNew ? '<span class="badge-new">NEW</span>' : ""}
        <span class="views">${fmtViews(v.views)}</span>
      </a>
      <div class="meta">
        <a class="t" href="${url}" target="_blank" rel="noopener" title="${title}">${title}</a>
        <div class="sub">${channel} · ${fmtDate(v.publishedAt)}</div>
      </div>
      <button class="hide-btn" data-channel="${esc(v.channelId)}" data-title="${channel}" title="이 채널 숨기기" aria-label="이 채널 숨기기">✕</button>
    </article>`;
}

function render() {
  const q = $("filter").value.trim().toLowerCase();
  const visible = (list) => list.filter((v) => !hidden[v.channelId]);
  const items = visible(data[tab]).filter(
    (v) => !q || decode(v.title).toLowerCase().includes(q) || decode(v.channelTitle).toLowerCase().includes(q)
  );

  $("count-long").textContent = visible(data.long).length;
  $("count-shorts").textContent = visible(data.shorts).length;
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === tab));
  $("rule").textContent = RULES[tab];

  // 업로드 날짜별로 묶어서 표시 (목록은 이미 최신순)
  const groups = new Map();
  for (const v of items) {
    const k = dayKey(v.publishedAt);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(v);
  }
  const isShort = tab === "shorts";
  $("list").innerHTML = [...groups]
    .map(([m, vs]) => `<h2 class="month">${m}</h2><div class="grid ${isShort ? "shorts" : ""}">${vs.map((v) => card(v, isShort)).join("")}</div>`)
    .join("");

  const empty = $("empty");
  empty.hidden = items.length > 0;
  empty.textContent = q ? `'${$("filter").value.trim()}'에 해당하는 영상이 없어요.` : "최근 7일 동안 조건에 맞는 영상이 없어요.";

  renderHidden();
}

function renderHidden() {
  const ids = Object.keys(hidden);
  $("hidden-box").hidden = ids.length === 0;
  $("hidden-count").textContent = ids.length;
  $("hidden-list").innerHTML = ids
    .map((id) => `<li><span>${esc(hidden[id])}</span><button data-unhide="${esc(id)}">다시 보기</button></li>`)
    .join("");
}

let toastTimer;
function toast(html, ms = 6000) {
  const el = $("toast");
  el.innerHTML = html;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), ms);
}

function hideChannel(id, title) {
  hidden[id] = title;
  store.set("hiddenChannels", hidden);
  render();
  toast(
    `<span><b>${esc(title)}</b> 채널을 숨겼어요</span>
     <button data-undo="${esc(id)}">되돌리기</button>
     <button class="primary" data-block="${esc(id)}">자동 수집에서도 제외</button>`,
    8000
  );
}

document.addEventListener("click", (e) => {
  const t = e.target.closest("button");
  if (!t) return;
  if (t.dataset.tab) {
    tab = t.dataset.tab;
    store.set("tab", tab);
    render();
    window.scrollTo({ top: 0 });
  } else if (t.classList.contains("hide-btn")) {
    hideChannel(t.dataset.channel, t.dataset.title);
  } else if (t.dataset.undo || t.dataset.unhide) {
    delete hidden[t.dataset.undo || t.dataset.unhide];
    store.set("hiddenChannels", hidden);
    $("toast").hidden = true;
    render();
  } else if (t.dataset.block) {
    // 내용이 미리 채워진 GitHub 새 파일 화면(blocklist/채널ID.txt)을 연다. Commit 만 누르면 된다.
    const id = t.dataset.block;
    const value = `${id}  # ${hidden[id] || ""}\n`;
    const params = new URLSearchParams({ filename: `${id}.txt`, value });
    window.open(`https://github.com/${REPO}/new/main/blocklist?${params}`, "_blank", "noopener");
    toast("열린 GitHub 화면에서 Commit changes 만 누르면 돼요. 1~2분 뒤 페이지에 반영돼요.", 10000);
  }
});

$("filter").addEventListener("input", render);

fetch("data/videos.json", { cache: "no-cache" })
  .then((r) => r.json())
  .then((json) => {
    data = json;
    if (json.updatedAt) {
      const d = new Date(json.updatedAt);
      $("updated").textContent = `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")} 갱신`;
      store.set("lastSeenUpdate", json.updatedAt);
    } else {
      $("updated").textContent = "첫 갱신 대기 중";
    }
    render();
  })
  .catch(() => {
    $("updated").textContent = "데이터를 불러오지 못했어요";
    render();
  });
