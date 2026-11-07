# 给浏览器 agent 的自动巡检提示词（全页面爬取版）

和 `BROWSER-TEST-PROMPT.md` 的区别：不靠肉眼一页页看，而是在浏览器 Console 里跑一段脚本，自动拿到每个页面的 HTTP 状态码、JS 报错和露出的字典编号。这样可以绕开"内置浏览器读不到 Network 面板"的限制。

开始前你先在那个浏览器里登录好路由器。把下面分隔线之间的内容整段发给 agent。

---

请在已登录的华硕路由器管理页（http://192.168.50.1 ，已经登录，不要输入任何密码；看到登录页就停下来告诉我）上做一次**只读**自动巡检。

规则：
- 只运行下面这段脚本，并把输出完整交回给我
- 不要点击页面上任何按钮，不要修改任何设置
- 脚本只做两件事：读取页面（GET 请求），以及把页面加载到一个隐藏的 iframe 里收集报错。它不会提交任何表单

步骤：
1. 打开 http://192.168.50.1/index.asp ，按 Cmd+Shift+R 强制刷新
2. 打开开发者工具的 Console，粘贴下面整段代码，回车运行
3. 脚本大约需要几分钟。结束后会打印一个 Markdown 表格，同时把结果存到 `window.__crawl`。把表格完整复制给我
4. 如果脚本中途报错停下，把报错原文发给我

```js
(async () => {
  // 加载时可能触发动作的页面，一律跳过
  const SKIP = /QIS_wizard|Advanced_FirmwareUpgrade|Advanced_SettingBackup|Advanced_Feedback|Main_Login|Logout|Reboot|AiMesh_Node|detect_firmware|Module_Softsetting/i;
  const menu = await new Promise(r => require(['/require/modules/menuTree.js'], m => r(m)));
  const exMenus = new Set(menu.exclude.menus()), exTabs = new Set(menu.exclude.tabs());
  const urls = [];
  for (const m of menu.list) {
    if (exMenus.has(m.index)) continue;
    for (const t of m.tab) {
      if (!t.url || t.url === 'NULL' || /<%|^javascript/i.test(t.url) || exTabs.has(t.url)) continue;
      if (!urls.includes(t.url)) urls.push(t.url);
    }
  }
  const rows = [];
  const frame = document.createElement('iframe');
  frame.style.cssText = 'position:absolute;left:-9999px;width:1200px;height:900px';
  document.body.appendChild(frame);
  for (const u of urls) {
    const row = { url: u, status: '', errors: [], tokens: 0, note: '' };
    if (SKIP.test(u)) { row.note = '跳过（加载可能触发动作）'; rows.push(row); continue; }
    try {
      const res = await fetch('/' + u, { credentials: 'same-origin', cache: 'no-store' });
      row.status = res.status;
      const html = await res.text();
      if (/Main_Login\.asp|login_authorization/.test(html) && !/Main_Login/.test(u)) row.note = '被重定向到登录页';
      // 抓页面引用的静态资源，逐个查状态码
      const refs = [...html.matchAll(/(?:src|href)=["'](\/?[\w./-]+\.(?:js|css|png|gif|svg|jpg|asp|htm|html))["']/gi)].map(m => m[1]);
      for (const r of [...new Set(refs)].slice(0, 80)) {
        const p = r.startsWith('/') ? r : '/' + r;
        const rr = await fetch(p, { method: 'GET', credentials: 'same-origin', cache: 'no-store' });
        if (rr.status >= 400) row.errors.push(`资源 ${p} → ${rr.status}`);
      }
    } catch (e) { row.status = 'fetch 失败'; row.errors.push(String(e)); }
    // 在隐藏 iframe 里加载，收集 JS 报错
    await new Promise(resolve => {
      const done = () => setTimeout(resolve, 2500);
      frame.onload = () => {
        try {
          const w = frame.contentWindow;
          w.addEventListener('error', ev => row.errors.push('JS: ' + (ev.message || ev.type)));
          w.addEventListener('unhandledrejection', ev => row.errors.push('Promise: ' + (ev.reason && ev.reason.message || ev.reason)));
          const origErr = w.console.error.bind(w.console);
          w.console.error = (...a) => { row.errors.push('console.error: ' + a.map(String).join(' ').slice(0, 160)); origErr(...a); };
          const text = w.document.body ? w.document.body.innerText : '';
          row.tokens = (text.match(/<#\d+#>/g) || []).length;
          if (/\bundefined\b/.test(text)) row.note += ' 正文含 undefined';
        } catch (e) { row.errors.push('读取 iframe 失败: ' + e); }
        done();
      };
      frame.onerror = done;
      frame.src = '/' + u;
      setTimeout(resolve, 12000);
    });
    rows.push(row);
    console.log(`[${rows.length}/${urls.length}] ${u} ${row.status} 错误${row.errors.length}`);
  }
  window.__crawl = rows;
  const md = ['| 页面 | HTTP | 露出编号 | 报错 / 说明 |', '|---|---|---|---|']
    .concat(rows.map(r => `| ${r.url} | ${r.status} | ${r.tokens || ''} | ${[r.note, ...r.errors].filter(Boolean).join('<br>').replace(/\|/g, '/')} |`));
  console.log(md.join('\n'));
})();
```

最后请总结：一共多少页、多少页有报错、多少页被跳过，然后列出所有 HTTP 状态不是 200 的页面和资源。

---
